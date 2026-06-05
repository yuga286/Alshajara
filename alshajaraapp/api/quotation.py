import frappe
from frappe.utils import now, strip_html, now_datetime, add_days, getdate, nowdate, flt
from frappe import _
import io
import requests
from frappe.utils.file_manager import save_file
from barcode import Code128
from barcode.writer import ImageWriter
from erpnext.selling.doctype.quotation.quotation import make_sales_order as core_make_sales_order
from erpnext.setup.utils import get_exchange_rate

@frappe.whitelist()
def get_live_exchange_rate(from_currency, to_currency, transaction_date=None):
    if not from_currency or not to_currency:
        return 0

    if from_currency == to_currency:
        return 1

    if not transaction_date:
        transaction_date = nowdate()

    # Prefer ERPNext's own exchange-rate resolution so the result matches
    # Currency Exchange records and pegged-currency logic.
    try:
        rate = get_exchange_rate(from_currency, to_currency, transaction_date=transaction_date)
        if rate and flt(rate) > 0:
            return flt(rate)
    except Exception:
        pass

    response = requests.get(
        f"https://open.er-api.com/v6/latest/{from_currency}", timeout=8
    )
    response.raise_for_status()
    payload = response.json() or {}
    rates = payload.get("rates") or {}
    return flt(rates.get(to_currency) or 0)


@frappe.whitelist()
def create_currency_exchange(from_currency, to_currency, rate=None, key_date=None):
    """Create a Currency Exchange record for `key_date` using `rate` (or live rate if not provided).

    - `from_currency`, `to_currency`: currency codes, e.g. 'USD', 'KWD'
    - `rate`: optional numeric conversion rate (from -> to). If omitted, will call `get_live_exchange_rate`.
    - `key_date`: optional date string YYYY-MM-DD; defaults to today.

    Returns the name of the created Currency Exchange record.
    """
    if not from_currency or not to_currency:
        frappe.throw("from_currency and to_currency are required")

    if not key_date:
        key_date = nowdate()

    if not rate:
            rate = get_live_exchange_rate(from_currency, to_currency, key_date)

    if not rate or flt(rate) <= 0:
        frappe.throw(f"Could not determine exchange rate for {from_currency} to {to_currency}")

    doc = frappe.get_doc(
        {
            "doctype": "Currency Exchange",
            "date": key_date,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "exchange_rate": flt(rate),
            # make it applicable for both buying and selling to be safe
            "for_buying": 1,
            "for_selling": 1,
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return doc.name


@frappe.whitelist()
def add_quotation_note(quotation, note, next_follow_up_date=None):
	if not quotation or not note:
		frappe.throw(_("Missing quotation or note"))

	# Permission check
	doc = frappe.get_doc("Quotation", quotation)
	doc.check_permission("read")

	current_time = now()

	# 1️⃣ Clean note for summary fields (plain text only)
	clean_note = strip_html(note).strip()

	# 2️⃣ Get next proper idx for child table
	max_idx = frappe.db.sql(
		"""
		SELECT IFNULL(MAX(idx), 0)
		FROM `tabCRM Note`
		WHERE parent = %s
		  AND parenttype = 'Quotation'
		  AND parentfield = 'notes'
		""",
		(quotation,)
	)[0][0]

	next_idx = max_idx + 1

	# 3️⃣ Insert CRM Note with correct idx
	frappe.get_doc({
		"doctype": "CRM Note",
		"parent": quotation,
		"parenttype": "Quotation",
		"parentfield": "notes",
		"idx": next_idx,              # ✅ FIXED INDEX
		"note": note,                 # keep rich text here
		"added_by": frappe.session.user,
		"added_on": current_time,
	}).insert(ignore_permissions=True)

	# 4️⃣ Store CLEAN text in quotation summary fields
	frappe.db.set_value(
		"Quotation",
		quotation,
		{
			"last_communication_note": clean_note,
			"last_communication_date": current_time,
			"next_follow_up_date": next_follow_up_date,
		},
		update_modified=False
	)

	return True

@frappe.whitelist()
def mark_quotation_sent(name):
    now = now_datetime()

    # Record that this quotation was sent and who sent it
    frappe.db.set_value(
        "Quotation",
        name,
        {
            "_sent": "Sent",
            "send_by": frappe.session.user,
            "last_communication_note": "Quotation Sent",
            "last_communication_date": now,
            "next_follow_up_date": add_days(now, 1),
        },
        update_modified=False,
    )

    frappe.db.commit()

def set_custom_quotation_name(doc, method):
    # Safety: do not override if already named
    if doc.name and not doc.name.startswith("New"):
        return

    # 1. Company Code (static as per requirement)
    company_code = "3S"

    # 2. Date parts
    if not doc.transaction_date:
        frappe.throw("Transaction Date is required to generate Quotation number")

    date = getdate(doc.transaction_date)
    year = date.strftime("%y")
    month = date.strftime("%m")
    day = date.strftime("%d")

    # 3. Collect UNIQUE brand abbreviations from items
    if not doc.items:
        frappe.throw("At least one item is required to generate Quotation number")

    brand_abbrs = set()

    for item in doc.items:
        if not item.brand:
            frappe.throw("Brand is required for all items in Quotation")

        abbreviation = frappe.db.get_value(
            "Brand",
            item.brand,
            "abbreviation"
        )

        if not abbreviation:
            frappe.throw(
                f"Abbreviation is missing for Brand: {item.brand}"
            )

        brand_abbrs.add(abbreviation.strip().upper())

    # Deterministic order
    brand_abbr_str = "".join(sorted(brand_abbrs))

    # 4. Prefix
    prefix = f"{company_code}{year}{brand_abbr_str}{month}{day}"

    # 5. Running series (last 2 digits)
    last_name = frappe.db.sql(
        """
        SELECT name
        FROM `tabQuotation`
        WHERE name LIKE %s
        ORDER BY name DESC
        LIMIT 1
        """,
        (prefix + "%",),
        as_dict=True
    )

    if last_name:
        last_series = int(last_name[0].name[-2:])
        new_series = last_series + 1
    else:
        new_series = 1

    series_str = str(new_series).zfill(2)

    # 6. Final name
    doc.name = f"{prefix}{series_str}"

def generate_quotation_barcode(doc, method):
    """
    Generates barcode image using Quotation name
    and attaches it to the Quotation document
    """

    # Do not regenerate if already exists
    if doc.barcode:
        return

    barcode_value = doc.name  # 🔑 Use generated quotation name

    # Generate barcode image in memory
    buffer = io.BytesIO()
    Code128(barcode_value, writer=ImageWriter()).write(buffer)

    filename = f"{barcode_value}.png"

    # Save file in Frappe
    file_doc = save_file(
        fname=filename,
        content=buffer.getvalue(),
        dt="Quotation",
        dn=doc.name,
        folder="Home/Attachments",
        is_private=0
    )

    # Update quotation with barcode file
    frappe.db.set_value(
        "Quotation",
        doc.name,
        "barcode",
        file_doc.file_url
    )

@frappe.whitelist()
def make_sales_order_with_shipping_status(source_name, target_doc=None):
    """
    Create Sales Order from Quotation
    and sync Shipping Status
    """

    # Call core ERPNext function
    sales_order = core_make_sales_order(source_name, target_doc)

    # Fetch Shipping Status from Quotation
    shipping_status = frappe.db.get_value(
        "Quotation",
        source_name,
        "shipping_status"
    )

    if shipping_status:
        sales_order.shipping_status = shipping_status

    return sales_order


def compute_and_persist_quotation_profit(doc, method=None):
    """
    Server-side calculation of profit so values persist after save.
    Runs as a Quotation doc event (before_save).
    """
    # defensive: ensure items exists
    if not getattr(doc, "items", None):
        doc.quotation_total_cost = 0.0
        doc.quotation_total_selling_price = 0.0
        doc.total_profit_amount = 0.0
        doc.total_profit_percentage = 0.0
        return

    grand_total_cost = 0.0
    grand_total_selling = 0.0
    grand_total_profit = 0.0

    for item in doc.items:
        qty = flt(item.qty or 0)
        cost_rate = flt(item.valuation_rate or item.price_list_rate or 0)
        selling_rate = flt(item.rate or 0)

        total_cost = qty * cost_rate
        total_selling = qty * selling_rate

        # Clamp negative profit to zero to match client behaviour
        profit_amount = max(total_selling - total_cost, 0)

        total_profit_percentage = 0.0
        if total_cost > 0:
            total_profit_percentage = (profit_amount / total_cost) * 100

        # assign back to child row so it's saved
        item.total_cost = flt(total_cost, 2)
        item.total_selling_price = flt(total_selling, 2)
        item.profit_amount = flt(profit_amount, 2)
        item.total_profit_percentage = flt(total_profit_percentage, 2)

        grand_total_cost += flt(item.total_cost)
        grand_total_selling += flt(item.total_selling_price)
        grand_total_profit += flt(item.profit_amount)

    grand_profit_percentage = 0.0
    if grand_total_cost > 0:
        grand_profit_percentage = (grand_total_profit / grand_total_cost) * 100

    # set parent fields on the doc so they're saved
    doc.quotation_total_cost = flt(grand_total_cost, 2)
    doc.quotation_total_selling_price = flt(grand_total_selling, 2)
    doc.total_profit_amount = flt(grand_total_profit, 2)
    doc.total_profit_percentage = flt(grand_profit_percentage, 2)


def ensure_quotation_conversion_rate(doc, method=None):
    """
    Avoid blocking save when Currency Exchange rows are missing.
    Sets a safe fallback conversion_rate before standard validation.
    """
    if not getattr(doc, "currency", None) or not getattr(doc, "company", None):
        return

    company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")

    # Conversion rate must be company currency per transaction currency.
    if company_currency and doc.currency == company_currency:
        doc.conversion_rate = 1
    else:
        rate = 0
        try:
            rate = flt(get_exchange_rate(doc.currency, company_currency, transaction_date=doc.transaction_date or nowdate()))
        except Exception:
            rate = 0

        if rate and rate > 0:
            doc.conversion_rate = rate
        else:
            # Last fallback to keep save unblocked when exchange lookup fails.
            doc.conversion_rate = 1

    # Taxes and charges rows may also require per-row exchange_rate.
    # Fill missing values from document conversion_rate to avoid
    # "Row X: Exchange Rate is mandatory" during ERPNext validation.
    for tax in doc.get("taxes") or []:
        if not flt(getattr(tax, "exchange_rate", 0)):
            tax.exchange_rate = flt(doc.conversion_rate or 1)

def reset_barcode_on_amend(doc, method):
    """
    On Amend, clear barcode fields so that
    after_insert regenerates barcode for new name
    """
    if doc.amended_from:
        doc.barcode = None
        doc.barcode_preview = None
        doc._sent = "Not Sent"

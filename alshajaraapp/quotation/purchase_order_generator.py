from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import erpnext
import frappe
from erpnext.setup.utils import get_exchange_rate
from frappe import _ as frappe_translate
from frappe.utils import flt, get_link_to_form, getdate, nowdate


def _(message):
    try:
        return frappe_translate(message)
    except Exception:
        return message


@dataclass
class QuotationShortageLine:
    quotation_item: str
    item_code: str
    item_name: str
    warehouse: str
    qty: float
    stock_qty: float
    uom: str
    stock_uom: str
    conversion_factor: float
    supplier: str | None
    schedule_date: str
    rate: float
    available_qty: float


class QuotationPurchaseOrderGenerator:
    """Create Purchase Orders for Quotation shortage quantities.

    This class is called from the Quotation `on_submit` hook only. It uses the
    numeric available_stock_qty captured from the stock check state, not the
    rendered HTML stock_status field.
    ERPNext Purchase Orders have one supplier, so shortages are grouped by
    supplier.
    """

    LOGGER_NAME = "alshajaraapp.quotation_auto_po"

    def __init__(self, quotation):
        self.quotation = quotation
        self.created_purchase_orders = []
        self.skipped_messages = []
        self.warning_messages = []
        self.purchase_defaults_by_supplier = {}

    def run(self):
        if self.quotation.docstatus != 1:
            self.log_debug(
                "Skipping Quotation {0}; docstatus is {1}.".format(
                    self.quotation.name, self.quotation.docstatus
                )
            )
            return []

        self.log_debug("Starting Quotation auto PO for {0}.".format(self.quotation.name))

        if not self.quotation.get("company"):
            self.log_skip(_("Quotation {0} has no company.").format(self.quotation.name))
            self.notify_user()
            return []

        self.lock_quotation()

        existing_purchase_orders = self.get_existing_purchase_orders()
        if existing_purchase_orders:
            self.created_purchase_orders.extend(existing_purchase_orders)
            self.log_debug(
                "Skipping Quotation {0}; Purchase Order already exists: {1}".format(
                    self.quotation.name, existing_purchase_orders
                )
            )
            self.notify_user(duplicate=True)
            return self.created_purchase_orders

        shortage_lines = self.get_shortage_lines()
        self.log_debug(
            "Quotation {0}: unavailable_items_count={1}".format(
                self.quotation.name,
                len(shortage_lines),
            )
        )
        if not shortage_lines:
            self.log_debug(
                "No stock shortages detected for Quotation {0}; no Purchase Order created.".format(
                    self.quotation.name
                )
            )
            self.notify_user()
            return []

        grouped_shortage_lines = self.group_shortage_lines_by_supplier(shortage_lines)
        if not grouped_shortage_lines:
            self.notify_user()
            return []

        for supplier, supplier_lines in grouped_shortage_lines.items():
            try:
                self.log_debug(
                    "Attempting Purchase Order insert for Quotation {0}; supplier={1}; items={2}".format(
                        self.quotation.name,
                        supplier,
                        [line.item_code for line in supplier_lines],
                    )
                )
                purchase_order = self.create_purchase_order(supplier, supplier_lines)
                self.created_purchase_orders.append(purchase_order.name)
                self.log_debug(
                    "Created Purchase Order {0} for Quotation {1}; supplier={2}; items={3}".format(
                        purchase_order.name,
                        self.quotation.name,
                        supplier,
                        [line.item_code for line in supplier_lines],
                    )
                )
            except Exception:
                self.log_skip(
                    _("Could not create Purchase Order for supplier {0} from Quotation {1}.").format(
                        supplier,
                        self.quotation.name,
                    ),
                    frappe.get_traceback(),
                )

        self.notify_user()
        return self.created_purchase_orders

    def lock_quotation(self):
        frappe.db.sql(
            "select name from `tabQuotation` where name = %s for update",
            self.quotation.name,
        )

    def get_existing_purchase_orders(self):
        reference_fields = [
            fieldname
            for fieldname in ("reference_quotation", "source_quotation")
            if frappe.db.has_column("Purchase Order", fieldname)
        ]
        if not reference_fields:
            return []

        conditions = " or ".join(f"po.{fieldname} = %(quotation)s" for fieldname in reference_fields)
        rows = frappe.db.sql(
            f"""
            select po.name
            from `tabPurchase Order` po
            where po.docstatus < 2
                and ({conditions})
            order by po.creation asc
            """,
            {"quotation": self.quotation.name},
            as_dict=True,
        )
        return [row.name for row in rows]

    def get_shortage_lines(self):
        shortage_lines = []

        for row in self.quotation.get("items", []):
            item_code = row.get("item_code")
            if not item_code:
                self.log_skip(_("Quotation row {0} has no item.").format(row.idx))
                continue

            item_details = self.get_item_details(item_code)
            if not item_details:
                self.log_skip(_("Item {0} does not exist.").format(item_code))
                continue

            if not flt(item_details.get("is_stock_item")):
                self.log_debug(
                    "Quotation {0} row {1}: item={2} is not a stock item; skipped.".format(
                        self.quotation.name, row.idx, item_code
                    )
                )
                continue

            warehouse = self.get_warehouse_for_row(row, item_details)
            if not warehouse:
                self.log_skip(
                    _("No warehouse set for item {0} in Quotation {1}.").format(
                        item_code, self.quotation.name
                    )
                )
                continue

            required_qty = self.get_required_qty(row)
            if required_qty <= 0:
                continue

            available_stock_qty = self.get_available_stock_qty(row)
            shortage_qty = self.get_shortage_qty(required_qty, available_stock_qty)

            if shortage_qty <= 0:
                continue

            conversion_factor = flt(row.get("conversion_factor")) or 1
            shortage_stock_qty = shortage_qty * conversion_factor
            supplier = self.get_supplier_for_item(item_code, row)
            if not supplier:
                self.log_warning(
                    _("No supplier configured for shortage item {0}; using the Purchase Order supplier selected from other rows if available.").format(
                        item_code
                    )
                )

            self.log_debug(
                "Quotation {0}: item={1}, required_qty={2}, available_qty={3}, shortage_qty={4}, supplier={5}".format(
                    self.quotation.name,
                    item_code,
                    required_qty,
                    available_stock_qty,
                    shortage_qty,
                    supplier,
                )
            )

            schedule_date = self.quotation.get("valid_till") or self.quotation.get("transaction_date") or nowdate()
            uom = row.get("uom") or item_details.get("stock_uom")
            stock_uom = row.get("stock_uom") or item_details.get("stock_uom")
            rate = 0
            if supplier:
                currency, buying_price_list, _conversion_rate = self.get_purchase_defaults(supplier)
                rate = self.get_supplier_rate(
                    item_code,
                    supplier,
                    uom,
                    shortage_qty,
                    schedule_date,
                    currency=currency,
                    buying_price_list=buying_price_list,
                )

            shortage_lines.append(
                QuotationShortageLine(
                    quotation_item=row.name,
                    item_code=item_code,
                    item_name=row.get("item_name") or item_details.get("item_name") or item_code,
                    warehouse=warehouse,
                    qty=shortage_qty,
                    stock_qty=shortage_stock_qty,
                    uom=uom,
                    stock_uom=stock_uom,
                    conversion_factor=conversion_factor,
                    supplier=supplier,
                    schedule_date=schedule_date,
                    rate=rate,
                    available_qty=available_stock_qty,
                )
            )

        return shortage_lines

    def get_required_qty(self, row):
        return flt(row.get("qty") or 0)

    def get_required_stock_qty(self, row, conversion_factor=None):
        return self.get_required_qty(row)

    def get_available_stock_qty(self, row):
        return flt(row.get("available_stock_qty") or 0)

    def get_shortage_qty(self, required_qty, available_stock_qty):
        return max(flt(required_qty) - flt(available_stock_qty), 0)

    def get_shortage_stock_qty(self, required_stock_qty, available_stock_qty):
        return self.get_shortage_qty(required_stock_qty, available_stock_qty)

    def should_create_po_for_item(self, row):
        required_qty = self.get_required_qty(row)
        if required_qty <= 0:
            return False

        available_stock_qty = self.get_available_stock_qty(row)
        return self.get_shortage_qty(required_qty, available_stock_qty) > 0

    def has_unavailable_stock(self, quotation_items):
        return any(self.should_create_po_for_item(row) for row in quotation_items or [])

    def group_shortage_lines_by_supplier(self, shortage_lines):
        grouped = defaultdict(list)
        missing_supplier_items = []

        for line in shortage_lines:
            if line.supplier:
                grouped[line.supplier].append(line)
            else:
                missing_supplier_items.append(line.item_code)

        if missing_supplier_items:
            self.log_skip(
                _("No supplier configured for shortage item(s): {0}.").format(
                    ", ".join(missing_supplier_items)
                )
            )

        if len(grouped) > 1:
            self.log_debug(
                "Quotation {0} shortage items grouped by supplier: {1}".format(
                    self.quotation.name,
                    {supplier: [line.item_code for line in lines] for supplier, lines in grouped.items()},
                )
            )

        return grouped

    def create_purchase_order(self, supplier, lines):
        currency, buying_price_list, conversion_rate = self.get_purchase_defaults(supplier)
        schedule_date = min(getdate(line.schedule_date) for line in lines)

        purchase_order = frappe.new_doc("Purchase Order")
        purchase_order.supplier = supplier
        purchase_order.company = self.quotation.company
        purchase_order.transaction_date = self.quotation.get("transaction_date") or nowdate()
        purchase_order.schedule_date = schedule_date
        purchase_order.currency = currency
        purchase_order.conversion_rate = conversion_rate
        purchase_order.buying_price_list = buying_price_list

        if frappe.get_meta("Purchase Order").has_field("source_quotation"):
            purchase_order.source_quotation = self.quotation.name
        if frappe.get_meta("Purchase Order").has_field("reference_quotation"):
            purchase_order.reference_quotation = self.quotation.name
        if frappe.get_meta("Purchase Order").has_field("auto_created_from_quotation"):
            purchase_order.auto_created_from_quotation = 1

        for line in lines:
            purchase_order_item = {
                "item_code": line.item_code,
                "item_name": line.item_name,
                "schedule_date": line.schedule_date,
                "qty": line.qty,
                "stock_qty": line.stock_qty,
                "uom": line.uom,
                "stock_uom": line.stock_uom,
                "conversion_factor": line.conversion_factor,
                "warehouse": line.warehouse,
                "rate": line.rate,
                "price_list_rate": line.rate,
            }

            if frappe.get_meta("Purchase Order Item").has_field("source_quotation_item"):
                purchase_order_item["source_quotation_item"] = line.quotation_item
            if frappe.get_meta("Purchase Order Item").has_field("reference_quotation"):
                purchase_order_item["reference_quotation"] = self.quotation.name
            if frappe.get_meta("Purchase Order Item").has_field("reference_quotation_item"):
                purchase_order_item["reference_quotation_item"] = line.quotation_item

            purchase_order.append("items", purchase_order_item)

        purchase_order.flags.ignore_permissions = True
        purchase_order.insert(ignore_permissions=True)
        purchase_order.submit()
        return purchase_order

    def get_item_details(self, item_code):
        return frappe.db.get_value(
            "Item",
            item_code,
            ["name", "item_name", "stock_uom", "is_stock_item"],
            as_dict=True,
        )

    def get_warehouse_for_row(self, row, item_details=None):
        warehouse = row.get("warehouse") or self.quotation.get("set_warehouse")
        if warehouse:
            return warehouse

        return None

    def get_supplier_for_item(self, item_code, row=None):
        default_supplier = frappe.db.get_value(
            "Item Default",
            {"parent": item_code, "company": self.quotation.company},
            "default_supplier",
        )
        if default_supplier:
            return default_supplier

        suppliers = frappe.get_all(
            "Item Supplier",
            filters={"parent": item_code},
            pluck="supplier",
            order_by="idx asc",
        )
        suppliers = [supplier for supplier in suppliers if supplier]
        if suppliers:
            return suppliers[0]

        if row:
            for fieldname in ("supplier", "default_supplier", "preferred_supplier"):
                if row.get(fieldname):
                    return row.get(fieldname)

        return self.get_project_or_company_supplier()

    def get_project_or_company_supplier(self):
        for doctype, docname in (
            ("Project", self.quotation.get("project")),
            ("Company", self.quotation.get("company")),
        ):
            if not docname:
                continue

            meta = frappe.get_meta(doctype)
            for fieldname in ("default_supplier", "supplier"):
                if meta.has_field(fieldname):
                    supplier = frappe.db.get_value(doctype, docname, fieldname)
                    if supplier:
                        return supplier

        return None

    def get_purchase_defaults(self, supplier):
        if supplier in self.purchase_defaults_by_supplier:
            return self.purchase_defaults_by_supplier[supplier]

        company_currency = erpnext.get_company_currency(self.quotation.company)
        supplier_defaults = frappe.db.get_value(
            "Supplier",
            supplier,
            ["default_currency", "default_price_list"],
            as_dict=True,
        ) or {}

        buying_price_list = supplier_defaults.get("default_price_list") or frappe.db.get_single_value(
            "Buying Settings", "buying_price_list"
        )
        price_list_currency = None
        if buying_price_list:
            price_list_currency = frappe.db.get_value("Price List", buying_price_list, "currency")

        currency = supplier_defaults.get("default_currency") or price_list_currency or company_currency
        conversion_rate = 1
        if currency != company_currency:
            conversion_rate = get_exchange_rate(
                currency,
                company_currency,
                self.quotation.get("transaction_date") or nowdate(),
                "for_buying",
            )

        self.purchase_defaults_by_supplier[supplier] = (currency, buying_price_list, conversion_rate)
        return self.purchase_defaults_by_supplier[supplier]

    def get_supplier_rate(
        self,
        item_code,
        supplier,
        uom,
        qty,
        transaction_date,
        currency=None,
        buying_price_list=None,
    ):
        filters = {
            "item_code": item_code,
            "buying": 1,
            "supplier": supplier,
        }

        if buying_price_list:
            filters["price_list"] = buying_price_list
        if currency:
            filters["currency"] = currency

        item_prices = frappe.get_all(
            "Item Price",
            filters=filters,
            fields=["price_list_rate", "uom", "valid_from", "valid_upto"],
            order_by="valid_from desc, uom desc",
        )

        transaction_date = getdate(transaction_date)
        for item_price in item_prices:
            if item_price.uom and item_price.uom != uom:
                continue
            if item_price.valid_from and getdate(item_price.valid_from) > transaction_date:
                continue
            if item_price.valid_upto and getdate(item_price.valid_upto) < transaction_date:
                continue
            return flt(item_price.price_list_rate)

        return 0

    def log_skip(self, message, details=None):
        self.skipped_messages.append(message)
        self.log_debug(message)
        self.log_error(
            title=_("Quotation auto Purchase Order skipped"),
            message=details or message,
        )

    def log_warning(self, message):
        self.warning_messages.append(message)
        self.log_debug(message)
        self.log_error(
            title=_("Quotation auto Purchase Order warning"),
            message=message,
        )

    def log_error(self, title, message):
        try:
            frappe.log_error(title=title, message=message)
        except Exception:
            pass

    def log_debug(self, message):
        try:
            frappe.logger(self.LOGGER_NAME).info(message)
        except Exception:
            pass

    def notify_user(self, duplicate=False):
        messages = []

        if duplicate and self.created_purchase_orders:
            links = [
                get_link_to_form("Purchase Order", po_name)
                for po_name in self.created_purchase_orders
            ]
            messages.append(
                _("Purchase Order already exists for this Quotation: {0}").format(", ".join(links))
            )
        elif self.created_purchase_orders:
            links = [
                get_link_to_form("Purchase Order", po_name)
                for po_name in self.created_purchase_orders
            ]
            messages.append(_("Created Purchase Order: {0}").format(", ".join(links)))

        if self.warning_messages:
            messages.append("<br>".join(self.warning_messages))

        if self.skipped_messages:
            messages.append(
                _("Automatic Purchase Order creation skipped some work. Check Error Log: {0}").format(
                    "; ".join(self.skipped_messages)
                )
            )

        if messages:
            indicator = "orange" if self.skipped_messages or self.warning_messages else "green"
            frappe.msgprint("<br>".join(messages), indicator=indicator)

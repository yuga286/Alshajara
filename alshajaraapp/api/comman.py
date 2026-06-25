import frappe
from frappe.utils import flt
from frappe.utils import now, strip_html, now_datetime, add_days , getdate
from frappe import _
import io
from frappe.utils.file_manager import save_file
from barcode import Code128
from barcode.writer import ImageWriter

def generate_document_barcode(doc, method):
    """
    Generic barcode generator for any document.
    Uses doc.name and attaches barcode to the same doctype.
    """

    if not hasattr(doc, "barcode") or doc.barcode:
        return

    barcode_value = doc.name

    buffer = io.BytesIO()
    Code128(barcode_value, writer=ImageWriter()).write(buffer)

    filename = f"{barcode_value}.png"

    file_doc = save_file(
        fname=filename,
        content=buffer.getvalue(),
        dt=doc.doctype,
        dn=doc.name,
        folder="Home/Attachments",
        is_private=0
    )

    frappe.db.set_value(
        doc.doctype,
        doc.name,
        "barcode",
        file_doc.file_url
    )


def reset_document_barcode_on_amend(doc, method):
    """
    Reset barcode if document is created via mapping
    (PO → PI / PR etc.)
    """

    if hasattr(doc, "barcode"):
        doc.barcode = None

    if hasattr(doc, "barcode_preview"):
        doc.barcode_preview = None



import frappe

@frappe.whitelist()
def send_payment_reminder(invoice):

    doc = frappe.get_doc(
        "Sales Invoice",
        invoice
    )
    
    email_id = frappe.db.get_value(
        "Address",
        doc.customer_address,
        "email_id"
    )

    frappe.sendmail(
        recipients=[email_id],
        subject=f"Payment Reminder - {doc.name}",
        message=f"""
        Dear Customer,

        This is a reminder that payment for
        invoice {doc.name}
        is still pending.

        Outstanding Amount:
        {doc.outstanding_amount}

        Kindly process the payment.

        Regards
        Accounts Team
        """
    )

    return True




# your_app/api.py

import frappe


@frappe.whitelist()
def get_stock_status(item_code, company=None, qty=0, warehouse=None):
    if not item_code:
        return {
            "status": "orange",
            "message": "Stock status unavailable",
            "available_qty": 0,
            "required_qty": _parse_stock_quantity(qty),
        }

    required_qty = _parse_stock_quantity(qty)
    if required_qty is None or required_qty <= 0:
        return {
            "status": "orange",
            "message": "Invalid Quantity",
            "available_qty": 0,
            "required_qty": required_qty,
        }

    # Prefer explicit warehouse passed from client
    if warehouse:
        chosen_warehouse = warehouse
    else:
        chosen_warehouse = None

        if company:
            chosen_warehouse = frappe.db.get_value(
                "Item Default",
                {
                    "parent": item_code,
                    "company": company,
                },
                "default_warehouse",
            )

        if not chosen_warehouse:
            chosen_warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")

    if not chosen_warehouse:
        return {
            "status": "orange",
            "message": "No Default Warehouse",
            "available_qty": 0,
            "required_qty": required_qty,
        }
    actual_qty = frappe.db.get_value(
        "Bin",
        {
            "item_code": item_code,
            "warehouse": chosen_warehouse
        },
        "actual_qty"
    ) or 0

    available_qty = _parse_stock_quantity(actual_qty)
    if available_qty is None:
        available_qty = 0

    if available_qty >= required_qty:
        return {
            "status": "green",
            "message": f"In Stock ({available_qty})",
            "available_qty": available_qty,
            "required_qty": required_qty,
        }

    elif available_qty > 0:
        return {
            "status": "blue",
            "message": f"Partial Stock ({available_qty})",
            "available_qty": available_qty,
            "required_qty": required_qty,
        }

    return {
        "status": "red",
        "message": "Out of Stock",
        "available_qty": available_qty,
        "required_qty": required_qty,
    }


def _parse_stock_quantity(value):
    if value is None or value == "":
        return None

    try:
        return flt(float(value))
    except (TypeError, ValueError):
        return None

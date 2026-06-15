import frappe
from frappe import _

from alshajaraapp.quotation.purchase_order_generator import QuotationPurchaseOrderGenerator


def log_auto_po_debug(message, *args):
    try:
        frappe.logger("alshajaraapp.quotation_auto_po").info(message, *args)
    except Exception:
        pass


def create_purchase_orders_for_shortages(doc, method=None):
    """Quotation on_submit hook for automatic Purchase Order creation."""
    log_auto_po_debug(
        "Quotation on_submit hook called for %s with docstatus %s",
        doc.name,
        doc.docstatus,
    )

    if doc.docstatus != 1:
        log_auto_po_debug(
            "Skipping Quotation %s because docstatus is not submitted.", doc.name
        )
        return

    try:
        QuotationPurchaseOrderGenerator(doc).run()
    except Exception:
        frappe.log_error(
            title=_("Auto Purchase Order generation failed for Quotation {0}").format(doc.name),
            message=frappe.get_traceback(),
        )
        frappe.msgprint(
            _(
                "Quotation was submitted, but automatic Purchase Order generation failed. "
                "Check Error Log."
            ),
            indicator="orange",
            alert=True,
        )

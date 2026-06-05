import frappe
from frappe import _

from alshajaraapp.quotation.purchase_order_generator import (
    QuotationPurchaseOrderGenerator,
    QuotationStockShortageEvaluator,
)


def update_shortage_status(doc, method=None):
    """Persist quotation item shortage details while the quotation is saved/submitted."""
    QuotationStockShortageEvaluator(doc).update_doc_fields()


def create_purchase_orders_for_shortages(doc, method=None):
    if doc.docstatus != 1:
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

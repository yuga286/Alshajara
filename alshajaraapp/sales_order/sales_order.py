import frappe
from frappe import _

from alshajaraapp.sales_order.purchase_order_generator import AutoPurchaseOrderGenerator


def create_purchase_orders_for_shortages(doc, method=None):
    if doc.docstatus != 1:
        return

    try:
        AutoPurchaseOrderGenerator(doc).run()
    except Exception:
        frappe.log_error(
            title=_("Auto Purchase Order generation failed for {0}").format(doc.name),
            message=frappe.get_traceback(),
        )
        frappe.msgprint(
            _("Sales Order was submitted, but automatic Purchase Order generation failed. Check Error Log."),
            indicator="orange",
            alert=True,
        )

import frappe
from frappe import _
from frappe.utils import cstr

from alshajaraapp.quotation.purchase_order_generator import QuotationPurchaseOrderGenerator

APPROVE_WORKFLOW_ACTION = "Approve"
APPROVED_WORKFLOW_STATES = {"Approve", "Approved"}


def log_auto_po_debug(message, *args):
    try:
        frappe.logger("alshajaraapp.quotation_auto_po").info(message, *args)
    except Exception:
        pass


def get_selected_workflow_action():
    try:
        return cstr(frappe.form_dict.get("action")).strip()
    except Exception:
        return ""


def get_quotation_workflow_state(doc):
    workflow_state = cstr(doc.get("workflow_state")).strip()
    if workflow_state:
        return workflow_state

    try:
        workflow_state_field = frappe.db.get_value(
            "Workflow",
            {"document_type": doc.doctype, "is_active": 1},
            "workflow_state_field",
        )
    except Exception:
        workflow_state_field = None

    if workflow_state_field:
        return cstr(doc.get(workflow_state_field)).strip()

    return ""


def should_create_auto_po_for_quotation_workflow(doc):
    selected_action = get_selected_workflow_action()
    if selected_action:
        return selected_action == APPROVE_WORKFLOW_ACTION

    return get_quotation_workflow_state(doc) in APPROVED_WORKFLOW_STATES


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

    if not should_create_auto_po_for_quotation_workflow(doc):
        log_auto_po_debug(
            "Skipping Quotation %s auto PO because workflow action/state is not Approve. action=%s state=%s",
            doc.name,
            get_selected_workflow_action() or "-",
            get_quotation_workflow_state(doc) or "-",
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

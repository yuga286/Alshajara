import unittest
from unittest.mock import patch

import frappe

from alshajaraapp.quotation import quotation as quotation_hooks


class CapturingQuotationPurchaseOrderGenerator:
    calls = []

    def __init__(self, quotation):
        self.quotation = quotation
        self.__class__.calls.append(quotation)

    def run(self):
        return ["PO-TEST"]


def make_quotation(workflow_state="Approved", docstatus=1):
    return frappe._dict(
        doctype="Quotation",
        name="QTN-WORKFLOW-TEST",
        docstatus=docstatus,
        workflow_state=workflow_state,
    )


class TestQuotationAutoPurchaseOrderWorkflowGate(unittest.TestCase):
    def setUp(self):
        CapturingQuotationPurchaseOrderGenerator.calls = []

    def run_hook(self, quotation, selected_action=""):
        with (
            patch.object(
                quotation_hooks,
                "QuotationPurchaseOrderGenerator",
                CapturingQuotationPurchaseOrderGenerator,
            ),
            patch.object(
                quotation_hooks,
                "get_selected_workflow_action",
                return_value=selected_action,
            ),
        ):
            quotation_hooks.create_purchase_orders_for_shortages(quotation)

    def test_reject_workflow_action_does_not_create_purchase_order(self):
        self.run_hook(make_quotation(workflow_state="Rejected"), selected_action="Reject")

        self.assertEqual(CapturingQuotationPurchaseOrderGenerator.calls, [])

    def test_reject_action_does_not_create_purchase_order_even_if_state_is_approved(self):
        self.run_hook(make_quotation(workflow_state="Approved"), selected_action="Reject")

        self.assertEqual(CapturingQuotationPurchaseOrderGenerator.calls, [])

    def test_approve_workflow_action_creates_purchase_order(self):
        quotation = make_quotation(workflow_state="Rejected")

        self.run_hook(quotation, selected_action="Approve")

        self.assertEqual(CapturingQuotationPurchaseOrderGenerator.calls, [quotation])

    def test_approved_workflow_state_creates_purchase_order_when_action_is_unavailable(self):
        quotation = make_quotation(workflow_state="Approved")

        self.run_hook(quotation, selected_action="")

        self.assertEqual(CapturingQuotationPurchaseOrderGenerator.calls, [quotation])

    def test_rejected_workflow_state_does_not_create_purchase_order_when_action_is_unavailable(self):
        self.run_hook(make_quotation(workflow_state="Rejected"), selected_action="")

        self.assertEqual(CapturingQuotationPurchaseOrderGenerator.calls, [])

    def test_draft_quotation_does_not_create_purchase_order(self):
        self.run_hook(make_quotation(workflow_state="Approved", docstatus=0), selected_action="Approve")

        self.assertEqual(CapturingQuotationPurchaseOrderGenerator.calls, [])


if __name__ == "__main__":
    unittest.main()

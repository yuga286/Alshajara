import frappe
from erpnext.buying.doctype.supplier_quotation.supplier_quotation import (
    make_purchase_order as erp_make_purchase_order
)

@frappe.whitelist()
def make_purchase_order(source_name, target_doc=None):
    """
    Override: Create Purchase Order from Supplier Quotation
    and map quotation number & date
    """

    purchase_order = erp_make_purchase_order(source_name, target_doc)

    supplier_quotation = frappe.get_doc("Supplier Quotation", source_name)

    purchase_order.supplier_quotation_no = supplier_quotation.quotation_number
    purchase_order.supplier_quotation_date = supplier_quotation.quotation_date

    return purchase_order

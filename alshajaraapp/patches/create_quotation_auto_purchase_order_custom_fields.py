import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


APP_MODULE = "Alshajaraapp"


CUSTOM_FIELDS = {
    "Quotation": [
        {
            "fieldname": "auto_purchase_order_created",
            "fieldtype": "Check",
            "label": "Auto Purchase Order Created",
            "insert_after": "items",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "module": APP_MODULE,
        },
    ],
    "Quotation Item": [
        {
            "fieldname": "shortage_qty",
            "fieldtype": "Float",
            "label": "Shortage Qty",
            "insert_after": "stock_status",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "in_list_view": 1,
            "columns": 1,
            "module": APP_MODULE,
        },
        {
            "fieldname": "purchase_order_generated",
            "fieldtype": "Check",
            "label": "PO Generated",
            "insert_after": "shortage_qty",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "module": APP_MODULE,
        },
        {
            "fieldname": "linked_purchase_order",
            "fieldtype": "Link",
            "label": "Linked Purchase Order",
            "options": "Purchase Order",
            "insert_after": "purchase_order_generated",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "in_list_view": 1,
            "columns": 2,
            "module": APP_MODULE,
        },
    ],
    "Purchase Order": [
        {
            "fieldname": "source_quotation",
            "fieldtype": "Link",
            "label": "Source Quotation",
            "options": "Quotation",
            "insert_after": "supplier",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "module": APP_MODULE,
        },
        {
            "fieldname": "auto_created_from_quotation",
            "fieldtype": "Check",
            "label": "Auto Created from Quotation",
            "insert_after": "source_quotation",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "hidden": 1,
            "module": APP_MODULE,
        },
    ],
    "Purchase Order Item": [
        {
            "fieldname": "source_quotation_item",
            "fieldtype": "Data",
            "label": "Source Quotation Item",
            "insert_after": "sales_order_item",
            "read_only": 1,
            "no_copy": 1,
            "hidden": 1,
            "search_index": 1,
            "module": APP_MODULE,
        },
    ],
}


def execute():
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True, update=True)

    for doctype, fields in CUSTOM_FIELDS.items():
        for field in fields:
            frappe.db.set_value(
                "Custom Field",
                {"dt": doctype, "fieldname": field["fieldname"]},
                "module",
                APP_MODULE,
                update_modified=False,
            )

    frappe.clear_cache(doctype="Quotation")
    frappe.clear_cache(doctype="Quotation Item")
    frappe.clear_cache(doctype="Purchase Order")
    frappe.clear_cache(doctype="Purchase Order Item")

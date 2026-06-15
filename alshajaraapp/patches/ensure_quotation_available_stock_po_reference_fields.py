import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


APP_MODULE = "Alshajaraapp"


CUSTOM_FIELDS = {
    "Quotation Item": [
        {
            "fieldname": "available_stock_qty",
            "fieldtype": "Float",
            "label": "Available Stock Qty",
            "insert_after": "stock_status",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "module": APP_MODULE,
        },
    ],
    "Purchase Order": [
        {
            "fieldname": "reference_quotation",
            "fieldtype": "Link",
            "label": "Reference Quotation",
            "options": "Quotation",
            "insert_after": "source_quotation",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "hidden": 1,
            "in_standard_filter": 1,
            "module": APP_MODULE,
        },
    ],
    "Purchase Order Item": [
        {
            "fieldname": "reference_quotation",
            "fieldtype": "Link",
            "label": "Reference Quotation",
            "options": "Quotation",
            "insert_after": "source_quotation_item",
            "read_only": 1,
            "no_copy": 1,
            "hidden": 1,
            "module": APP_MODULE,
        },
        {
            "fieldname": "reference_quotation_item",
            "fieldtype": "Data",
            "label": "Reference Quotation Item",
            "insert_after": "reference_quotation",
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
        frappe.clear_cache(doctype=doctype)

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


APP_MODULE = "Alshajaraapp"


CUSTOM_FIELDS = {
    "Sales Order": [
        {
            "fieldname": "auto_purchase_orders_section",
            "fieldtype": "Section Break",
            "label": "Generated Purchase Orders",
            "insert_after": "items",
            "collapsible": 1,
            "module": APP_MODULE,
        },
        {
            "fieldname": "generated_purchase_orders",
            "fieldtype": "Table",
            "label": "Generated Purchase Orders",
            "options": "Sales Order Generated Purchase Order",
            "insert_after": "auto_purchase_orders_section",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "module": APP_MODULE,
        },
    ],
    "Purchase Order": [
        {
            "fieldname": "source_sales_order",
            "fieldtype": "Link",
            "label": "Source Sales Order",
            "options": "Sales Order",
            "insert_after": "supplier",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "module": APP_MODULE,
        },
        {
            "fieldname": "auto_created_from_sales_order",
            "fieldtype": "Check",
            "label": "Auto Created from Sales Order",
            "insert_after": "source_sales_order",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "hidden": 1,
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

    frappe.clear_cache(doctype="Sales Order")
    frappe.clear_cache(doctype="Purchase Order")

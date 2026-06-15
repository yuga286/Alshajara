import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "Quotation Item": [
                {
                    "fieldname": "stock_status",
                    "fieldtype": "HTML",
                    "label": "Stock Status",
                    "insert_after": "item_code",
                    "hidden": 0,
                    "read_only": 1,
                    "in_list_view": 1,
                    "module": "Alshajaraapp",
                },
                {
                    "fieldname": "available_stock_qty",
                    "fieldtype": "Float",
                    "label": "Available Stock Qty",
                    "insert_after": "stock_status",
                    "hidden": 1,
                    "read_only": 1,
                    "no_copy": 1,
                    "module": "Alshajaraapp",
                }
            ]
        },
        ignore_validate=True,
    )
    frappe.db.set_value(
        "Custom Field",
        {"dt": "Quotation Item", "fieldname": "stock_status"},
        "module",
        "Alshajaraapp",
        update_modified=True,
    )
    frappe.db.set_value(
        "Custom Field",
        {"dt": "Quotation Item", "fieldname": "available_stock_qty"},
        "module",
        "Alshajaraapp",
        update_modified=True,
    )

    set_property(
        "Quotation Item",
        "warehouse",
        "link_filters",
        '[[\"Warehouse\",\"company\",\"=\",\"eval:parent.company\"]]',
        "JSON",
    )
    set_property(
        "Quotation Item",
        "stock_status",
        "hidden",
        "0",
        "Check",
    )
    set_property(
        "Quotation Item",
        "stock_status",
        "in_list_view",
        "1",
        "Check",
    )
    set_property(
        "Quotation Item",
        "stock_status",
        "read_only",
        "1",
        "Check",
    )
    set_property(
        "Quotation Item",
        "total_profit_percentage",
        "hidden",
        "0",
        "Check",
    )
    set_property(
        "Quotation Item",
        "total_profit_percentage",
        "read_only",
        "1",
        "Check",
    )
    set_property(
        "Quotation Item",
        "total_profit_percentage",
        "in_list_view",
        "1",
        "Check",
    )
    frappe.clear_cache(doctype="Quotation")
    frappe.clear_cache(doctype="Quotation Item")


def set_property(doctype, fieldname, property_name, value, property_type, for_doctype=False):
    property_setter_name = f"{doctype}-{fieldname or 'main'}-{property_name}"
    values = {
        "doctype_or_field": "DocType" if for_doctype else "DocField",
        "doc_type": doctype,
        "field_name": fieldname,
        "property": property_name,
        "value": value,
        "property_type": property_type,
        "is_system_generated": 0,
        "module": "Alshajaraapp",
    }

    if frappe.db.exists("Property Setter", property_setter_name):
        frappe.db.set_value(
            "Property Setter",
            property_setter_name,
            values,
            update_modified=True,
        )
        return

    property_setter = frappe.get_doc({
        "doctype": "Property Setter",
        "name": property_setter_name,
        **values,
    })
    property_setter.flags.ignore_permissions = True
    property_setter.flags.validate_fields_for_doctype = False
    property_setter.insert()

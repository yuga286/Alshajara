import json

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
                    "insert_after": "warehouse",
                    "columns": 2,
                    "hidden": 0,
                    "read_only": 1,
                    "in_list_view": 1,
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
        update_modified=False,
    )

    set_property(
        "Quotation Item",
        "item_code",
        "columns",
        "3",
        "Int",
    )
    set_property(
        "Quotation Item",
        "qty",
        "columns",
        "1",
        "Int",
    )
    set_property(
        "Quotation Item",
        "rate",
        "columns",
        "2",
        "Int",
    )
    set_property(
        "Quotation Item",
        "amount",
        "columns",
        "2",
        "Int",
    )
    set_property(
        "Quotation Item",
        "warehouse",
        "in_list_view",
        "1",
        "Check",
    )
    set_property(
        "Quotation Item",
        "warehouse",
        "hidden",
        "0",
        "Check",
    )
    set_property(
        "Quotation Item",
        "warehouse",
        "read_only",
        "0",
        "Check",
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
        "warehouse",
        "columns",
        "2",
        "Int",
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
    set_property(
        "Quotation Item",
        "total_profit_percentage",
        "columns",
        "1",
        "Int",
    )
    set_property(
        "Quotation Item",
        "stock_status",
        "columns",
        "2",
        "Int",
    )
    set_property(
        "Quotation Item",
        None,
        "field_order",
        json.dumps(get_quotation_item_field_order()),
        "JSON",
        for_doctype=True,
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
            update_modified=False,
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


def get_quotation_item_field_order():
    meta = frappe.get_meta("Quotation Item", cached=False)
    field_order = [df.fieldname for df in meta.fields if df.fieldname]

    for fieldname in ("warehouse", "stock_status", "total_profit_percentage"):
        if fieldname in field_order:
            field_order.remove(fieldname)

    insert_after = "item_code"
    insert_index = field_order.index(insert_after) + 1 if insert_after in field_order else 0
    field_order[insert_index:insert_index] = ["warehouse", "stock_status"]

    insert_after = "amount"
    insert_index = field_order.index(insert_after) + 1 if insert_after in field_order else len(field_order)
    field_order.insert(insert_index, "total_profit_percentage")

    return field_order

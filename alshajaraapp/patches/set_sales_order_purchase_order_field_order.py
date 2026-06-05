import json

import frappe


SALES_ORDER_DOCTYPE = "Sales Order"
APP_MODULE = "Alshajaraapp"
PO_NO = "po_no"
PO_DATE = "po_date"
INSERT_AFTER = "delivery_date"


def execute():
    apply_sales_order_purchase_order_field_order()


def apply_sales_order_purchase_order_field_order():
    """Create Property Setters that keep customer PO fields near order details."""
    field_order = get_sales_order_purchase_order_field_order()
    if not field_order:
        return

    upsert_property_setter(
        {
            "doctype": SALES_ORDER_DOCTYPE,
            "doctype_or_field": "DocType",
            "property": "field_order",
            "property_type": "Data",
            "value": json.dumps(field_order),
        }
    )
    upsert_property_setter(
        {
            "doctype": SALES_ORDER_DOCTYPE,
            "doctype_or_field": "DocField",
            "fieldname": PO_NO,
            "property": "insert_after",
            "property_type": "Data",
            "value": INSERT_AFTER,
        }
    )
    upsert_property_setter(
        {
            "doctype": SALES_ORDER_DOCTYPE,
            "doctype_or_field": "DocField",
            "fieldname": PO_DATE,
            "property": "insert_after",
            "property_type": "Data",
            "value": PO_NO,
        }
    )

    frappe.clear_cache(doctype=SALES_ORDER_DOCTYPE)


def get_sales_order_purchase_order_field_order():
    if not frappe.db.exists("DocType", SALES_ORDER_DOCTYPE):
        return []

    meta = frappe.get_meta(SALES_ORDER_DOCTYPE, cached=False)
    field_order = [df.fieldname for df in meta.fields if df.fieldname]

    required_fields = (INSERT_AFTER, PO_NO, PO_DATE)
    missing_fields = [fieldname for fieldname in required_fields if fieldname not in field_order]
    if missing_fields:
        frappe.log_error(
            title="Sales Order PO field order skipped",
            message=f"Missing Sales Order field(s): {', '.join(missing_fields)}",
        )
        return []

    field_order = [fieldname for fieldname in field_order if fieldname not in (PO_NO, PO_DATE)]
    insert_index = field_order.index(INSERT_AFTER) + 1
    field_order[insert_index:insert_index] = [PO_NO, PO_DATE]
    return field_order


def upsert_property_setter(args):
    frappe.make_property_setter(
        args,
        validate_fields_for_doctype=False,
        is_system_generated=False,
        module=APP_MODULE,
    )

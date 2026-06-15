import frappe


OBSOLETE_CUSTOM_FIELDS = {
    "Quotation": [
        "auto_purchase_order_created",
    ],
    "Quotation Item": [
        "shortage_qty",
        "purchase_order_generated",
        "linked_purchase_order",
    ],
}


def execute():
    """Remove fields from the earlier Quotation PO automation implementation."""
    for doctype, fieldnames in OBSOLETE_CUSTOM_FIELDS.items():
        for fieldname in fieldnames:
            custom_field_name = frappe.db.get_value(
                "Custom Field",
                {"dt": doctype, "fieldname": fieldname},
                "name",
            )
            if custom_field_name:
                frappe.delete_doc(
                    "Custom Field",
                    custom_field_name,
                    ignore_permissions=True,
                    force=True,
                )

        frappe.clear_cache(doctype=doctype)

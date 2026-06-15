import frappe


OBSOLETE_PROPERTY_SETTERS = (
    "Quotation Item-main-field_order",
    "Quotation Item-item_code-columns",
    "Quotation Item-qty-columns",
    "Quotation Item-rate-columns",
    "Quotation Item-amount-columns",
    "Quotation Item-warehouse-in_list_view",
    "Quotation Item-warehouse-columns",
    "Quotation Item-warehouse-hidden",
    "Quotation Item-warehouse-read_only",
    "Quotation Item-stock_status-columns",
    "Quotation Item-total_profit_percentage-columns",
)

CUSTOM_FIELD_COLUMNS_TO_CLEAR = (
    ("Opportunity Item", "stock_status"),
    ("Opportunity Item", "warehouse"),
    ("Quotation Item", "stock_status"),
)


def execute():
    """Remove child-table layout overrides so Frappe grid customization works normally."""
    for property_setter in OBSOLETE_PROPERTY_SETTERS:
        if frappe.db.exists("Property Setter", property_setter):
            frappe.delete_doc(
                "Property Setter",
                property_setter,
                ignore_permissions=True,
                force=True,
            )

    for doctype, fieldname in CUSTOM_FIELD_COLUMNS_TO_CLEAR:
        custom_field = frappe.db.get_value(
            "Custom Field",
            {"dt": doctype, "fieldname": fieldname},
            "name",
        )
        if custom_field:
            frappe.db.set_value(
                "Custom Field",
                custom_field,
                "columns",
                0,
                update_modified=False,
            )

    frappe.clear_cache(doctype="Opportunity Item")
    frappe.clear_cache(doctype="Quotation Item")

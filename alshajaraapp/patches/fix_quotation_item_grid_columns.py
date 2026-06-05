import json

import frappe

from alshajaraapp.patches.ensure_quotation_stock_status_fields import execute as ensure_fields


def execute():
    ensure_fields()
    clear_quotation_item_grid_user_settings()


def clear_quotation_item_grid_user_settings():
    if not frappe.db.table_exists("__UserSettings"):
        return

    rows = frappe.db.sql(
        "select user, data from `__UserSettings` where doctype = %s",
        "Quotation",
        as_dict=True,
    )

    for row in rows:
        if not row.data:
            continue

        try:
            data = json.loads(row.data)
        except ValueError:
            continue

        grid_view = data.get("GridView")
        if not isinstance(grid_view, dict) or "Quotation Item" not in grid_view:
            continue

        grid_view.pop("Quotation Item", None)
        if not grid_view:
            data.pop("GridView", None)

        frappe.db.sql(
            "update `__UserSettings` set data = %s where user = %s and doctype = %s",
            (json.dumps(data), row.user, "Quotation"),
        )

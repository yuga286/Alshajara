from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def _clean_note(note: str | None) -> str:
    return (note or "").strip()


def _get_price_list_details(price_list: str) -> frappe._dict:
    if not price_list:
        frappe.throw(_("Price List is required."))

    details = frappe.db.get_value(
        "Price List",
        {"name": price_list, "enabled": 1},
        ["currency", "buying", "selling"],
        as_dict=True,
    )
    if not details:
        frappe.throw(_("Price List {0} does not exist or is disabled.").format(frappe.bold(price_list)))

    return frappe._dict(details)


def _get_item_details(item_code: str) -> frappe._dict:
    if not item_code:
        frappe.throw(_("Item is required."))

    details = frappe.db.get_value(
        "Item",
        {"name": item_code, "has_variants": 0},
        ["item_name", "stock_uom"],
        as_dict=True,
    )
    if not details:
        frappe.throw(_("Item {0} does not exist or is a template item.").format(frappe.bold(item_code)))

    return frappe._dict(details)


def get_default_item_price(price_list: str, item_code: str, uom: str | None = None):
    """Return the generic Item Price row edited by the shared popup.

    Customer, supplier, batch, and date-specific Item Price records are not
    edited by this popup because those are separate ERPNext price definitions.
    """

    candidates = frappe.get_all(
        "Item Price",
        filters={"price_list": price_list, "item_code": item_code},
        fields=[
            "name",
            "uom",
            "price_list_rate",
            "currency",
            "note",
            "customer",
            "supplier",
            "batch_no",
            "valid_from",
            "valid_upto",
        ],
        order_by="modified desc",
        limit=50,
    )

    for candidate in candidates:
        if uom and candidate.get("uom") != uom:
            continue
        if any(candidate.get(fieldname) for fieldname in ("customer", "supplier", "batch_no")):
            continue
        if candidate.get("valid_from") or candidate.get("valid_upto"):
            continue
        return frappe._dict(candidate)

    return None


@frappe.whitelist()
def get_item_price_popup_context(
    price_list: str | None = None,
    item_code: str | None = None,
    uom: str | None = None,
):
    context = frappe._dict()

    if price_list:
        price_list_details = _get_price_list_details(price_list)
        context.update(
            price_list=price_list,
            currency=price_list_details.currency,
            buying=price_list_details.buying,
            selling=price_list_details.selling,
        )

    if item_code:
        item_details = _get_item_details(item_code)
        context.update(
            item_code=item_code,
            item_name=item_details.item_name,
            uom=uom or item_details.stock_uom,
        )

    if price_list and item_code:
        resolved_uom = context.get("uom")
        item_price = get_default_item_price(price_list, item_code, resolved_uom)
        context.update(
            item_price=item_price.name if item_price else None,
            current_rate=flt(item_price.price_list_rate) if item_price else None,
            price_list_rate=flt(item_price.price_list_rate) if item_price else None,
            note=item_price.note if item_price else "",
        )

    return context


@frappe.whitelist()
def save_item_price_from_popup(
    price_list: str,
    item_code: str,
    price_list_rate,
    uom: str | None = None,
    note: str | None = None,
    item_price: str | None = None,
):
    _get_price_list_details(price_list)
    item_details = _get_item_details(item_code)
    resolved_uom = uom or item_details.stock_uom

    if item_price:
        item_price_doc = frappe.get_doc("Item Price", item_price)
        item_price_doc.check_permission("write")
    else:
        existing = get_default_item_price(price_list, item_code, resolved_uom)
        if existing:
            item_price_doc = frappe.get_doc("Item Price", existing.name)
            item_price_doc.check_permission("write")
        else:
            if not frappe.has_permission("Item Price", "create"):
                frappe.throw(_("Not permitted to create Item Price."), frappe.PermissionError)
            item_price_doc = frappe.new_doc("Item Price")
            item_price_doc.item_code = item_code
            item_price_doc.price_list = price_list
            item_price_doc.uom = resolved_uom

    item_price_doc.price_list_rate = flt(price_list_rate)
    item_price_doc.uom = resolved_uom
    item_price_doc.note = _clean_note(note)

    if item_price_doc.is_new():
        item_price_doc.insert()
    else:
        item_price_doc.save()

    return frappe._dict(
        item_price=item_price_doc.name,
        item_code=item_price_doc.item_code,
        price_list=item_price_doc.price_list,
        uom=item_price_doc.uom,
        price_list_rate=flt(item_price_doc.price_list_rate),
        currency=item_price_doc.currency,
        note=item_price_doc.note,
    )


# Compatibility aliases for any stale client bundle from the earlier implementation.
get_price_adjustment_context = get_item_price_popup_context
save_price_adjustment = save_item_price_from_popup

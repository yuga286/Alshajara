from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import erpnext
import frappe
from erpnext.setup.utils import get_exchange_rate
from frappe import _
from frappe.utils import flt, getdate, nowdate


@dataclass
class ShortageLine:
    sales_order_item: str
    item_code: str
    item_name: str
    warehouse: str
    qty: float
    stock_qty: float
    uom: str
    stock_uom: str
    conversion_factor: float
    supplier: str
    schedule_date: str
    rate: float


class AutoPurchaseOrderGenerator:
    def __init__(self, sales_order):
        self.sales_order = sales_order
        self.created_purchase_orders = []
        self.skipped_messages = []
        self.purchase_defaults_by_supplier = {}

    def run(self):
        if self.sales_order.docstatus != 1:
            return []

        if not self.sales_order.get("company"):
            self.log_skip(_("Sales Order {0} has no company.").format(self.sales_order.name))
            self.notify_user()
            return []

        existing_qty_by_so_item = self.get_existing_po_qty_by_so_item()
        shortage_lines = self.get_shortage_lines(existing_qty_by_so_item)

        if shortage_lines:
            for supplier, lines in self.group_by_supplier(shortage_lines).items():
                try:
                    purchase_order = self.create_purchase_order(supplier, lines)
                    self.created_purchase_orders.append(purchase_order.name)
                except Exception:
                    self.log_skip(
                        _("Could not create Purchase Order for supplier {0} from Sales Order {1}.").format(
                            supplier, self.sales_order.name
                        ),
                        frappe.get_traceback(),
                    )

        self.sync_tracking_table()
        self.notify_user()
        return self.created_purchase_orders

    def get_shortage_lines(self, existing_qty_by_so_item):
        shortage_lines = []
        available_qty_by_item_warehouse = {}

        for row in self.sales_order.get("items", []):
            item_code = row.get("item_code")
            if not item_code:
                self.log_skip(_("Sales Order row {0} has no item.").format(row.idx))
                continue

            item_details = self.get_item_details(item_code)
            if not item_details:
                self.log_skip(_("Item {0} does not exist.").format(item_code))
                continue

            if not flt(item_details.get("is_stock_item")):
                continue

            warehouse = row.get("warehouse") or self.sales_order.get("set_warehouse")
            if not warehouse:
                self.log_skip(
                    _("No warehouse set for item {0} in Sales Order {1}.").format(
                        item_code, self.sales_order.name
                    )
                )
                continue

            conversion_factor = flt(row.get("conversion_factor")) or 1
            ordered_stock_qty = flt(row.get("stock_qty")) or (flt(row.get("qty")) * conversion_factor)
            availability_key = (item_code, warehouse)

            if availability_key not in available_qty_by_item_warehouse:
                available_qty_by_item_warehouse[availability_key] = self.get_available_qty(item_code, warehouse)

            available_qty = available_qty_by_item_warehouse[availability_key]
            shortage_stock_qty = ordered_stock_qty - available_qty
            available_qty_by_item_warehouse[availability_key] = max(available_qty - ordered_stock_qty, 0)

            if shortage_stock_qty <= 0:
                continue

            shortage_qty = shortage_stock_qty / conversion_factor
            already_ordered_qty = flt(existing_qty_by_so_item.get(row.name))
            shortage_qty = shortage_qty - already_ordered_qty
            if shortage_qty <= 0:
                continue

            supplier = self.get_supplier_for_item(item_code)
            if not supplier:
                self.log_skip(
                    _("No default or unambiguous supplier configured for item {0}.").format(item_code)
                )
                continue

            schedule_date = row.get("delivery_date") or self.sales_order.get("delivery_date") or nowdate()
            uom = row.get("uom") or item_details.get("stock_uom")
            stock_uom = row.get("stock_uom") or item_details.get("stock_uom")
            currency, buying_price_list, _conversion_rate = self.get_purchase_defaults(supplier)

            shortage_lines.append(
                ShortageLine(
                    sales_order_item=row.name,
                    item_code=item_code,
                    item_name=row.get("item_name") or item_details.get("item_name"),
                    warehouse=warehouse,
                    qty=shortage_qty,
                    stock_qty=shortage_qty * conversion_factor,
                    uom=uom,
                    stock_uom=stock_uom,
                    conversion_factor=conversion_factor,
                    supplier=supplier,
                    schedule_date=schedule_date,
                    rate=self.get_supplier_rate(
                        item_code,
                        supplier,
                        uom,
                        shortage_qty,
                        schedule_date,
                        currency=currency,
                        buying_price_list=buying_price_list,
                    ),
                )
            )

        return shortage_lines

    def group_by_supplier(self, shortage_lines):
        grouped = defaultdict(list)
        for line in shortage_lines:
            grouped[line.supplier].append(line)
        return grouped

    def create_purchase_order(self, supplier, lines):
        currency, buying_price_list, conversion_rate = self.get_purchase_defaults(supplier)
        schedule_date = min(getdate(line.schedule_date) for line in lines)

        purchase_order = frappe.new_doc("Purchase Order")
        purchase_order.supplier = supplier
        purchase_order.company = self.sales_order.company
        purchase_order.transaction_date = self.sales_order.get("transaction_date") or nowdate()
        purchase_order.schedule_date = schedule_date
        purchase_order.currency = currency
        purchase_order.conversion_rate = conversion_rate
        purchase_order.buying_price_list = buying_price_list
        purchase_order.source_sales_order = self.sales_order.name
        purchase_order.auto_created_from_sales_order = 1

        for line in lines:
            purchase_order.append(
                "items",
                {
                    "item_code": line.item_code,
                    "item_name": line.item_name,
                    "schedule_date": line.schedule_date,
                    "qty": line.qty,
                    "stock_qty": line.stock_qty,
                    "uom": line.uom,
                    "stock_uom": line.stock_uom,
                    "conversion_factor": line.conversion_factor,
                    "warehouse": line.warehouse,
                    "rate": line.rate,
                    "price_list_rate": line.rate,
                    "sales_order": self.sales_order.name,
                    "sales_order_item": line.sales_order_item,
                },
            )

        purchase_order.insert(ignore_permissions=True)
        return purchase_order

    def get_item_details(self, item_code):
        return frappe.db.get_value(
            "Item",
            item_code,
            ["name", "item_name", "stock_uom", "is_stock_item"],
            as_dict=True,
        )

    def get_available_qty(self, item_code, warehouse):
        return flt(
            frappe.db.get_value(
                "Bin",
                {"item_code": item_code, "warehouse": warehouse},
                "actual_qty",
            )
        )

    def get_supplier_for_item(self, item_code):
        default_supplier = frappe.db.get_value(
            "Item Default",
            {"parent": item_code, "company": self.sales_order.company},
            "default_supplier",
        )
        if default_supplier:
            return default_supplier

        suppliers = frappe.get_all(
            "Item Supplier",
            filters={"parent": item_code},
            pluck="supplier",
            order_by="idx",
        )
        suppliers = [supplier for supplier in suppliers if supplier]

        if len(suppliers) == 1:
            return suppliers[0]

        return None

    def get_supplier_rate(
        self,
        item_code,
        supplier,
        uom,
        qty,
        transaction_date,
        currency=None,
        buying_price_list=None,
    ):
        filters = {
            "item_code": item_code,
            "buying": 1,
            "supplier": supplier,
        }

        if buying_price_list:
            filters["price_list"] = buying_price_list
        if currency:
            filters["currency"] = currency

        item_prices = frappe.get_all(
            "Item Price",
            filters=filters,
            fields=["price_list_rate", "uom", "valid_from", "valid_upto"],
            order_by="valid_from desc, uom desc",
        )

        transaction_date = getdate(transaction_date)
        for item_price in item_prices:
            if item_price.uom and item_price.uom != uom:
                continue
            if item_price.valid_from and getdate(item_price.valid_from) > transaction_date:
                continue
            if item_price.valid_upto and getdate(item_price.valid_upto) < transaction_date:
                continue
            return flt(item_price.price_list_rate)

        return 0

    def get_purchase_defaults(self, supplier):
        if supplier in self.purchase_defaults_by_supplier:
            return self.purchase_defaults_by_supplier[supplier]

        company_currency = erpnext.get_company_currency(self.sales_order.company)
        supplier_defaults = frappe.db.get_value(
            "Supplier",
            supplier,
            ["default_currency", "default_price_list"],
            as_dict=True,
        ) or {}

        buying_price_list = self.get_buying_price_list(supplier, supplier_defaults)
        price_list_currency = None
        if buying_price_list:
            price_list_currency = frappe.db.get_value("Price List", buying_price_list, "currency")

        currency = supplier_defaults.get("default_currency") or price_list_currency or company_currency
        conversion_rate = 1
        if currency != company_currency:
            conversion_rate = get_exchange_rate(
                currency,
                company_currency,
                self.sales_order.get("transaction_date") or nowdate(),
                "for_buying",
            )

        self.purchase_defaults_by_supplier[supplier] = (currency, buying_price_list, conversion_rate)
        return self.purchase_defaults_by_supplier[supplier]

    def get_buying_price_list(self, supplier, supplier_defaults=None):
        supplier_defaults = supplier_defaults or frappe.db.get_value(
            "Supplier", supplier, ["default_price_list"], as_dict=True
        ) or {}
        return supplier_defaults.get("default_price_list") or frappe.db.get_single_value(
            "Buying Settings", "buying_price_list"
        )

    def get_existing_po_qty_by_so_item(self):
        if not frappe.db.has_column("Purchase Order", "source_sales_order"):
            return {}

        rows = frappe.db.sql(
            """
            select
                poi.sales_order_item,
                sum(poi.qty) as qty
            from `tabPurchase Order Item` poi
            inner join `tabPurchase Order` po on po.name = poi.parent
            where po.docstatus < 2
                and poi.sales_order = %(sales_order)s
                and po.source_sales_order = %(sales_order)s
                and ifnull(poi.sales_order_item, '') != ''
            group by poi.sales_order_item
            """,
            {"sales_order": self.sales_order.name},
            as_dict=True,
        )
        return {row.sales_order_item: flt(row.qty) for row in rows}

    def sync_tracking_table(self):
        if not frappe.get_meta("Sales Order").has_field("generated_purchase_orders"):
            return

        rows = self.get_generated_purchase_order_rows()
        sales_order = frappe.get_doc("Sales Order", self.sales_order.name)
        sales_order.flags.ignore_validate_update_after_submit = True
        sales_order.set("generated_purchase_orders", [])

        for row in rows:
            sales_order.append("generated_purchase_orders", row)

        sales_order.save(ignore_permissions=True)

    def get_generated_purchase_order_rows(self):
        if not frappe.db.has_column("Purchase Order", "source_sales_order"):
            return []

        return frappe.db.sql(
            """
            select
                po.supplier,
                po.name as purchase_order,
                poi.item_code,
                poi.item_name,
                poi.warehouse,
                poi.qty as shortage_qty,
                poi.sales_order_item
            from `tabPurchase Order` po
            inner join `tabPurchase Order Item` poi on poi.parent = po.name
            where po.docstatus < 2
                and po.source_sales_order = %(sales_order)s
            order by po.creation, poi.idx
            """,
            {"sales_order": self.sales_order.name},
            as_dict=True,
        )

    def log_skip(self, message, details=None):
        self.skipped_messages.append(message)
        frappe.log_error(
            title=_("Auto Purchase Order skipped item"),
            message=details or message,
        )

    def notify_user(self):
        messages = []
        if self.created_purchase_orders:
            links = [
                frappe.utils.get_link_to_form("Purchase Order", po_name)
                for po_name in self.created_purchase_orders
            ]
            messages.append(_("Created Purchase Order(s): {0}").format(", ".join(links)))

        if self.skipped_messages:
            messages.append(
                _("Some shortage items were skipped. Check Error Log for details: {0}").format(
                    "; ".join(self.skipped_messages)
                )
            )

        if messages:
            frappe.msgprint("<br>".join(messages), indicator="orange" if self.skipped_messages else "green")

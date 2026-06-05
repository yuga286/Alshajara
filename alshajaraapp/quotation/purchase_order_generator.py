from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import erpnext
import frappe
from erpnext.setup.utils import get_exchange_rate
from frappe import _
from frappe.utils import flt, get_link_to_form, getdate, nowdate


@dataclass
class QuotationShortageLine:
    quotation_item: str
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


class QuotationStockShortageEvaluator:
    def __init__(self, quotation):
        self.quotation = quotation
        self.skipped_messages = []

    def update_doc_fields(self):
        self.get_shortage_lines(update_doc_fields=True)
        return self.quotation

    def get_shortage_lines(self, existing_qty_by_quotation_item=None, update_doc_fields=False):
        existing_qty_by_quotation_item = existing_qty_by_quotation_item or {}
        shortage_lines = []
        available_qty_by_item_warehouse = {}

        for row in self.quotation.get("items", []):
            if update_doc_fields:
                self.reset_shortage_fields_for_row(row)

            item_code = row.get("item_code")
            if not item_code:
                self.log_skip(_("Quotation row {0} has no item.").format(row.idx))
                continue

            item_details = self.get_item_details(item_code)
            if not item_details:
                self.log_skip(_("Item {0} does not exist.").format(item_code))
                continue

            if not flt(item_details.get("is_stock_item")):
                continue

            warehouse = row.get("warehouse")
            if not warehouse:
                self.log_skip(
                    _("No warehouse set for item {0} in Quotation {1}.").format(
                        item_code, self.quotation.name
                    )
                )
                continue

            conversion_factor = flt(row.get("conversion_factor")) or 1
            quoted_stock_qty = flt(row.get("stock_qty")) or (flt(row.get("qty")) * conversion_factor)
            availability_key = (item_code, warehouse)

            if availability_key not in available_qty_by_item_warehouse:
                available_qty_by_item_warehouse[availability_key] = self.get_available_qty(
                    item_code, warehouse
                )

            available_qty = available_qty_by_item_warehouse[availability_key]
            shortage_stock_qty = max(quoted_stock_qty - available_qty, 0)
            available_qty_by_item_warehouse[availability_key] = max(available_qty - quoted_stock_qty, 0)
            shortage_qty = shortage_stock_qty / conversion_factor if conversion_factor else 0

            if update_doc_fields:
                row.shortage_qty = flt(shortage_qty)

            if shortage_qty <= 0:
                continue

            existing_qty = flt(existing_qty_by_quotation_item.get(row.name))
            remaining_qty = shortage_qty - existing_qty
            if remaining_qty <= 0:
                continue

            supplier = self.get_supplier_for_item(item_code)
            if not supplier:
                self.log_skip(
                    _("No default or prioritized supplier configured for item {0}.").format(
                        item_code
                    )
                )
                continue

            schedule_date = self.quotation.get("valid_till") or self.quotation.get("transaction_date") or nowdate()
            uom = row.get("uom") or item_details.get("stock_uom")
            stock_uom = row.get("stock_uom") or item_details.get("stock_uom")
            currency, buying_price_list, _conversion_rate = self.get_purchase_defaults(supplier)

            shortage_lines.append(
                QuotationShortageLine(
                    quotation_item=row.name,
                    item_code=item_code,
                    item_name=row.get("item_name") or item_details.get("item_name"),
                    warehouse=warehouse,
                    qty=remaining_qty,
                    stock_qty=remaining_qty * conversion_factor,
                    uom=uom,
                    stock_uom=stock_uom,
                    conversion_factor=conversion_factor,
                    supplier=supplier,
                    schedule_date=schedule_date,
                    rate=self.get_supplier_rate(
                        item_code,
                        supplier,
                        uom,
                        remaining_qty,
                        schedule_date,
                        currency=currency,
                        buying_price_list=buying_price_list,
                    ),
                )
            )

        return shortage_lines

    def reset_shortage_fields_for_row(self, row):
        row.shortage_qty = 0
        linked_purchase_order = row.get("linked_purchase_order")
        if not linked_purchase_order or not self.is_active_purchase_order(linked_purchase_order):
            row.purchase_order_generated = 0
            row.linked_purchase_order = None

    def is_active_purchase_order(self, purchase_order):
        if not purchase_order:
            return False

        docstatus = frappe.db.get_value("Purchase Order", purchase_order, "docstatus")
        return docstatus is not None and flt(docstatus) < 2

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
            {"parent": item_code, "company": self.quotation.company},
            "default_supplier",
        )
        if default_supplier:
            return default_supplier

        suppliers = frappe.get_all(
            "Item Supplier",
            filters={"parent": item_code},
            pluck="supplier",
            order_by="idx asc",
        )
        suppliers = [supplier for supplier in suppliers if supplier]
        return suppliers[0] if suppliers else None

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
        company_currency = erpnext.get_company_currency(self.quotation.company)
        supplier_defaults = frappe.db.get_value(
            "Supplier",
            supplier,
            ["default_currency", "default_price_list"],
            as_dict=True,
        ) or {}

        buying_price_list = supplier_defaults.get("default_price_list") or frappe.db.get_single_value(
            "Buying Settings", "buying_price_list"
        )
        price_list_currency = None
        if buying_price_list:
            price_list_currency = frappe.db.get_value("Price List", buying_price_list, "currency")

        currency = supplier_defaults.get("default_currency") or price_list_currency or company_currency
        conversion_rate = 1
        if currency != company_currency:
            conversion_rate = get_exchange_rate(
                currency,
                company_currency,
                self.quotation.get("transaction_date") or nowdate(),
                "for_buying",
            )

        return currency, buying_price_list, conversion_rate

    def log_skip(self, message, details=None):
        self.skipped_messages.append(message)
        frappe.log_error(
            title=_("Quotation auto Purchase Order skipped item"),
            message=details or message,
        )


class QuotationPurchaseOrderGenerator(QuotationStockShortageEvaluator):
    def __init__(self, quotation):
        super().__init__(quotation)
        self.created_purchase_orders = []
        self.purchase_defaults_by_supplier = {}

    def run(self):
        if self.quotation.docstatus != 1:
            return []

        if not self.quotation.get("company"):
            self.log_skip(_("Quotation {0} has no company.").format(self.quotation.name))
            self.notify_user()
            return []

        self.lock_quotation()
        existing_qty_by_quotation_item = self.get_existing_po_qty_by_quotation_item()
        shortage_lines = self.get_shortage_lines(existing_qty_by_quotation_item)

        if shortage_lines:
            for supplier, lines in self.group_by_supplier(shortage_lines).items():
                try:
                    purchase_order = self.create_purchase_order(supplier, lines)
                    self.created_purchase_orders.append(purchase_order.name)
                    self.mark_quotation_items_as_generated(lines, purchase_order.name)
                except Exception:
                    self.log_skip(
                        _("Could not create Purchase Order for supplier {0} from Quotation {1}.").format(
                            supplier, self.quotation.name
                        ),
                        frappe.get_traceback(),
                    )

        self.update_parent_generation_flag()
        self.notify_user()
        return self.created_purchase_orders

    def lock_quotation(self):
        if not self.quotation.name:
            return

        frappe.db.sql(
            "select name from `tabQuotation` where name = %s for update",
            self.quotation.name,
        )

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
        purchase_order.company = self.quotation.company
        purchase_order.transaction_date = self.quotation.get("transaction_date") or nowdate()
        purchase_order.schedule_date = schedule_date
        purchase_order.currency = currency
        purchase_order.conversion_rate = conversion_rate
        purchase_order.buying_price_list = buying_price_list
        purchase_order.source_quotation = self.quotation.name
        purchase_order.auto_created_from_quotation = 1

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
                    "source_quotation_item": line.quotation_item,
                },
            )

        purchase_order.insert(ignore_permissions=True)
        return purchase_order

    def get_purchase_defaults(self, supplier):
        if supplier in self.purchase_defaults_by_supplier:
            return self.purchase_defaults_by_supplier[supplier]

        self.purchase_defaults_by_supplier[supplier] = super().get_purchase_defaults(supplier)
        return self.purchase_defaults_by_supplier[supplier]

    def get_existing_po_qty_by_quotation_item(self):
        if not frappe.db.has_column("Purchase Order", "source_quotation"):
            return {}

        if not frappe.db.has_column("Purchase Order Item", "source_quotation_item"):
            return {}

        rows = frappe.db.sql(
            """
            select
                poi.source_quotation_item,
                sum(poi.qty) as qty
            from `tabPurchase Order Item` poi
            inner join `tabPurchase Order` po on po.name = poi.parent
            where po.docstatus < 2
                and po.source_quotation = %(quotation)s
                and ifnull(poi.source_quotation_item, '') != ''
            group by poi.source_quotation_item
            """,
            {"quotation": self.quotation.name},
            as_dict=True,
        )
        return {row.source_quotation_item: flt(row.qty) for row in rows}

    def mark_quotation_items_as_generated(self, lines, purchase_order_name):
        for line in lines:
            frappe.db.set_value(
                "Quotation Item",
                line.quotation_item,
                {
                    "purchase_order_generated": 1,
                    "linked_purchase_order": purchase_order_name,
                    "shortage_qty": line.qty,
                },
                update_modified=False,
            )

    def update_parent_generation_flag(self):
        generated = 1 if self.has_generated_purchase_orders() else 0
        frappe.db.set_value(
            "Quotation",
            self.quotation.name,
            "auto_purchase_order_created",
            generated,
            update_modified=False,
        )

    def has_generated_purchase_orders(self):
        if not frappe.db.has_column("Purchase Order", "source_quotation"):
            return False

        return bool(
            frappe.db.exists(
                "Purchase Order",
                {
                    "source_quotation": self.quotation.name,
                    "docstatus": ["<", 2],
                },
            )
        )

    def notify_user(self):
        messages = []
        if self.created_purchase_orders:
            links = [
                get_link_to_form("Purchase Order", po_name)
                for po_name in self.created_purchase_orders
            ]
            messages.append(_("Created Purchase Order(s): {0}").format(", ".join(links)))

        if self.skipped_messages:
            messages.append(
                _("Some quotation shortage items were skipped. Check Error Log for details: {0}").format(
                    "; ".join(self.skipped_messages)
                )
            )

        if messages:
            frappe.msgprint("<br>".join(messages), indicator="orange" if self.skipped_messages else "green")

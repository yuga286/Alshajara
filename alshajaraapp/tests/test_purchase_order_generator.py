import unittest

import frappe

from alshajaraapp.sales_order.purchase_order_generator import AutoPurchaseOrderGenerator


class CapturingPurchaseOrderGenerator(AutoPurchaseOrderGenerator):
    def __init__(self, sales_order, available_qty, suppliers, existing_qty=None):
        super().__init__(sales_order)
        self.available_qty = available_qty
        self.suppliers = suppliers
        self.existing_qty = existing_qty or {}
        self.created = []

    def get_item_details(self, item_code):
        return frappe._dict(
            name=item_code,
            item_name=f"{item_code} Name",
            stock_uom="Nos",
            is_stock_item=1,
        )

    def get_available_qty(self, item_code, warehouse):
        return self.available_qty.get((item_code, warehouse), 0)

    def get_supplier_for_item(self, item_code):
        return self.suppliers.get(item_code)

    def get_purchase_defaults(self, supplier):
        return "KWD", "Standard Buying", 1

    def get_supplier_rate(self, item_code, supplier, uom, qty, transaction_date, **kwargs):
        return 100

    def get_existing_po_qty_by_so_item(self):
        return self.existing_qty

    def create_purchase_order(self, supplier, lines):
        self.created.append((supplier, lines))
        return frappe._dict(name=f"PO-{len(self.created)}")

    def sync_tracking_table(self):
        return None

    def notify_user(self):
        return None

    def log_skip(self, message, details=None):
        self.skipped_messages.append(message)


def make_sales_order(*items):
    return frappe._dict(
        name="SO-TEST",
        docstatus=1,
        company="_Test Company",
        transaction_date="2026-06-04",
        delivery_date="2026-06-10",
        items=list(items),
    )


def make_item(name, item_code, qty, warehouse="Stores - _TC"):
    return frappe._dict(
        name=name,
        idx=1,
        item_code=item_code,
        item_name=f"{item_code} Name",
        qty=qty,
        stock_qty=qty,
        uom="Nos",
        stock_uom="Nos",
        conversion_factor=1,
        warehouse=warehouse,
        delivery_date="2026-06-10",
    )


class TestAutoPurchaseOrderGenerator(unittest.TestCase):
    def test_zero_stock_creates_po_for_full_qty(self):
        sales_order = make_sales_order(make_item("SOI-1", "ITEM-1", 10))
        generator = CapturingPurchaseOrderGenerator(
            sales_order,
            available_qty={("ITEM-1", "Stores - _TC"): 0},
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(generator.created[0][0], "Supplier A")
        self.assertEqual(generator.created[0][1][0].qty, 10)

    def test_partial_stock_creates_po_for_shortage_qty(self):
        sales_order = make_sales_order(make_item("SOI-1", "ITEM-1", 10))
        generator = CapturingPurchaseOrderGenerator(
            sales_order,
            available_qty={("ITEM-1", "Stores - _TC"): 4},
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(generator.created[0][1][0].qty, 6)

    def test_sufficient_stock_creates_no_po(self):
        sales_order = make_sales_order(make_item("SOI-1", "ITEM-1", 10))
        generator = CapturingPurchaseOrderGenerator(
            sales_order,
            available_qty={("ITEM-1", "Stores - _TC"): 20},
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(generator.created, [])

    def test_multiple_suppliers_create_one_po_per_supplier(self):
        sales_order = make_sales_order(
            make_item("SOI-1", "ITEM-1", 10),
            make_item("SOI-2", "ITEM-2", 5),
        )
        generator = CapturingPurchaseOrderGenerator(
            sales_order,
            available_qty={
                ("ITEM-1", "Stores - _TC"): 0,
                ("ITEM-2", "Stores - _TC"): 0,
            },
            suppliers={"ITEM-1": "Supplier A", "ITEM-2": "Supplier B"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 2)
        self.assertEqual({entry[0] for entry in generator.created}, {"Supplier A", "Supplier B"})

    def test_existing_purchase_order_qty_prevents_duplicate(self):
        sales_order = make_sales_order(make_item("SOI-1", "ITEM-1", 10))
        generator = CapturingPurchaseOrderGenerator(
            sales_order,
            available_qty={("ITEM-1", "Stores - _TC"): 0},
            suppliers={"ITEM-1": "Supplier A"},
            existing_qty={"SOI-1": 10},
        )

        generator.run()

        self.assertEqual(generator.created, [])

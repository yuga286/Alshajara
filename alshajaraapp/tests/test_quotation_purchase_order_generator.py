import unittest
from pathlib import Path

import frappe

from alshajaraapp.quotation.purchase_order_generator import QuotationPurchaseOrderGenerator


class CapturingQuotationPurchaseOrderGenerator(QuotationPurchaseOrderGenerator):
    def __init__(
        self,
        quotation,
        available_qty=None,
        suppliers=None,
        existing_purchase_orders=None,
        fallback_warehouse=None,
    ):
        super().__init__(quotation)
        self.available_qty = available_qty or {}
        self.suppliers = suppliers or {}
        self.existing_purchase_orders = existing_purchase_orders or []
        self.fallback_warehouse = fallback_warehouse
        self.created = []

    def lock_quotation(self):
        return None

    def get_existing_purchase_orders(self):
        return self.existing_purchase_orders

    def get_item_details(self, item_code):
        return frappe._dict(
            name=item_code,
            item_name=f"{item_code} Name",
            stock_uom="Nos",
            is_stock_item=1,
        )

    def get_available_qty(self, item_code, warehouse):
        return self.available_qty.get((item_code, warehouse), 0)

    def get_warehouse_for_row(self, row, item_details=None):
        return row.get("warehouse") or self.fallback_warehouse

    def get_supplier_for_item(self, item_code, row=None):
        return self.suppliers.get(item_code)

    def get_purchase_defaults(self, supplier):
        return "KWD", "Standard Buying", 1

    def get_supplier_rate(self, item_code, supplier, uom, qty, transaction_date, **kwargs):
        return 100 if supplier else 0

    def create_purchase_order(self, supplier, lines):
        self.created.append((supplier, lines))
        return frappe._dict(name=f"PO-{len(self.created)}")

    def notify_user(self, duplicate=False):
        return None

    def log_skip(self, message, details=None):
        self.skipped_messages.append(message)

    def log_warning(self, message):
        self.warning_messages.append(message)


def make_quotation(*items):
    return frappe._dict(
        name="QTN-TEST",
        docstatus=1,
        company="_Test Company",
        transaction_date="2026-06-05",
        valid_till="2026-06-10",
        items=list(items),
    )


def make_item(
    name,
    item_code,
    qty,
    warehouse="Stores - _TC",
    stock_status=None,
    available_stock_qty=0,
    stock_qty=None,
    conversion_factor=1,
):
    return frappe._dict(
        name=name,
        idx=1,
        item_code=item_code,
        item_name=f"{item_code} Name",
        qty=qty,
        stock_qty=stock_qty if stock_qty is not None else qty,
        uom="Nos",
        stock_uom="Nos",
        conversion_factor=conversion_factor,
        warehouse=warehouse,
        stock_status=stock_status,
        available_stock_qty=available_stock_qty,
    )


class TestQuotationPurchaseOrderGenerator(unittest.TestCase):
    def test_draft_quotation_does_not_create_purchase_order(self):
        quotation = make_quotation(
            make_item("QTI-1", "ITEM-1", 10, stock_status="Unavailable Stock")
        )
        quotation.docstatus = 0
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={("ITEM-1", "Stores - _TC"): 0},
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(generator.created, [])

    def test_sufficient_stock_creates_no_purchase_order(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                stock_status="Out of Stock",
                available_stock_qty=20,
            )
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={("ITEM-1", "Stores - _TC"): 20},
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(generator.created, [])

    def test_zero_required_qty_creates_no_purchase_order(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                0,
                available_stock_qty=0,
            )
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(generator.created, [])

    def test_zero_stock_creates_one_draft_purchase_order_for_full_shortage(self):
        quotation = make_quotation(
            make_item("QTI-1", "ITEM-1", 10, stock_status="Unavailable Stock")
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={("ITEM-1", "Stores - _TC"): 0},
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(generator.created[0][0], "Supplier A")
        self.assertEqual(generator.created[0][1][0].qty, 10)

    def test_partial_stock_creates_purchase_order_for_shortage_qty(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                stock_status="Partial Stock (4)",
                available_stock_qty=4,
            )
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={("ITEM-1", "Stores - _TC"): 4},
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(generator.created[0][1][0].qty, 6)

    def test_available_stock_qty_shortage_creates_po_even_if_other_warehouse_has_stock(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                warehouse="Warehouse A - _TC",
                stock_status="In Stock (50)",
                available_stock_qty=0,
            )
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={
                ("ITEM-1", "Warehouse A - _TC"): 0,
                ("ITEM-1", "Warehouse B - _TC"): 50,
            },
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(generator.created[0][1][0].warehouse, "Warehouse A - _TC")
        self.assertEqual(generator.created[0][1][0].qty, 10)

    def test_partial_available_stock_qty_creates_po_for_shortage_only(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                warehouse="Warehouse A - _TC",
                stock_status="Partially Available (4)",
                available_stock_qty=4,
            )
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={
                ("ITEM-1", "Warehouse A - _TC"): 4,
                ("ITEM-1", "Warehouse B - _TC"): 50,
            },
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(generator.created[0][1][0].qty, 6)

    def test_available_stock_qty_creates_no_po_even_if_stock_status_text_is_unavailable(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                warehouse="Warehouse A - _TC",
                stock_status="Out of Stock",
                available_stock_qty=10,
            )
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={
                ("ITEM-1", "Warehouse A - _TC"): 10,
                ("ITEM-1", "Warehouse B - _TC"): 0,
            },
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(generator.created, [])

    def test_mixed_available_stock_qty_shortage_creates_one_purchase_order(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                warehouse="Warehouse A - _TC",
                stock_status="Out of Stock",
                available_stock_qty=20,
            ),
            make_item(
                "QTI-2",
                "ITEM-2",
                5,
                warehouse="Warehouse B - _TC",
                stock_status="In Stock (50)",
                available_stock_qty=0,
            ),
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={
                ("ITEM-1", "Warehouse A - _TC"): 20,
                ("ITEM-2", "Warehouse B - _TC"): 0,
                ("ITEM-2", "Warehouse A - _TC"): 50,
            },
            suppliers={"ITEM-1": "Supplier A", "ITEM-2": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual([line.item_code for line in generator.created[0][1]], ["ITEM-2"])
        self.assertEqual(generator.created[0][1][0].warehouse, "Warehouse B - _TC")

    def test_shortage_is_based_on_available_stock_qty_not_stock_status_text(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                warehouse="Warehouse A - _TC",
                stock_status="In Stock (20)",
                available_stock_qty=0,
            )
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={("ITEM-1", "Warehouse A - _TC"): 20},
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(generator.created[0][1][0].qty, 10)

    def test_shortage_uses_quotation_qty_not_stock_qty(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                stock_qty=20,
                conversion_factor=2,
                available_stock_qty=10,
            )
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(generator.created, [])

    def test_purchase_order_line_qty_is_shortage_qty_only(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                stock_qty=20,
                conversion_factor=2,
                available_stock_qty=4,
            )
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(generator.created[0][1][0].qty, 6)
        self.assertEqual(generator.created[0][1][0].stock_qty, 12)

    def test_generator_does_not_read_stock_status_field_for_shortage(self):
        source = Path("apps/alshajaraapp/alshajaraapp/quotation/purchase_order_generator.py").read_text()

        self.assertIn("available_stock_qty", source)
        self.assertNotIn('row.get("stock_status")', source)
        self.assertNotIn("row.get('stock_status')", source)

    def test_multiple_short_items_create_one_purchase_order(self):
        quotation = make_quotation(
            make_item("QTI-1", "ITEM-1", 10, stock_status="Unavailable"),
            make_item("QTI-2", "ITEM-2", 5, stock_status="Out of Stock"),
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={
                ("ITEM-1", "Stores - _TC"): 0,
                ("ITEM-2", "Stores - _TC"): 0,
            },
            suppliers={"ITEM-1": "Supplier A", "ITEM-2": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(generator.created[0][0], "Supplier A")
        self.assertEqual([line.item_code for line in generator.created[0][1]], ["ITEM-1", "ITEM-2"])

    def test_same_item_rows_use_each_row_stock_status_independently(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                stock_status="Out of Stock",
                available_stock_qty=12,
            ),
            make_item(
                "QTI-2",
                "ITEM-1",
                10,
                stock_status="In Stock (12)",
                available_stock_qty=0,
            ),
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={("ITEM-1", "Stores - _TC"): 12},
            suppliers={"ITEM-1": "Supplier A"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(len(generator.created[0][1]), 1)
        self.assertEqual(generator.created[0][1][0].quotation_item, "QTI-2")
        self.assertEqual(generator.created[0][1][0].qty, 10)

    def test_missing_row_warehouse_uses_fallback_warehouse(self):
        quotation = make_quotation(
            make_item(
                "QTI-1",
                "ITEM-1",
                10,
                warehouse=None,
                stock_status="Partial Stock (4)",
                available_stock_qty=4,
            )
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={("ITEM-1", "Fallback - _TC"): 4},
            suppliers={"ITEM-1": "Supplier A"},
            fallback_warehouse="Fallback - _TC",
        )

        generator.run()

        self.assertEqual(len(generator.created), 1)
        self.assertEqual(generator.created[0][1][0].warehouse, "Fallback - _TC")
        self.assertEqual(generator.created[0][1][0].qty, 6)

    def test_existing_purchase_order_prevents_duplicate_creation(self):
        quotation = make_quotation(
            make_item("QTI-1", "ITEM-1", 10, stock_status="Unavailable")
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={("ITEM-1", "Stores - _TC"): 0},
            suppliers={"ITEM-1": "Supplier A"},
            existing_purchase_orders=["PO-EXISTING"],
        )

        generator.run()

        self.assertEqual(generator.created, [])
        self.assertEqual(generator.created_purchase_orders, ["PO-EXISTING"])

    def test_multiple_suppliers_create_one_purchase_order_per_supplier(self):
        quotation = make_quotation(
            make_item("QTI-1", "ITEM-1", 10, stock_status="Unavailable"),
            make_item("QTI-2", "ITEM-2", 5, stock_status="No Stock"),
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={
                ("ITEM-1", "Stores - _TC"): 0,
                ("ITEM-2", "Stores - _TC"): 0,
            },
            suppliers={"ITEM-1": "Supplier A", "ITEM-2": "Supplier B"},
        )

        generator.run()

        self.assertEqual(len(generator.created), 2)
        self.assertEqual(generator.created[0][0], "Supplier A")
        self.assertEqual(generator.created[1][0], "Supplier B")
        self.assertEqual([line.item_code for line in generator.created[0][1]], ["ITEM-1"])
        self.assertEqual([line.item_code for line in generator.created[1][1]], ["ITEM-2"])

    def test_no_supplier_for_any_short_item_creates_no_purchase_order(self):
        quotation = make_quotation(
            make_item("QTI-1", "ITEM-1", 10, stock_status="Unavailable")
        )
        generator = CapturingQuotationPurchaseOrderGenerator(
            quotation,
            available_qty={("ITEM-1", "Stores - _TC"): 0},
            suppliers={},
        )

        generator.run()

        self.assertEqual(generator.created, [])
        self.assertTrue(generator.skipped_messages)

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from alshajaraapp.api import comman


class TestStockStatusStability(unittest.TestCase):
    def get_stock_status_with_actual_qty(self, actual_qty, required_qty=10):
        sentinel = object()
        original_db = comman.frappe.__dict__.get("db", sentinel)
        comman.frappe.__dict__["db"] = SimpleNamespace(get_value=lambda *args, **kwargs: actual_qty)

        try:
            return comman.get_stock_status("ITEM-1", qty=required_qty, warehouse="Stores")
        finally:
            if original_db is sentinel:
                comman.frappe.__dict__.pop("db", None)
            else:
                comman.frappe.__dict__["db"] = original_db

    def test_stock_quantity_parser_handles_invalid_values(self):
        self.assertIsNone(comman._parse_stock_quantity(None))
        self.assertIsNone(comman._parse_stock_quantity(""))
        self.assertIsNone(comman._parse_stock_quantity("not-a-number"))
        self.assertEqual(comman._parse_stock_quantity("-5"), -5)
        self.assertEqual(comman._parse_stock_quantity("4.5"), 4.5)

    def test_invalid_required_qty_returns_stable_status_without_db_lookup(self):
        result = comman.get_stock_status("ITEM-1", qty=-1)

        self.assertEqual(result["status"], "orange")
        self.assertEqual(result["message"], "Invalid Quantity")
        self.assertEqual(result["required_qty"], -1)

    def test_in_stock_returns_visible_status(self):
        result = self.get_stock_status_with_actual_qty(20)

        self.assertEqual(result["status"], "green")
        self.assertEqual(result["message"], "In Stock (20.0)")
        self.assertEqual(result["available_qty"], 20)
        self.assertEqual(result["required_qty"], 10)

    def test_low_stock_returns_visible_status(self):
        result = self.get_stock_status_with_actual_qty(4)

        self.assertEqual(result["status"], "blue")
        self.assertEqual(result["message"], "Partial Stock (4.0)")
        self.assertEqual(result["available_qty"], 4)
        self.assertEqual(result["required_qty"], 10)

    def test_out_of_stock_returns_visible_status(self):
        result = self.get_stock_status_with_actual_qty(0)

        self.assertEqual(result["status"], "red")
        self.assertEqual(result["message"], "Out of Stock")
        self.assertEqual(result["available_qty"], 0)
        self.assertEqual(result["required_qty"], 10)

    def test_missing_item_returns_visible_fallback(self):
        result = comman.get_stock_status(None, qty=1)

        self.assertEqual(result["status"], "orange")
        self.assertEqual(result["message"], "Stock status unavailable")

    def test_quotation_stock_status_has_single_source_and_race_guard(self):
        script = Path("apps/alshajaraapp/alshajaraapp/public/js/quotation.js").read_text()

        self.assertIn("Single source of truth for stock status stability", script)
        self.assertIn("hasItemAdded", script)
        self.assertIn("stockStatus", script)
        self.assertIn("lastValidStockStatus", script)
        self.assertIn("QUOTATION_STOCK_STATUS_ROW_STATES", script)
        self.assertIn("get_quotation_stock_status_row_key", script)
        self.assertIn("restore_quotation_stock_status_from_row_cache", script)
        self.assertIn("preserve_quotation_stock_statuses", script)
        self.assertIn("available_stock_qty", script)
        self.assertIn("next_state.available_qty !== undefined", script)
        self.assertIn("last_valid_state", script)
        self.assertIn("request_id", script)
        self.assertIn("request_key", script)
        self.assertIn("Stock Check Failed", script)
        self.assertIn("Checking Stock...", script)
        self.assertIn("Stock status unavailable", script)
        self.assertIn('return "";', script)
        self.assertIn("if (!response_message)", script)
        self.assertIn("catch (error)", script)
        self.assertIn("QUOTATION_STOCK_STATUS.INVALID_QTY,", script)
        self.assertIn("QUOTATION_STOCK_STATUS_FALLBACK,", script)
        self.assertIn('row.stock_status = "";', script)
        self.assertIn("stock_status_df.hidden = 0", script)
        self.assertIn("stock_status_df.in_list_view = 1", script)
        self.assertNotIn("QUOTATION_ITEM_GRID_LAYOUT", script)
        self.assertNotIn("visible_columns", script)
        self.assertNotIn("user_defined_columns", script)
        self.assertNotIn("configure_columns_button?.hide", script)
        self.assertNotIn("MutationObserver", script)
        self.assertNotIn("grid.refresh = function", script)
        self.assertNotIn("set_quotation_stock_status_area_html", script)
        self.assertNotIn("render_quotation_stock_status", script)
        self.assertNotIn("items_add(frm, cdt, cdn)", script)
        self.assertNotIn('make_quotation_stock_status_state(QUOTATION_STOCK_STATUS.EMPTY, "")', script)
        self.assertNotIn("append(", script)

    def test_child_grid_layout_css_is_not_included(self):
        hooks = Path("apps/alshajaraapp/alshajaraapp/hooks.py").read_text()

        self.assertNotIn("quotation_item_grid.css", hooks)
        self.assertFalse(Path("apps/alshajaraapp/alshajaraapp/public/css/quotation_item_grid.css").exists())

    def test_quotation_item_warehouse_grid_override_is_removed(self):
        property_setters = Path("apps/alshajaraapp/alshajaraapp/fixtures/property_setter.json").read_text()
        custom_fields = json.loads(Path("apps/alshajaraapp/alshajaraapp/fixtures/custom_field.json").read_text())
        patch = Path("apps/alshajaraapp/alshajaraapp/patches/remove_child_grid_layout_overrides.py").read_text()

        self.assertNotIn('"name": "Quotation Item-warehouse-in_list_view"', property_setters)
        self.assertIn('"Quotation Item-warehouse-in_list_view"', patch)
        for custom_field in custom_fields:
            if custom_field.get("name") in {
                "Opportunity Item-stock_status",
                "Opportunity Item-warehouse",
                "Quotation Item-stock_status",
            }:
                self.assertNotIn("columns", custom_field)
        self.assertIn("CUSTOM_FIELD_COLUMNS_TO_CLEAR", patch)

    def test_opportunity_stock_status_has_single_source_and_race_guard(self):
        script = Path("apps/alshajaraapp/alshajaraapp/public/js/opportunity.js").read_text()

        self.assertIn("Single source of truth for Opportunity stock status", script)
        self.assertIn("hasItemAdded", script)
        self.assertIn("stockStatus", script)
        self.assertIn("lastValidStockStatus", script)
        self.assertIn("OPPORTUNITY_STOCK_STATUS_ROW_STATES", script)
        self.assertIn("get_opportunity_stock_status_row_key", script)
        self.assertIn("get_opportunity_stock_status_row_keys", script)
        self.assertIn("restore_opportunity_stock_status_from_row_cache", script)
        self.assertIn("preserve_opportunity_stock_statuses", script)
        self.assertIn("last_valid_state", script)
        self.assertIn("request_id", script)
        self.assertIn("request_key", script)
        self.assertIn("Stock Check Failed", script)
        self.assertIn("Checking Stock...", script)
        self.assertIn("Stock status unavailable", script)
        self.assertIn('return "";', script)
        self.assertIn("apply_opportunity_items_grid_stock_docfields", script)
        self.assertIn("setup_opportunity_warehouse_query", script)
        self.assertIn("refresh_opportunity_stock_statuses_display(frm);", script)
        self.assertIn("normalize_opportunity_stock_status_response", script)
        self.assertIn("if (!response_message)", script)
        self.assertIn("get_opportunity_stock_required_qty", script)
        self.assertIn("schedule_opportunity_item_stock_status_update", script)
        self.assertIn("schedule_opportunity_stock_statuses_update", script)
        self.assertIn("OPPORTUNITY_STOCK_STATUS.NO_WAREHOUSE", script)
        self.assertIn('"Select Warehouse"', script)
        self.assertIn("warehouse: row.warehouse", script)
        self.assertIn("catch (error)", script)
        self.assertIn("OPPORTUNITY_STOCK_STATUS.INVALID_QTY,", script)
        self.assertIn("OPPORTUNITY_STOCK_STATUS_FALLBACK", script)
        self.assertIn("stock_status_df.hidden = 0", script)
        self.assertIn("stock_status_df.in_list_view = 1", script)
        self.assertIn('row.stock_status = "";', script)
        self.assertNotIn("OPPORTUNITY_ITEM_STOCK_GRID_COLUMNS", script)
        self.assertNotIn("visible_columns", script)
        self.assertNotIn("user_defined_columns", script)
        self.assertNotIn("MutationObserver", script)
        self.assertNotIn("grid.refresh = function", script)
        self.assertNotIn("capture_opportunity_stock_statuses_from_grid", script)
        self.assertNotIn("set_opportunity_stock_status_area_html", script)
        self.assertNotIn("render_opportunity_stock_status", script)
        self.assertNotIn("items_add(frm, cdt, cdn)", script)
        self.assertNotIn('make_opportunity_stock_status_state(OPPORTUNITY_STOCK_STATUS.EMPTY, "")', script)
        self.assertNotIn("append(", script)


if __name__ == "__main__":
    unittest.main()

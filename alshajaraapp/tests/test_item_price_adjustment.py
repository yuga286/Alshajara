import unittest
from pathlib import Path
from unittest.mock import patch

import frappe

from alshajaraapp.api import item_price


class FakeItemPrice(frappe._dict):
    def __init__(self, is_new=False, **kwargs):
        super().__init__(**kwargs)
        self._is_new = is_new
        self.saved = False
        self.inserted = False

    def is_new(self):
        return self._is_new

    def check_permission(self, permission_type):
        self.checked_permission = permission_type

    def save(self):
        self.saved = True
        return self

    def insert(self):
        self.inserted = True
        self.name = self.name or "ITEM-PRICE-NEW"
        return self


class TestItemPricePopup(unittest.TestCase):
    def test_shared_popup_contains_one_note_field(self):
        script = Path("apps/alshajaraapp/alshajaraapp/public/js/item_price_list_popup.js").read_text()

        self.assertEqual(script.count('fieldname: "note"'), 1)
        self.assertIn("function add_note_field(fields)", script)
        self.assertIn('method: "alshajaraapp.api.item_price.save_item_price_from_popup"', script)

    def test_price_list_button_uses_shared_popup(self):
        script = Path("apps/alshajaraapp/alshajaraapp/public/js/price_list.js").read_text()

        self.assertIn("/assets/alshajaraapp/js/item_price_list_popup.js", script)
        self.assertIn("alshajaraapp.item_price_list.open", script)
        self.assertIn("price_list: frm.doc.name", script)
        self.assertNotIn("Price Change History", script)

    def test_item_button_uses_shared_popup_with_item_context(self):
        script = Path("apps/alshajaraapp/alshajaraapp/public/js/item.js").read_text()

        self.assertIn("/assets/alshajaraapp/js/item_price_list_popup.js", script)
        self.assertIn("alshajaraapp.item_price_list.open", script)
        self.assertIn("item_code: frm.doc.name", script)

    def test_save_updates_existing_item_price_note(self):
        existing = frappe._dict(name="ITEM-PRICE-1")
        doc = FakeItemPrice(
            is_new=False,
            name="ITEM-PRICE-1",
            item_code="ITEM-1",
            price_list="Standard Selling",
            uom="Nos",
            price_list_rate=100,
            currency="KWD",
            note="",
        )

        with (
            patch.object(item_price, "_get_price_list_details", return_value=frappe._dict(currency="KWD")),
            patch.object(item_price, "_get_item_details", return_value=frappe._dict(item_name="Item 1", stock_uom="Nos")),
            patch.object(item_price, "get_default_item_price", return_value=existing),
            patch.object(item_price.frappe, "get_doc", return_value=doc),
        ):
            result = item_price.save_item_price_from_popup(
                price_list="Standard Selling",
                item_code="ITEM-1",
                price_list_rate=125,
                uom="Nos",
                note="  seasonal update  ",
            )

        self.assertTrue(doc.saved)
        self.assertEqual(doc.checked_permission, "write")
        self.assertEqual(doc.price_list_rate, 125)
        self.assertEqual(doc.note, "seasonal update")
        self.assertEqual(result.note, "seasonal update")

    def test_save_creates_item_price_with_note(self):
        doc = FakeItemPrice(
            is_new=True,
            name=None,
            item_code=None,
            price_list=None,
            uom=None,
            price_list_rate=0,
            currency="KWD",
            note="",
        )

        with (
            patch.object(item_price, "_get_price_list_details", return_value=frappe._dict(currency="KWD")),
            patch.object(item_price, "_get_item_details", return_value=frappe._dict(item_name="Item 1", stock_uom="Nos")),
            patch.object(item_price, "get_default_item_price", return_value=None),
            patch.object(item_price.frappe, "has_permission", return_value=True),
            patch.object(item_price.frappe, "new_doc", return_value=doc),
        ):
            result = item_price.save_item_price_from_popup(
                price_list="Standard Selling",
                item_code="ITEM-1",
                price_list_rate=125,
                uom="Nos",
                note="new price",
            )

        self.assertTrue(doc.inserted)
        self.assertEqual(doc.item_code, "ITEM-1")
        self.assertEqual(doc.price_list, "Standard Selling")
        self.assertEqual(doc.note, "new price")
        self.assertEqual(result.item_price, "ITEM-PRICE-NEW")


if __name__ == "__main__":
    unittest.main()

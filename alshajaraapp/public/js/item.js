frappe.provide("alshajaraapp.item");

frappe.ui.form.on("Item", {
	refresh(frm) {
		alshajaraapp.item.install_price_button(frm);
	},
});

alshajaraapp.item.install_price_button = function (frm) {
	if (frm.doc.__islocal) {
		return;
	}

	setTimeout(() => {
		frm.remove_custom_button(__("Add / Edit Prices"), __("Actions"));

		frm.add_custom_button(
			__("Add / Edit Prices"),
			() => {
				frappe.require("/assets/alshajaraapp/js/item_price_list_popup.js", () => {
					alshajaraapp.item_price_list.open({
						item_code: frm.doc.name,
						frm,
					});
				});
			},
			__("Actions")
		);
	}, 0);
};

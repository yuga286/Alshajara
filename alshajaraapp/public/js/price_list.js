frappe.provide("alshajaraapp.price_list");

frappe.ui.form.on("Price List", {
	refresh(frm) {
		alshajaraapp.price_list.install_price_button(frm);
	},
});

alshajaraapp.price_list.install_price_button = function (frm) {
	if (frm.doc.__islocal) {
		return;
	}

	setTimeout(() => {
		frm.remove_custom_button(__("Add / Edit Prices"), "fa fa-money");
		frm.remove_custom_button(__("Add / Edit Prices"), __("Actions"));

		frm.add_custom_button(
			__("Add / Edit Prices"),
			() => {
				frappe.require("/assets/alshajaraapp/js/item_price_list_popup.js", () => {
					alshajaraapp.item_price_list.open({
						price_list: frm.doc.name,
						frm,
					});
				});
			},
			__("Actions")
		);
	}, 0);
};

frappe.provide("alshajaraapp.item_price_list");

alshajaraapp.item_price_list.open = function (options = {}) {
	let fetching = false;

	const dialog = new frappe.ui.Dialog({
		title: __("New Item Price List"),
		fields: get_dialog_fields(options),
		primary_action_label: __("Save"),
		primary_action(values) {
			frappe.call({
				method: "alshajaraapp.api.item_price.save_item_price_from_popup",
				args: {
					price_list: values.price_list,
					item_code: values.item_code,
					uom: values.uom,
					item_price: values.item_price,
					price_list_rate: values.price_list_rate,
					note: values.note,
				},
				freeze: true,
				freeze_message: __("Saving..."),
				callback(r) {
					if (!r.message) {
						return;
					}

					dialog.hide();
					frappe.show_alert({
						message: __("Item price saved."),
						indicator: "green",
					});

					if (options.frm) {
						options.frm.reload_doc();
					}
				},
			});
		},
	});

	dialog.show();
	refresh_context();

	function get_dialog_fields(opts) {
		const fields = [
			{
				fieldtype: "Link",
				fieldname: "item_code",
				label: __("Item"),
				options: "Item",
				default: opts.item_code,
				read_only: Boolean(opts.item_code),
				reqd: 1,
				get_query: () => ({
					filters: {
						has_variants: 0,
					},
				}),
				onchange: () => refresh_context(),
			},
			{
				fieldtype: "Data",
				fieldname: "item_name",
				label: __("Item Name"),
				read_only: 1,
			},
			{
				fieldtype: "Column Break",
			},
			{
				fieldtype: "Link",
				fieldname: "price_list",
				label: __("Price List"),
				options: "Price List",
				default: opts.price_list,
				read_only: Boolean(opts.price_list),
				reqd: 1,
				get_query: () => ({
					filters: {
						enabled: 1,
					},
				}),
				onchange: () => refresh_context(),
			},
			{
				fieldtype: "Link",
				fieldname: "currency",
				label: __("Currency"),
				options: "Currency",
				read_only: 1,
			},
			{
				fieldtype: "Section Break",
			},
			{
				fieldtype: "Link",
				fieldname: "uom",
				label: __("UOM"),
				options: "UOM",
				reqd: 1,
				onchange: () => refresh_context(),
			},
			// {
			// 	fieldtype: "Link",
			// 	fieldname: "item_price",
			// 	label: __("Existing Item Price"),
			// 	options: "Item Price",
			// 	read_only: 1,
			// },
			{
				fieldtype: "Column Break",
			},
			// {
			// 	fieldtype: "Currency",
			// 	fieldname: "current_rate",
			// 	label: __("Current Rate"),
			// 	options: "currency",
			// 	read_only: 1,
			// },
			{
				fieldtype: "Currency",
				fieldname: "price_list_rate",
				label: __("New Rate"),
				options: "currency",
				reqd: 1,
			},
		];

		add_note_field(fields);
		return fields;
	}

	function add_note_field(fields) {
		if (fields.some((field) => field.fieldname === "note")) {
			return;
		}

		fields.push({
			fieldtype: "Small Text",
			fieldname: "note",
			label: __("Note"),
		});
	}

	function value_or_blank(value) {
		return value === null || value === undefined ? "" : value;
	}

	function set_context_values(data) {
		fetching = true;
		dialog.set_value("currency", data.currency || "");
		dialog.set_value("item_name", data.item_name || "");

		if (data.uom && !dialog.get_value("uom")) {
			dialog.set_value("uom", data.uom);
		}

		if (dialog.get_value("item_code") && dialog.get_value("price_list")) {
			dialog.set_value("item_price", data.item_price || "");
			dialog.set_value("current_rate", value_or_blank(data.current_rate));
			dialog.set_value("price_list_rate", value_or_blank(data.price_list_rate));
			dialog.set_value("note", data.note || "");
		}

		fetching = false;
	}

	function refresh_context() {
		if (fetching) {
			return;
		}

		frappe.call({
			method: "alshajaraapp.api.item_price.get_item_price_popup_context",
			args: {
				price_list: dialog.get_value("price_list"),
				item_code: dialog.get_value("item_code"),
				uom: dialog.get_value("uom"),
			},
			callback(r) {
				set_context_values(r.message || {});
			},
		});
	}
};

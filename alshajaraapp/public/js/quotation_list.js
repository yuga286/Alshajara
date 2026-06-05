frappe.listview_settings["Quotation"] = {
	formatters: {
		_sent(val) {
			if (val === "Sent") {
				return `<span class="indicator green">${val}</span>`;
			}

			if (val === "Not Sent") {
				return `<span class="indicator orange">${val}</span>`;
			}

			return val;
		},
	},
};

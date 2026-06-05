const QUOTATION_ITEM_GRID_CLASS = "alshajara-quotation-items-grid";
const QUOTATION_ITEM_GRID_LAYOUT = [
	{ fieldname: "item_code", columns: 3, width: 220 },
	{ fieldname: "warehouse", columns: 2, width: 180 },
	{ fieldname: "stock_status", columns: 2, width: 170 },
	{ fieldname: "qty", columns: 1, width: 90 },
	{ fieldname: "rate", columns: 2, width: 140 },
	{ fieldname: "amount", columns: 2, width: 150 },
	{ fieldname: "total_profit_percentage", columns: 1, width: 120 },
];

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		setup_quotation_stock_status_formatter(frm);
		update_quotation_stock_statuses(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(__("+ Add Note"), () => {
				frm.trigger("open_add_note_dialog");
			});
		}

		if (!frappe.user.has_role("System Manager") && frm.doc.docstatus === 1 && frm.doc._sent === "Not Sent") {
			frm.add_custom_button(__("Mark as Sent"), () => {
				frappe.call({
					method: "alshajaraapp.api.quotation.mark_quotation_sent",
					args: { name: frm.doc.name },
					callback() {
						frm.reload_doc();
					},
				});
			});
		}

		(frm.doc.items || []).forEach((row) => {
			if (row.original_rate == null) {
				row.original_rate = flt(row.base_price_list_rate || row.price_list_rate || row.rate || 0);
			}

			if (row.original_currency == null) {
				row.original_currency = frm.doc.company_currency || frm.doc.currency;
			}
		});

		calculate_quotation_profit(frm, false);
		frm._last_currency = frm.doc.currency;
	},

	company(frm) {
		update_quotation_stock_statuses(frm);
	},

	open_add_note_dialog(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Add Note"),
			fields: [
				{
					label: __("Note"),
					fieldname: "note",
					fieldtype: "Text Editor",
					reqd: 1,
				},
			],
			primary_action_label: __("Add"),
			primary_action(values) {
				frappe.call({
					method: "alshajaraapp.api.quotation.add_quotation_note",
					args: {
						quotation: frm.doc.name,
						note: values.note,
					},
					freeze: true,
					callback() {
						d.hide();
						frm.reload_doc();
					},
				});
			},
		});

		d.show();
	},

	async currency(frm) {
		const current_currency = frm.doc.currency;
		if (!current_currency) {
			return;
		}

		const company_currency = frm.doc.company
			? await frappe.db
				.get_value("Company", frm.doc.company, "default_currency")
				.then((r) => r.message?.default_currency)
			: null;

		for (const row of frm.doc.items || []) {
			const source_currency = company_currency || current_currency;
			const source_rate = flt(row.original_rate || row.base_price_list_rate || row.price_list_rate || row.rate || 0);
			const qty = flt(row.qty) || 1;

			let exchange_rate = 1;
			if (source_currency !== current_currency) {
				exchange_rate = await get_exchange_rate(
					source_currency,
					current_currency,
					frm.doc.transaction_date || frm.doc.posting_date
				);
				if (!exchange_rate) {
					exchange_rate = flt(frm.doc.conversion_rate || 1);
				}
			}

			let company_exchange_rate = 1;
			if (company_currency && current_currency !== company_currency) {
				company_exchange_rate = await get_exchange_rate(
					current_currency,
					company_currency,
					frm.doc.transaction_date || frm.doc.posting_date
				);
				if (!company_exchange_rate) {
					company_exchange_rate = flt(frm.doc.conversion_rate || 1);
				}
			}

			const converted_rate = flt(source_rate * exchange_rate, 2);
			const amount = flt(converted_rate * qty, 2);
			const base_rate = flt(source_rate, 2);
			const base_amount = flt(base_rate * qty, 2);

			await frm.set_value("conversion_rate", flt(company_exchange_rate, 6));
			await frappe.model.set_value(row.doctype, row.name, "rate", converted_rate);
			await frappe.model.set_value(row.doctype, row.name, "base_rate", base_rate);
			await frappe.model.set_value(row.doctype, row.name, "net_rate", converted_rate);
			await frappe.model.set_value(row.doctype, row.name, "amount", amount);
			await frappe.model.set_value(row.doctype, row.name, "base_amount", base_amount);
			await frappe.model.set_value(row.doctype, row.name, "net_amount", amount);
			await frappe.model.set_value(row.doctype, row.name, "base_net_amount", base_amount);

			row.original_rate = source_rate;
			row.original_currency = source_currency;
		}

		frm.refresh_field("items");
		frm.trigger("calculate_taxes_and_totals");
		await calculate_quotation_profit(frm, false);
		refresh_quotation_stock_statuses_display(frm);
		frm._last_currency = current_currency;
	},

	validate(frm) {
		return calculate_quotation_profit(frm, true);
	},

	before_save(frm) {
		return calculate_quotation_profit(frm, true);
	},
});

async function get_exchange_rate(from_currency, to_currency, transaction_date) {
	const response = await frappe.call({
		method: "alshajaraapp.api.quotation.get_live_exchange_rate",
		args: {
			from_currency,
			to_currency,
			transaction_date,
		},
	});

	return flt(response.message || 0);
}

function setup_quotation_stock_status_formatter(frm) {
	const grid = frm.fields_dict?.items?.grid;
	apply_quotation_items_grid_docfield_properties(grid);

	if (grid) {
		setup_quotation_warehouse_query(frm);
		lock_quotation_items_grid_refresh(grid);
		observe_quotation_items_grid(grid);
		apply_quotation_items_grid_layout(grid);
		rebuild_quotation_items_grid_if_columns_changed(grid);
		apply_quotation_items_grid_dom_lock(grid);
	}
}

function setup_quotation_warehouse_query(frm) {
	const warehouse_field = frm.fields_dict?.items?.grid?.get_field("warehouse");
	if (!warehouse_field) {
		return;
	}

	warehouse_field.get_query = () => {
		if (!frm.doc.company) {
			return {};
		}

		return {
			filters: {
				company: frm.doc.company,
			},
		};
	};
}

function get_quotation_items_grid_docfield(grid, fieldname) {
	return grid?.fields_map?.[fieldname]
		|| grid?.docfields?.find((field) => field.fieldname === fieldname)
		|| frappe.meta.get_docfield("Quotation Item", fieldname);
}

function apply_quotation_items_grid_docfield_properties(grid) {
	for (const column of QUOTATION_ITEM_GRID_LAYOUT) {
		const meta_df = frappe.meta.get_docfield("Quotation Item", column.fieldname);
		const grid_df = get_quotation_items_grid_docfield(grid, column.fieldname);
		const docfields = [...new Set([meta_df, grid_df].filter(Boolean))];

		for (const df of docfields) {
			df.hidden = 0;
			df.in_list_view = 1;
			df.columns = column.columns;
			df.colsize = column.columns;
		}
	}

	const stock_status_df = get_quotation_items_grid_docfield(grid, "stock_status");
	if (stock_status_df) {
		stock_status_df.formatter = format_quotation_stock_status;
		stock_status_df.read_only = 1;
	}

	const warehouse_df = get_quotation_items_grid_docfield(grid, "warehouse");
	if (warehouse_df) {
		warehouse_df.read_only = 0;
	}

	const total_profit_df = get_quotation_items_grid_docfield(grid, "total_profit_percentage");
	if (total_profit_df) {
		total_profit_df.read_only = 1;
	}
}

function apply_quotation_items_grid_layout(grid) {
	if (!grid) {
		return;
	}

	apply_quotation_items_grid_docfield_properties(grid);

	const visible_columns = QUOTATION_ITEM_GRID_LAYOUT
		.map((column) => {
			const df = get_quotation_items_grid_docfield(grid, column.fieldname);
			if (!df) {
				return null;
			}

			df.columns = column.columns;
			df.colsize = column.columns;
			return [df, column.columns];
		})
		.filter(Boolean);

	grid.wrapper?.addClass(QUOTATION_ITEM_GRID_CLASS);
	grid.visible_columns = visible_columns;
	grid.user_defined_columns = visible_columns.map(([df]) => df);
}

function lock_quotation_items_grid_refresh(grid) {
	if (!grid || grid._quotation_items_grid_refresh_locked) {
		return;
	}

	const original_refresh = grid.refresh.bind(grid);
	grid.refresh = function (...args) {
		apply_quotation_items_grid_layout(grid);
		const result = original_refresh(...args);
		apply_quotation_items_grid_layout(grid);
		apply_quotation_items_grid_dom_lock(grid);
		return result;
	};

	grid._quotation_items_grid_refresh_locked = true;
}

function apply_quotation_items_grid_dom_lock(grid) {
	if (!grid?.wrapper) {
		return;
	}

	grid.wrapper.addClass(QUOTATION_ITEM_GRID_CLASS);
	grid.header_row?.configure_columns_button?.hide();

	for (const column of QUOTATION_ITEM_GRID_LAYOUT) {
		grid.wrapper
			.find(`.grid-static-col[data-fieldname="${column.fieldname}"]`)
			.css({
				flex: `0 0 ${column.width}px`,
				width: `${column.width}px`,
				"min-width": `${column.width}px`,
				"max-width": `${column.width}px`,
			});
	}

	grid.wrapper
		.find(".grid-heading-row .data-row.row, .grid-body .rows .data-row.row")
		.css({
			"flex-wrap": "nowrap",
			"justify-content": "flex-start",
		});
}

function observe_quotation_items_grid(grid) {
	if (!grid?.wrapper || grid._quotation_items_grid_observer || !window.MutationObserver) {
		return;
	}

	let scheduled = false;
	const observer = new MutationObserver(() => {
		if (scheduled) {
			return;
		}

		scheduled = true;
		setTimeout(() => {
			scheduled = false;
			apply_quotation_items_grid_layout(grid);
			apply_quotation_items_grid_dom_lock(grid);
		}, 0);
	});

	observer.observe(grid.wrapper.get(0), {
		childList: true,
		subtree: true,
	});

	grid._quotation_items_grid_observer = observer;
}

function get_quotation_items_grid_column_signature(grid) {
	return (grid.visible_columns || [])
		.map(([df, colsize]) => `${df.fieldname}:${colsize}`)
		.join("|");
}

function rebuild_quotation_items_grid_if_columns_changed(grid) {
	const signature = get_quotation_items_grid_column_signature(grid);
	if (!signature || grid._quotation_items_grid_column_signature === signature) {
		return;
	}

	grid._quotation_items_grid_column_signature = signature;
	grid.grid_rows = [];
	grid.grid_rows_by_docname = {};
	grid.header_row = null;
	grid.header_search = null;
	grid.wrapper?.find(".grid-body .rows .grid-row").remove();
	grid.wrapper?.find(".grid-heading-row .grid-row").remove();
	grid.refresh();
}

function update_quotation_stock_statuses(frm) {
	return Promise.all((frm.doc.items || []).map((row) => {
		return update_quotation_stock_status(frm, row.doctype, row.name);
	}));
}

function format_quotation_stock_status(value) {
	if (!value) return "";

	const text = cstr(value);
	const escaped_value = frappe.utils.escape_html(text);

	if (text.includes("In Stock")) {
		return `<span class="indicator green">${escaped_value}</span>`;
	}

	if (text.includes("Partial")) {
		return `<span class="indicator blue">${escaped_value}</span>`;
	}

	return `<span class="indicator red">${escaped_value}</span>`;
}

function refresh_quotation_stock_statuses_display(frm) {
	(frm.doc.items || []).forEach((row) => {
		refresh_quotation_stock_status_display(frm, row.name);
	});
}

function refresh_quotation_stock_status_display(frm, cdn) {
	const grid = frm.fields_dict?.items?.grid;
	const grid_row = grid?.grid_rows_by_docname?.[cdn];

	if (grid_row) {
		const row = locals[grid_row.doc?.doctype]?.[cdn] || grid_row.doc;
		const html = format_quotation_stock_status(row?.stock_status);

		grid_row.refresh_field("stock_status");
		grid_row.columns?.stock_status?.static_area?.html(html);
		if (grid_row.on_grid_fields_dict?.stock_status?.html) {
			grid_row.on_grid_fields_dict.stock_status.html(html);
		} else {
			grid_row.columns?.stock_status?.field_area?.html(html);
		}
		return;
	}

	frm.refresh_field("items");
}

async function set_quotation_stock_status(frm, cdt, cdn, value) {
	const row = locals[cdt]?.[cdn];
	if (row) {
		row.stock_status = value;
	}

	refresh_quotation_stock_status_display(frm, cdn);
}

async function update_quotation_stock_status(frm, cdt, cdn) {
	const row = locals[cdt]?.[cdn];

	if (!row) {
		return;
	}

	if (!row.item_code) {
		await set_quotation_stock_status(frm, cdt, cdn, "");
		return;
	}

	if (!row.warehouse) {
		await set_quotation_stock_status(frm, cdt, cdn, "");
		return;
	}

	const required_qty = get_quotation_stock_required_qty(row);
	const request_key = [
		row.item_code,
		row.warehouse || "",
		required_qty,
		frm.doc.company || "",
	].join("|");

	row._stock_status_request_key = request_key;

	const r = await frappe.call({
		method: "alshajaraapp.api.comman.get_stock_status",
		args: {
			item_code: row.item_code,
			company: frm.doc.company,
			warehouse: row.warehouse,
			qty: required_qty,
		},
	});

	const latest_row = locals[cdt]?.[cdn];
	if (!latest_row || latest_row._stock_status_request_key !== request_key) {
		return;
	}

	await set_quotation_stock_status(frm, cdt, cdn, r.message?.message || "");
}

function get_quotation_stock_required_qty(row) {
	const stock_qty = flt(row.stock_qty);
	if (stock_qty) {
		return stock_qty;
	}

	return flt(row.qty) * flt(row.conversion_factor || 1);
}

function schedule_quotation_stock_status_update(frm, cdt, cdn) {
	setTimeout(() => {
		update_quotation_stock_status(frm, cdt, cdn);
	}, 0);
}

function schedule_quotation_item_stock_status_update(frm, cdt, cdn) {
	schedule_quotation_stock_status_update(frm, cdt, cdn);
	setTimeout(() => {
		update_quotation_stock_status(frm, cdt, cdn);
	}, 500);
}

function calculate_row_profit(row) {
	const qty = flt(row.qty);
	const cost_rate = Math.max(flt(row.valuation_rate || row.price_list_rate || 0), 0);
	const selling_rate = Math.max(flt(row.rate), 0);
	const total_cost = qty * cost_rate;
	const total_selling = qty * selling_rate;
	const profit_amount = Math.max(total_selling - total_cost, 0);
	const profit_percentage = total_cost > 0 ? (profit_amount / total_cost) * 100 : 0;

	row.total_cost = flt(total_cost, 2);
	row.total_selling_price = flt(total_selling, 2);
	row.profit_amount = flt(profit_amount, 2);
	row.total_profit_percentage = flt(profit_percentage, 2);
}

async function calculate_quotation_profit(frm, persist = false) {
	let grand_total_cost = 0;
	let grand_total_selling = 0;
	let grand_total_profit = 0;

	for (const row of frm.doc.items || []) {
		calculate_row_profit(row);
		grand_total_cost += flt(row.total_cost);
		grand_total_selling += flt(row.total_selling_price);
		grand_total_profit += flt(row.profit_amount);

		if (persist) {
			await frappe.model.set_value(row.doctype, row.name, "total_cost", flt(row.total_cost, 2));
			await frappe.model.set_value(row.doctype, row.name, "total_selling_price", flt(row.total_selling_price, 2));
			await frappe.model.set_value(row.doctype, row.name, "profit_amount", flt(row.profit_amount, 2));
			await frappe.model.set_value(row.doctype, row.name, "total_profit_percentage", flt(row.total_profit_percentage, 2));
		}
	}

	const grand_profit_percentage = grand_total_cost > 0 ? (grand_total_profit / grand_total_cost) * 100 : 0;

	if (persist) {
		await frm.set_value("quotation_total_cost", flt(grand_total_cost, 2));
		await frm.set_value("quotation_total_selling_price", flt(grand_total_selling, 2));
		await frm.set_value("total_profit_amount", flt(grand_total_profit, 2));
		await frm.set_value("total_profit_percentage", flt(grand_profit_percentage, 2));
	} else {
		frm.doc.quotation_total_cost = flt(grand_total_cost, 2);
		frm.doc.quotation_total_selling_price = flt(grand_total_selling, 2);
		frm.doc.total_profit_amount = flt(grand_total_profit, 2);
		frm.doc.total_profit_percentage = flt(grand_profit_percentage, 2);
	}

	frm.refresh_fields([
		"quotation_total_cost",
		"quotation_total_selling_price",
		"total_profit_amount",
		"total_profit_percentage",
		"items",
	]);
	refresh_quotation_stock_statuses_display(frm);
}

frappe.ui.form.on("Quotation Item", {
	item_code(frm, cdt, cdn) {
		schedule_quotation_item_stock_status_update(frm, cdt, cdn);
	},

	uom(frm, cdt, cdn) {
		schedule_quotation_stock_status_update(frm, cdt, cdn);
	},

	conversion_factor(frm, cdt, cdn) {
		schedule_quotation_stock_status_update(frm, cdt, cdn);
	},

	stock_qty(frm, cdt, cdn) {
		schedule_quotation_stock_status_update(frm, cdt, cdn);
	},

	qty(frm, cdt, cdn) {
		setTimeout(async () => {
			await calculate_quotation_profit(frm, false);
			await update_quotation_stock_status(frm, cdt, cdn);
		}, 0);
	},

	warehouse(frm, cdt, cdn) {
		schedule_quotation_stock_status_update(frm, cdt, cdn);
	},

	price_list_rate(frm) {
		setTimeout(() => {
			calculate_quotation_profit(frm, false);
		}, 0);
	},

	rate(frm) {
		setTimeout(() => {
			calculate_quotation_profit(frm, false);
		}, 0);
	},

	cost_price(frm) {
		setTimeout(() => {
			calculate_quotation_profit(frm, false);
		}, 0);
	},
});

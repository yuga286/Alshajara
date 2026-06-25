const QUOTATION_STOCK_STATUS = {
	LOADING: "loading",
	IN_STOCK: "in_stock",
	LOW_STOCK: "low_stock",
	OUT_OF_STOCK: "out_of_stock",
	NO_WAREHOUSE: "no_warehouse",
	INVALID_QTY: "invalid_qty",
	API_ERROR: "api_error",
	EMPTY: "empty",
};
const QUOTATION_STOCK_STATUS_FALLBACK = "Stock status unavailable";
const QUOTATION_STOCK_STATUS_ROW_STATES = new Map();

frappe.ui.form.on("Quotation", {
	before_workflow_action(frm) {
		validate_quotation_reject_lost_reasons(frm);
	},

	refresh(frm) {
		setup_quotation_stock_status_formatter(frm);
		if (frm.doc.docstatus === 0) {
			update_quotation_stock_statuses(frm);
		} else {
			refresh_quotation_stock_statuses_display(frm);
		}

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

		preserve_quotation_stock_statuses(frm);
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

function validate_quotation_reject_lost_reasons(frm) {
	if (frm.selected_workflow_action !== "Reject") {
		return;
	}

	const lost_reasons = frm.doc.lost_reasons || [];
	const has_lost_reason = lost_reasons.some((row) => row.lost_reason);

	if (!has_lost_reason) {
		frm.scroll_to_field("lost_reasons");
		frappe.throw(__("Lost Reasons is required before rejecting this Quotation."));
	}
}

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
	apply_quotation_stock_status_docfield_properties(grid);

	if (grid) {
		setup_quotation_warehouse_query(frm);
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

function apply_quotation_stock_status_docfield_properties(grid) {
	const stock_status_df = get_quotation_items_grid_docfield(grid, "stock_status");
	if (stock_status_df) {
		stock_status_df.hidden = 0;
		stock_status_df.in_list_view = 1;
		stock_status_df.formatter = format_quotation_stock_status;
		stock_status_df.read_only = 1;
	}
}

function update_quotation_stock_statuses(frm) {
	return Promise.all((frm.doc.items || []).map((row) => {
		restore_quotation_stock_status_from_row_cache(row);
		return update_quotation_stock_status(frm, row.doctype, row.name);
	}));
}

function format_quotation_stock_status(value) {
	const text = cstr(value);
	if (!text) {
		return "";
	}

	const escaped_value = frappe.utils.escape_html(text);

	if (text.includes("In Stock")) {
		return `<span class="indicator green">${escaped_value}</span>`;
	}

	if (text.includes("Partial") || text.includes("Low Stock")) {
		return `<span class="indicator blue">${escaped_value}</span>`;
	}

	if (
		text.includes("Checking")
		|| text.includes("Select")
		|| text.includes("Invalid")
		|| text.includes("No Default")
		|| text.includes("Failed")
		|| text.includes("unavailable")
	) {
		return `<span class="indicator orange">${escaped_value}</span>`;
	}

	return `<span class="indicator red">${escaped_value}</span>`;
}

function refresh_quotation_stock_statuses_display(frm) {
	(frm.doc.items || []).forEach((row) => {
		restore_quotation_stock_status_from_row_cache(row);
		refresh_quotation_stock_status_display(frm, row.name);
	});
}

function refresh_quotation_stock_status_display(frm, cdn) {
	const grid = frm.fields_dict?.items?.grid;
	const grid_row = grid?.grid_rows_by_docname?.[cdn];

	if (grid_row) {
		grid_row.refresh_field("stock_status");
		return;
	}

	frm.refresh_field("items");
}

function make_quotation_stock_status_state(status, message, options = {}) {
	return {
		status,
		message: cstr(message),
		available_qty: options.available_qty,
		required_qty: options.required_qty,
		is_valid_stock: Boolean(options.is_valid_stock),
	};
}

function get_quotation_stock_status_row_key(row) {
	if (!row?.name) {
		return "";
	}

	return `${row.doctype || "Quotation Item"}:${row.name}`;
}

function make_quotation_stock_status_truth(row, has_item_added) {
	const stock_status = has_item_added ? cstr(row.stock_status || QUOTATION_STOCK_STATUS_FALLBACK) : "";
	return {
		hasItemAdded: has_item_added,
		stockStatus: stock_status,
		lastValidStockStatus: row.stock_status ? cstr(row.stock_status) : "",
		request_id: 0,
		request_key: "",
		current_state: make_quotation_stock_status_state(
			QUOTATION_STOCK_STATUS.EMPTY,
			stock_status
		),
		last_valid_state: row.stock_status
			? make_quotation_stock_status_state(
				classify_quotation_stock_status_message(row.stock_status),
				row.stock_status,
				{ is_valid_stock: true }
			)
			: null,
	};
}

function cache_quotation_stock_status_truth(row, truth) {
	const row_key = get_quotation_stock_status_row_key(row);
	if (row_key) {
		QUOTATION_STOCK_STATUS_ROW_STATES.set(row_key, truth);
	}
}

function restore_quotation_stock_status_from_row_cache(row) {
	const row_key = get_quotation_stock_status_row_key(row);
	if (!row_key) {
		return null;
	}

	const cached_truth = QUOTATION_STOCK_STATUS_ROW_STATES.get(row_key);
	if (!cached_truth) {
		return null;
	}

	row._stock_status_truth = cached_truth;
	if (cached_truth.hasItemAdded && !row.stock_status) {
		row.stock_status = cached_truth.stockStatus
			|| cached_truth.lastValidStockStatus
			|| cached_truth.last_valid_state?.message
			|| QUOTATION_STOCK_STATUS_FALLBACK;
	}

	return cached_truth;
}

function preserve_quotation_stock_statuses(frm) {
	for (const row of frm?.doc?.items || []) {
		restore_quotation_stock_status_from_row_cache(row);
	}
}

function get_quotation_stock_status_truth(row) {
	// Single source of truth for stock status stability. The grid field is only
	// a display projection of this object, so refresh/reload code cannot invent
	// a different status.
	if (!row._stock_status_truth) {
		const cached_truth = restore_quotation_stock_status_from_row_cache(row);
		if (cached_truth) {
			return cached_truth;
		}

		const has_item_added = Boolean(row.item_code || row.stock_status);
		row._stock_status_truth = make_quotation_stock_status_truth(row, has_item_added);
		cache_quotation_stock_status_truth(row, row._stock_status_truth);
	}

	return row._stock_status_truth;
}

function get_quotation_stock_status_fallback_message(truth) {
	return truth.lastValidStockStatus || truth.last_valid_state?.message || QUOTATION_STOCK_STATUS_FALLBACK;
}

function classify_quotation_stock_status_message(message) {
	const text = cstr(message);

	if (text.includes("In Stock")) {
		return QUOTATION_STOCK_STATUS.IN_STOCK;
	}
	if (text.includes("Partial") || text.includes("Low Stock")) {
		return QUOTATION_STOCK_STATUS.LOW_STOCK;
	}
	if (text.includes("Out of Stock")) {
		return QUOTATION_STOCK_STATUS.OUT_OF_STOCK;
	}
	if (text.includes("No Default")) {
		return QUOTATION_STOCK_STATUS.NO_WAREHOUSE;
	}
	if (text.includes("Invalid")) {
		return QUOTATION_STOCK_STATUS.INVALID_QTY;
	}

	return QUOTATION_STOCK_STATUS.EMPTY;
}

function is_quotation_stock_state_valid(state) {
	return Boolean(state && typeof state.message === "string" && state.status);
}

function normalize_quotation_stock_status_response(message, required_qty) {
	const response_message = cstr(message?.message || "");
	const available_qty = normalize_quotation_stock_quantity(message?.available_qty, 0);
	const response_required_qty = normalize_quotation_stock_quantity(message?.required_qty, required_qty);
	const status = message?.status || classify_quotation_stock_status_message(response_message);

	if (!response_message) {
		return make_quotation_stock_status_state(
			QUOTATION_STOCK_STATUS.API_ERROR,
			"Stock Check Failed",
			{ required_qty }
		);
	}

	return make_quotation_stock_status_state(
		status === "green"
			? QUOTATION_STOCK_STATUS.IN_STOCK
			: status === "blue"
				? QUOTATION_STOCK_STATUS.LOW_STOCK
				: status === "red"
					? QUOTATION_STOCK_STATUS.OUT_OF_STOCK
					: classify_quotation_stock_status_message(response_message),
		response_message,
		{
			available_qty,
			required_qty: response_required_qty,
			is_valid_stock: ["green", "blue", "red"].includes(status),
		}
	);
}

function apply_quotation_stock_status_state(frm, cdt, cdn, next_state) {
	const row = locals[cdt]?.[cdn];
	if (!row || !is_quotation_stock_state_valid(next_state)) {
		return;
	}

	const truth = get_quotation_stock_status_truth(row);
	let display_state = next_state;

	if (next_state.status === QUOTATION_STOCK_STATUS.EMPTY && !truth.hasItemAdded) {
		truth.current_state = next_state;
		truth.stockStatus = "";
		row.stock_status = "";
		cache_quotation_stock_status_truth(row, truth);
		refresh_quotation_stock_status_display(frm, cdn);
		return;
	}

	if (next_state.status !== QUOTATION_STOCK_STATUS.EMPTY) {
		truth.hasItemAdded = true;
	}

	// After the item has existed once, no later path may make stock_status blank.
	// Loading, invalid responses, and failed API calls reuse the last valid
	// status when possible, otherwise the stable fallback text is shown.
	if (
		truth.hasItemAdded
		&& (
			!display_state.message
			|| display_state.status === QUOTATION_STOCK_STATUS.LOADING
			|| display_state.status === QUOTATION_STOCK_STATUS.API_ERROR
			|| display_state.status === QUOTATION_STOCK_STATUS.INVALID_QTY
		)
	) {
		truth.current_state = next_state;
		display_state = make_quotation_stock_status_state(
			truth.last_valid_state?.status || QUOTATION_STOCK_STATUS.EMPTY,
			get_quotation_stock_status_fallback_message(truth)
		);
	} else {
		truth.current_state = next_state;
	}

	if (next_state.is_valid_stock) {
		truth.last_valid_state = next_state;
		truth.lastValidStockStatus = next_state.message;
	}

	if (next_state.available_qty !== undefined) {
		const available_stock_qty = normalize_quotation_stock_quantity(next_state.available_qty, 0);
		if (flt(row.available_stock_qty) !== available_stock_qty) {
			row.available_stock_qty = available_stock_qty;
			frappe.model.set_value(cdt, cdn, "available_stock_qty", available_stock_qty);
		}
	}

	truth.stockStatus = display_state.message || get_quotation_stock_status_fallback_message(truth);
	row.stock_status = truth.stockStatus;
	cache_quotation_stock_status_truth(row, truth);
	refresh_quotation_stock_status_display(frm, cdn);
}

async function update_quotation_stock_status(frm, cdt, cdn) {
	const row = locals[cdt]?.[cdn];

	if (!row) {
		return;
	}

	if (!row.item_code) {
		const truth = get_quotation_stock_status_truth(row);
		if (truth.hasItemAdded) {
			apply_quotation_stock_status_state(
				frm,
				cdt,
				cdn,
				make_quotation_stock_status_state(
					QUOTATION_STOCK_STATUS.EMPTY,
					get_quotation_stock_status_fallback_message(truth)
				)
			);
			return;
		}

		apply_quotation_stock_status_state(
			frm,
			cdt,
			cdn,
			make_quotation_stock_status_state(
				QUOTATION_STOCK_STATUS.EMPTY,
				QUOTATION_STOCK_STATUS_FALLBACK
			)
		);
		return;
	}

	get_quotation_stock_status_truth(row).hasItemAdded = true;

	if (!row.warehouse) {
		apply_quotation_stock_status_state(
			frm,
			cdt,
			cdn,
			make_quotation_stock_status_state(QUOTATION_STOCK_STATUS.NO_WAREHOUSE, "Select Warehouse")
		);
		return;
	}

	const required_qty = get_quotation_stock_required_qty(row);
	if (required_qty == null || required_qty <= 0) {
		apply_quotation_stock_status_state(
			frm,
			cdt,
			cdn,
			make_quotation_stock_status_state(
				QUOTATION_STOCK_STATUS.INVALID_QTY,
				QUOTATION_STOCK_STATUS_FALLBACK,
				{ required_qty }
			)
		);
		return;
	}

	const request_key = [
		row.item_code,
		row.warehouse || "",
		required_qty,
		frm.doc.company || "",
	].join("|");

	const truth = get_quotation_stock_status_truth(row);
	const request_id = truth.request_id + 1;
	truth.request_id = request_id;
	truth.request_key = request_key;

	apply_quotation_stock_status_state(
		frm,
		cdt,
		cdn,
		make_quotation_stock_status_state(
			QUOTATION_STOCK_STATUS.LOADING,
			"Checking Stock...",
			{ required_qty }
		)
	);

	try {
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
		const latest_truth = latest_row ? get_quotation_stock_status_truth(latest_row) : null;

		// Race guard: a slow older request must never overwrite the status from a
		// newer item/warehouse/qty request.
		if (
			!latest_row
			|| latest_truth.request_id !== request_id
			|| latest_truth.request_key !== request_key
		) {
			return;
		}

		apply_quotation_stock_status_state(
			frm,
			cdt,
			cdn,
			normalize_quotation_stock_status_response(r.message, required_qty)
		);
	} catch (error) {
		const latest_row = locals[cdt]?.[cdn];
		const latest_truth = latest_row ? get_quotation_stock_status_truth(latest_row) : null;

		if (
			!latest_row
			|| latest_truth.request_id !== request_id
			|| latest_truth.request_key !== request_key
		) {
			return;
		}

		apply_quotation_stock_status_state(
			frm,
			cdt,
			cdn,
			make_quotation_stock_status_state(
				QUOTATION_STOCK_STATUS.API_ERROR,
				"Stock Check Failed",
				{ required_qty }
			)
		);
		frappe.log_error?.(error, "Quotation stock status check failed");
	}
}

function normalize_quotation_stock_quantity(value, fallback = null) {
	if (value === null || value === undefined || value === "") {
		return fallback;
	}

	const numeric_value = Number(value);
	if (!Number.isFinite(numeric_value)) {
		return fallback;
	}

	return flt(numeric_value);
}

function get_quotation_stock_required_qty(row) {
	const stock_qty = normalize_quotation_stock_quantity(row.stock_qty);
	if (stock_qty !== null && stock_qty > 0) {
		return stock_qty;
	}

	const qty = normalize_quotation_stock_quantity(row.qty);
	if (qty === null) {
		return null;
	}

	const conversion_factor = normalize_quotation_stock_quantity(row.conversion_factor, 1) || 1;
	return qty * conversion_factor;
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

	preserve_quotation_stock_statuses(frm);
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

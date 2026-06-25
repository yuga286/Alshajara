const OPPORTUNITY_STOCK_STATUS = {
	LOADING: "loading",
	IN_STOCK: "in_stock",
	LOW_STOCK: "low_stock",
	OUT_OF_STOCK: "out_of_stock",
	NO_WAREHOUSE: "no_warehouse",
	INVALID_QTY: "invalid_qty",
	API_ERROR: "api_error",
	EMPTY: "empty",
};
const OPPORTUNITY_STOCK_STATUS_FALLBACK = "Stock status unavailable";
const OPPORTUNITY_STOCK_STATUS_ROW_STATES = new Map();

frappe.ui.form.on("Opportunity", {
	refresh(frm) {
		frm.custom_make_buttons = frm.custom_make_buttons || {};
		setup_opportunity_stock_status_formatter(frm);
		update_opportunity_stock_statuses(frm);
	},

	company(frm) {
		setup_opportunity_warehouse_query(frm);
		update_opportunity_stock_statuses(frm);
	},

	make_quotation(frm) {
		frappe.model.open_mapped_doc({
			method: "erpnext.crm.doctype.opportunity.opportunity.make_quotation",
			frm: frm,
			callback(doc) {
				if (frm.doc.project && doc) {
					doc.project = frm.doc.project;
				}
			},
		});
	},
});

frappe.ui.form.on("Opportunity", {
    before_save: async function (frm) {
        await sync_last_communication(frm);
	},
});

const opportunity_item_currency_field_labels = {
    Rate: "Rate (KWD)",
    AmountKwd: "Amount (KWD)",
    AmountQar: "Amount (QAR)",
};

function get_opportunity_item_currency_fieldname(label) {
    const item_meta = frappe.get_meta("Opportunity Item");
    const field = item_meta.fields.find((df) => df.label === label);
    return field ? field.fieldname : null;
}

async function convert_currency_amount(amount, from_currency, to_currency) {
    if (!amount) {
        return 0;
    }

    if (from_currency === to_currency) {
        return flt(amount);
    }

    const exchange_rate = await get_exchange_rate(from_currency, to_currency);
    return flt(amount) * flt(exchange_rate);
}

async function sync_opportunity_item_currency_fields(frm, row) {
    const rate_kwd_field = get_opportunity_item_currency_fieldname(
        opportunity_item_currency_field_labels.Rate
    );
    const amount_kwd_field = get_opportunity_item_currency_fieldname(
        opportunity_item_currency_field_labels.AmountKwd
    );
    const amount_qar_field = get_opportunity_item_currency_fieldname(
        opportunity_item_currency_field_labels.AmountQar
    );

    if (!rate_kwd_field && !amount_kwd_field && !amount_qar_field) {
        return;
    }

    const source_currency = frm.doc.currency || frappe.defaults.get_user_default("Currency");
    const row_rate = flt(row.rate || 0);
    const row_amount = flt(row.amount || flt(row.qty) * row_rate);

    if (rate_kwd_field) {
        row[rate_kwd_field] = await convert_currency_amount(row_rate, source_currency, "KWD");
    }

    if (amount_kwd_field) {
        row[amount_kwd_field] = await convert_currency_amount(row_amount, source_currency, "KWD");
    }

    if (amount_qar_field) {
        row[amount_qar_field] = await convert_currency_amount(row_amount, source_currency, "QAR");
    }
}

async function sync_opportunity_item_currency_fields_for_form(frm) {
    if (!frm.doc.items || !frm.doc.items.length) {
        return;
    }

    for (const row of frm.doc.items) {
        await sync_opportunity_item_currency_fields(frm, row);
    }

    preserve_opportunity_stock_statuses(frm);
    frm.refresh_field("items");
    refresh_opportunity_stock_statuses_display(frm);
}

async function sync_opportunity_amount_fields(frm) {
    const total = flt(frm.doc.total || 0);
    const base_total = flt(frm.doc.base_total || 0);

    // Ensure values are set before save completes
    await frm.set_value("opportunity_amount", total);
    await frm.set_value("base_opportunity_amount", base_total);
}

function update_opportunity_stock_statuses(frm) {
    return Promise.all((frm.doc.items || []).map((row) => {
        restore_opportunity_stock_status_from_row_cache(row);
        return update_opportunity_stock_status(frm, row.doctype, row.name);
    }));
}

function refresh_opportunity_stock_statuses_display(frm) {
    (frm.doc.items || []).forEach((row) => {
        restore_opportunity_stock_status_from_row_cache(row);
        refresh_opportunity_stock_status_display(frm, row.name);
    });
}

function setup_opportunity_stock_status_formatter(frm) {
	const grid = frm?.fields_dict?.items?.grid;
	apply_opportunity_items_grid_stock_docfields(grid);
	setup_opportunity_warehouse_query(frm);
}

function setup_opportunity_warehouse_query(frm) {
	const warehouse_field = frm?.fields_dict?.items?.grid?.get_field("warehouse");
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

function get_opportunity_items_grid_docfield(grid, fieldname) {
	return grid?.fields_map?.[fieldname]
		|| grid?.docfields?.find((field) => field.fieldname === fieldname)
		|| frappe.meta.get_docfield("Opportunity Item", fieldname);
}

function apply_opportunity_items_grid_stock_docfields(grid) {
	const stock_status_df = get_opportunity_items_grid_docfield(grid, "stock_status");
	if (stock_status_df) {
		stock_status_df.hidden = 0;
		stock_status_df.in_list_view = 1;
		stock_status_df.formatter = format_opportunity_stock_status;
		stock_status_df.read_only = 1;
	}
}

function format_opportunity_stock_status(value) {
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
		|| text.includes("Invalid")
		|| text.includes("Failed")
		|| text.includes("unavailable")
		|| text.includes("Select")
		|| text.includes("No Default")
	) {
		return `<span class="indicator orange">${escaped_value}</span>`;
	}

    return `<span class="indicator red">${escaped_value}</span>`;
}

function refresh_opportunity_stock_status_display(frm, cdn) {
    const grid = frm.fields_dict?.items?.grid;
    const grid_row = grid?.grid_rows_by_docname?.[cdn];

    if (grid_row) {
        grid_row.refresh_field("stock_status");
        return;
    }

    frm.refresh_field("items");
}

function make_opportunity_stock_status_state(status, message, options = {}) {
    return {
        status,
        message: cstr(message),
        available_qty: options.available_qty,
        required_qty: options.required_qty,
        is_valid_stock: Boolean(options.is_valid_stock),
    };
}

function get_opportunity_stock_status_row_keys(row) {
    if (!row) {
        return [];
    }

    const keys = [];
    if (row.name) {
        keys.push(`${row.doctype || "Opportunity Item"}:${row.name}`);
    }

    // Frappe can rebuild child rows while adding a new row. Keep a row-level
    // alias based on the existing row's stable table position and item context
    // so the previous row status can be restored after the rebuild.
    if (row.idx && (row.item_code || row.stock_status)) {
        keys.push([
            row.parent || "",
            row.parentfield || "items",
            row.idx,
            row.item_code || "",
            row.warehouse || "",
        ].join(":"));
    }

    return [...new Set(keys.filter(Boolean))];
}

function get_opportunity_stock_status_row_key(row) {
    return get_opportunity_stock_status_row_keys(row)[0] || "";
}

function make_opportunity_stock_status_truth(row, has_item_added) {
    const stock_status = has_item_added ? cstr(row.stock_status || OPPORTUNITY_STOCK_STATUS_FALLBACK) : "";
    return {
        hasItemAdded: has_item_added,
        stockStatus: stock_status,
        lastValidStockStatus: row.stock_status ? cstr(row.stock_status) : "",
        request_id: 0,
        request_key: "",
        current_state: make_opportunity_stock_status_state(
            OPPORTUNITY_STOCK_STATUS.EMPTY,
            stock_status
        ),
        last_valid_state: row.stock_status
            ? make_opportunity_stock_status_state(
                classify_opportunity_stock_status_message(row.stock_status),
                row.stock_status,
                { is_valid_stock: true }
            )
            : null,
    };
}

function cache_opportunity_stock_status_truth(row, truth) {
    for (const row_key of get_opportunity_stock_status_row_keys(row)) {
        OPPORTUNITY_STOCK_STATUS_ROW_STATES.set(row_key, truth);
    }
}

function restore_opportunity_stock_status_from_row_cache(row) {
    const cached_truth = get_opportunity_stock_status_row_keys(row)
        .map((row_key) => OPPORTUNITY_STOCK_STATUS_ROW_STATES.get(row_key))
        .find(Boolean);
    if (!cached_truth) {
        return null;
    }

    row._stock_status_truth = cached_truth;
    if (cached_truth.hasItemAdded && !row.stock_status) {
        row.stock_status = cached_truth.stockStatus
            || cached_truth.lastValidStockStatus
            || cached_truth.last_valid_state?.message
            || OPPORTUNITY_STOCK_STATUS_FALLBACK;
    }
    cache_opportunity_stock_status_truth(row, cached_truth);

    return cached_truth;
}

function preserve_opportunity_stock_statuses(frm) {
    for (const row of frm?.doc?.items || []) {
        restore_opportunity_stock_status_from_row_cache(row);
    }
}

function get_opportunity_stock_status_truth(row) {
    // Single source of truth for Opportunity stock status. The visible field is
    // updated only from this object to prevent refreshes and async calls from
    // producing conflicting UI states.
    if (!row._stock_status_truth) {
        const cached_truth = restore_opportunity_stock_status_from_row_cache(row);
        if (cached_truth) {
            return cached_truth;
        }

        const has_item_added = Boolean(row.item_code || row.stock_status);
        row._stock_status_truth = make_opportunity_stock_status_truth(row, has_item_added);
        cache_opportunity_stock_status_truth(row, row._stock_status_truth);
    }

    return row._stock_status_truth;
}

function get_opportunity_stock_status_fallback_message(truth) {
    return truth.lastValidStockStatus || truth.last_valid_state?.message || OPPORTUNITY_STOCK_STATUS_FALLBACK;
}

function classify_opportunity_stock_status_message(message) {
    const text = cstr(message);
    if (text.includes("In Stock")) return OPPORTUNITY_STOCK_STATUS.IN_STOCK;
    if (text.includes("Partial") || text.includes("Low Stock")) return OPPORTUNITY_STOCK_STATUS.LOW_STOCK;
    if (text.includes("Out of Stock")) return OPPORTUNITY_STOCK_STATUS.OUT_OF_STOCK;
    if (text.includes("No Default")) return OPPORTUNITY_STOCK_STATUS.NO_WAREHOUSE;
    if (text.includes("Invalid")) return OPPORTUNITY_STOCK_STATUS.INVALID_QTY;
    return OPPORTUNITY_STOCK_STATUS.EMPTY;
}

function is_opportunity_stock_state_valid(state) {
    return Boolean(state && typeof state.message === "string" && state.status);
}

function normalize_opportunity_stock_status_response(message, required_qty) {
    const response_message = cstr(message?.message || "");
    const available_qty = normalize_opportunity_stock_quantity(message?.available_qty, 0);
    const response_required_qty = normalize_opportunity_stock_quantity(message?.required_qty, required_qty);
    const status = message?.status || classify_opportunity_stock_status_message(response_message);

    if (!response_message) {
        return make_opportunity_stock_status_state(
            OPPORTUNITY_STOCK_STATUS.API_ERROR,
            "Stock Check Failed",
            { required_qty }
        );
    }

    return make_opportunity_stock_status_state(
        status === "green"
            ? OPPORTUNITY_STOCK_STATUS.IN_STOCK
            : status === "blue"
                ? OPPORTUNITY_STOCK_STATUS.LOW_STOCK
                : status === "red"
                    ? OPPORTUNITY_STOCK_STATUS.OUT_OF_STOCK
                    : classify_opportunity_stock_status_message(response_message),
        response_message,
        {
            available_qty,
            required_qty: response_required_qty,
            is_valid_stock: ["green", "blue", "red"].includes(status),
        }
    );
}

function apply_opportunity_stock_status_state(frm, cdt, cdn, next_state) {
    const row = locals[cdt]?.[cdn];
    if (!row || !is_opportunity_stock_state_valid(next_state)) {
        return;
    }

    const truth = get_opportunity_stock_status_truth(row);
    let display_state = next_state;

    if (next_state.status === OPPORTUNITY_STOCK_STATUS.EMPTY && !truth.hasItemAdded) {
        truth.current_state = next_state;
        truth.stockStatus = "";
        row.stock_status = "";
        cache_opportunity_stock_status_truth(row, truth);
        refresh_opportunity_stock_status_display(frm, cdn);
        return;
    }

    if (next_state.status !== OPPORTUNITY_STOCK_STATUS.EMPTY) {
        truth.hasItemAdded = true;
    }

    // After an item has been added, every code path must leave one non-empty
    // stock status in the existing field. Loading, API failures, and invalid
    // quantities reuse the last valid value or the fallback text.
    if (
        truth.hasItemAdded
        && (
            !display_state.message
            || display_state.status === OPPORTUNITY_STOCK_STATUS.LOADING
            || display_state.status === OPPORTUNITY_STOCK_STATUS.API_ERROR
            || display_state.status === OPPORTUNITY_STOCK_STATUS.INVALID_QTY
        )
    ) {
        truth.current_state = next_state;
        display_state = make_opportunity_stock_status_state(
            truth.last_valid_state?.status || OPPORTUNITY_STOCK_STATUS.EMPTY,
            get_opportunity_stock_status_fallback_message(truth)
        );
    } else {
        truth.current_state = next_state;
    }

    if (next_state.is_valid_stock) {
        truth.last_valid_state = next_state;
        truth.lastValidStockStatus = next_state.message;
    }

    truth.stockStatus = display_state.message || get_opportunity_stock_status_fallback_message(truth);
    row.stock_status = truth.stockStatus;
    cache_opportunity_stock_status_truth(row, truth);
    refresh_opportunity_stock_status_display(frm, cdn);
}

async function update_opportunity_stock_status(frm, cdt, cdn) {
    const row = locals[cdt]?.[cdn];

    if (!row) {
        return;
    }

    if (!row.item_code) {
        const truth = get_opportunity_stock_status_truth(row);
        if (truth.hasItemAdded) {
            apply_opportunity_stock_status_state(
                frm,
                cdt,
                cdn,
                make_opportunity_stock_status_state(
                    OPPORTUNITY_STOCK_STATUS.EMPTY,
                    get_opportunity_stock_status_fallback_message(truth)
                )
            );
            return;
        }

        apply_opportunity_stock_status_state(
            frm,
            cdt,
            cdn,
            make_opportunity_stock_status_state(
                OPPORTUNITY_STOCK_STATUS.EMPTY,
                OPPORTUNITY_STOCK_STATUS_FALLBACK
            )
        );
        return;
    }

    get_opportunity_stock_status_truth(row).hasItemAdded = true;

    if (!row.warehouse) {
        apply_opportunity_stock_status_state(
            frm,
            cdt,
            cdn,
            make_opportunity_stock_status_state(
                OPPORTUNITY_STOCK_STATUS.NO_WAREHOUSE,
                "Select Warehouse"
            )
        );
        return;
    }

    const required_qty = get_opportunity_stock_required_qty(row);
    if (required_qty == null || required_qty <= 0) {
        apply_opportunity_stock_status_state(
            frm,
            cdt,
            cdn,
            make_opportunity_stock_status_state(
                OPPORTUNITY_STOCK_STATUS.INVALID_QTY,
                OPPORTUNITY_STOCK_STATUS_FALLBACK,
                { required_qty }
            )
        );
        return;
    }

    const request_key = [row.item_code, row.warehouse || "", required_qty, frm.doc.company || ""].join("|");
    const truth = get_opportunity_stock_status_truth(row);
    const request_id = truth.request_id + 1;
    truth.request_id = request_id;
    truth.request_key = request_key;

    apply_opportunity_stock_status_state(
        frm,
        cdt,
        cdn,
        make_opportunity_stock_status_state(
            OPPORTUNITY_STOCK_STATUS.LOADING,
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
        const latest_truth = latest_row ? get_opportunity_stock_status_truth(latest_row) : null;
        if (!latest_row || latest_truth.request_id !== request_id || latest_truth.request_key !== request_key) {
            return;
        }

        apply_opportunity_stock_status_state(
            frm,
            cdt,
            cdn,
            normalize_opportunity_stock_status_response(r.message, required_qty)
        );
    } catch (error) {
        const latest_row = locals[cdt]?.[cdn];
        const latest_truth = latest_row ? get_opportunity_stock_status_truth(latest_row) : null;
        if (!latest_row || latest_truth.request_id !== request_id || latest_truth.request_key !== request_key) {
            return;
        }

        apply_opportunity_stock_status_state(
            frm,
            cdt,
            cdn,
            make_opportunity_stock_status_state(
                OPPORTUNITY_STOCK_STATUS.API_ERROR,
                "Stock Check Failed",
                { required_qty }
            )
        );
        frappe.log_error?.(error, "Opportunity stock status check failed");
    }
}

function normalize_opportunity_stock_quantity(value, fallback = null) {
    if (value === null || value === undefined || value === "") {
        return fallback;
    }

    const numeric_value = Number(value);
    return Number.isFinite(numeric_value) ? flt(numeric_value) : fallback;
}

function get_opportunity_stock_required_qty(row) {
    const stock_qty = normalize_opportunity_stock_quantity(row.stock_qty);
    if (stock_qty !== null && stock_qty > 0) {
        return stock_qty;
    }

    const qty = normalize_opportunity_stock_quantity(row.qty);
    if (qty === null) {
        return null;
    }

    const conversion_factor = normalize_opportunity_stock_quantity(row.conversion_factor, 1) || 1;
    return qty * conversion_factor;
}

function schedule_opportunity_stock_status_update(frm, cdt, cdn) {
    setTimeout(() => {
        update_opportunity_stock_status(frm, cdt, cdn);
    }, 0);
}

function schedule_opportunity_item_stock_status_update(frm, cdt, cdn) {
    schedule_opportunity_stock_status_update(frm, cdt, cdn);
    setTimeout(() => {
        update_opportunity_stock_status(frm, cdt, cdn);
    }, 500);
}

function schedule_opportunity_stock_statuses_update(frm) {
	setTimeout(() => {
		update_opportunity_stock_statuses(frm);
	}, 0);
}

async function sync_last_communication(frm) {
	if (!frm.doc.notes || frm.doc.notes.length === 0) {
		await frm.set_value("last_communicated_note", "");
		await frm.set_value("last_communicated_date", "");
		return;
	}

	// Filter rows having added_on
	let valid_notes = frm.doc.notes.filter((row) => row.added_on);

	if (valid_notes.length === 0) {
		return;
	}

	// Sort by added_on DESC
	valid_notes.sort((a, b) => {
		return new Date(b.added_on) - new Date(a.added_on);
	});

	let latest = valid_notes[0];

	await frm.set_value("last_communicated_note", latest.note || "");
	await frm.set_value("last_communicated_date", latest.added_on || "");
}

// Render address and contact when opportunity is from lead and party name is set
frappe.ui.form.on("Opportunity", {

onload(frm) {

    if (
        frm.doc.opportunity_from === "Lead"
        && frm.doc.party_name
    ) {

        frappe.contacts.render_address_and_contact(frm);

    }

},

refresh(frm) {

    if (
        frm.doc.opportunity_from === "Lead"
        && frm.doc.party_name
    ) {

        frappe.contacts.render_address_and_contact(frm);

    }

}

});

frappe.ui.form.on("Opportunity", {
    total(frm) {
        sync_opportunity_amount_fields(frm);
    },

    base_total(frm) {
        sync_opportunity_amount_fields(frm);
    },

    conversion_rate(frm) {
        sync_opportunity_amount_fields(frm);
    },

    currency(frm) {
        sync_opportunity_amount_fields(frm);
    }
});


async function get_exchange_rate(
    from_currency,
    to_currency
) {

    if (
        from_currency === to_currency
    ) {
        return 1;
    }

    const response = await fetch(
        `https://open.er-api.com/v6/latest/${from_currency}`
    );

    const data = await response.json();

    return data.rates[to_currency] || 1;
}


async function convert_row_currency(
    frm,
    row
) {

    if (
        !row.original_rate ||
        !row.original_currency
    ) {
        return;
    }

    const current_currency =
        frm.doc.currency;

    let converted_rate =
        flt(row.original_rate);

    if (
        row.original_currency !==
        current_currency
    ) {

        const exchange_rate =
            await get_exchange_rate(
                row.original_currency,
                current_currency
            );

        converted_rate =
            flt(row.original_rate) *
            flt(exchange_rate);

    }

    // Set converted value
    await frappe.model.set_value(
        row.doctype,
        row.name,
        "rate",
        converted_rate
    );

    await sync_opportunity_item_currency_fields(
        frm,
        row
    );

    preserve_opportunity_stock_statuses(frm);
    frm.refresh_field(
        "items"
    );
    refresh_opportunity_stock_statuses_display(frm);

}


frappe.ui.form.on(
    "Opportunity Item",
    {
        async item_code(frm, cdt, cdn) {

            const row =
                locals[cdt][cdn];

            schedule_opportunity_item_stock_status_update(frm, cdt, cdn);

            if (!row.item_code) {
                return;
            }

            frappe.call({

                method:
                    "frappe.client.get_value",

                args: {

                    doctype:
                        "Item Price",

                    filters: {

                        item_code:
                            row.item_code,

                        price_list:
                            "Standard Selling",

                        selling: 1
                    },

                    fieldname: [
                        "price_list_rate",
                        "currency"
                    ]
                },

                callback: async function(r) {

                    if (!r.message) {
                        return;
                    }

                    // SAVE ORIGINAL VALUES
                    row.original_rate =
                        r.message.price_list_rate;

                    row.original_currency =
                        r.message.currency;

                    // IMPORTANT
                    frm.dirty();

                    await convert_row_currency(
                        frm,
                        row
                    );

                    schedule_opportunity_stock_status_update(frm, cdt, cdn);

                }

            });

        }

    }
);

frappe.ui.form.on(
    "Opportunity Item",
    {
        uom(frm, cdt, cdn) {
            schedule_opportunity_stock_status_update(frm, cdt, cdn);
        },
        conversion_factor(frm, cdt, cdn) {
            schedule_opportunity_stock_status_update(frm, cdt, cdn);
        },
        stock_qty(frm, cdt, cdn) {
            schedule_opportunity_stock_status_update(frm, cdt, cdn);
        },
        qty(frm, cdt, cdn) {
            schedule_opportunity_stock_status_update(frm, cdt, cdn);
        },
        warehouse(frm, cdt, cdn) {
            schedule_opportunity_stock_status_update(frm, cdt, cdn);
            schedule_opportunity_stock_statuses_update(frm);
        },

    }
);


frappe.ui.form.on(
    "Opportunity",
    {

        async currency(frm) {

            if (!frm.doc.items) {
                return;
            }

            for (const row of frm.doc.items) {

                await convert_row_currency(
                    frm,
                    row
                );

            }

            preserve_opportunity_stock_statuses(frm);
            frm.refresh_field(
                "items"
            );
            refresh_opportunity_stock_statuses_display(frm);

        }

    }
);

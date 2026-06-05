frappe.ui.form.on("Opportunity", {
	refresh(frm) {
		frm.custom_make_buttons = frm.custom_make_buttons || {};
        setup_opportunity_stock_status_formatter();
        update_opportunity_stock_statuses(frm);
	},

    company(frm) {
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

    frm.refresh_field("items");
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
        return update_opportunity_stock_status(frm, row.doctype, row.name);
    }));
}

function setup_opportunity_stock_status_formatter() {
    const df = frappe.meta.get_docfield("Opportunity Item", "stock_status");
    if (!df) return;

    df.formatter = format_opportunity_stock_status;
}

function format_opportunity_stock_status(value) {
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

function refresh_opportunity_stock_status_display(frm, cdn) {
    const grid = frm.fields_dict?.items?.grid;
    const grid_row = grid?.grid_rows_by_docname?.[cdn];

    if (grid_row) {
        const row = locals[grid_row.doc?.doctype]?.[cdn] || grid_row.doc;
        const html = format_opportunity_stock_status(row?.stock_status);

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

async function set_opportunity_stock_status(frm, cdt, cdn, value) {
    const row = locals[cdt]?.[cdn];
    if (row) {
        row.stock_status = value;
    }

    refresh_opportunity_stock_status_display(frm, cdn);
}

async function update_opportunity_stock_status(frm, cdt, cdn) {
    const row = locals[cdt]?.[cdn];

    if (!row) {
        return;
    }

    if (!row.item_code) {
        await set_opportunity_stock_status(frm, cdt, cdn, "");
        return;
    }

    const r = await frappe.call({
        method: "alshajaraapp.api.comman.get_stock_status",
        args: {
            item_code: row.item_code,
            company: frm.doc.company,
            warehouse: row.warehouse,
            qty: row.qty,
        },
    });

    await set_opportunity_stock_status(frm, cdt, cdn, r.message?.message || "");
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

    frm.refresh_field(
        "items"
    );

}


frappe.ui.form.on(
    "Opportunity Item",
    {
        async item_code(frm, cdt, cdn) {

            const row =
                locals[cdt][cdn];

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

                    update_opportunity_stock_status(frm, cdt, cdn);

                }

            });

        }

    }
);

frappe.ui.form.on(
    "Opportunity Item",
    {
        qty(frm, cdt, cdn) {
            update_opportunity_stock_status(frm, cdt, cdn);
        },
        warehouse(frm, cdt, cdn) {
            setTimeout(() => {
                update_opportunity_stock_status(frm, cdt, cdn);
            }, 0);
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

            frm.refresh_field(
                "items"
            );

        }

    }
);

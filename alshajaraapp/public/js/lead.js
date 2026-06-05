
frappe.ui.form.on("Lead", {

    refresh(frm) {

        setTimeout(() => {

            frm.remove_custom_button("Opportunity", "Create");

            frm.add_custom_button("Opportunity", () => {

                frappe.model.open_mapped_doc({
                    method: "erpnext.crm.doctype.lead.lead.make_opportunity",
                    frm: frm
                });

            }, "Create");

        }, 500);

    }

});
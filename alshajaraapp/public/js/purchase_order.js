frappe.ui.form.on("Purchase Order", {
	before_workflow_action(frm) {
		const action = frm.selected_workflow_action;

		if (["Send for Re-verification", "Cancel"].includes(action) && !frm.doc.approval_comment) {
			frappe.throw("Comment / Reason is mandatory for this action.");
		}
	},
});

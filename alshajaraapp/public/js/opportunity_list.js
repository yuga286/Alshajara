frappe.listview_settings['Opportunity'] = {
    get_indicator(doc) {

        if (doc.stock_status_text === "In Stock") {
            return ["In Stock", "green", "stock_status_text,=,In Stock"];
        }

        if (doc.stock_status_text === "Partial Stock") {
            return ["Partial Stock", "orange", "stock_status_text,=,Partial Stock"];
        }

        if (doc.stock_status_text === "Out of Stock") {
            return ["Out of Stock", "red", "stock_status_text,=,Out of Stock"];
        }
    }
};
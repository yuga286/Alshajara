
frappe.listview_settings['Opportunity'] = {
     formatters: {
        stock_status(value) {
            if (value === "In Stock") {
                return `<span class="indicator green"></span> ${value}`;
            }

            if (value === "Low Stock") {
                return `<span class="indicator orange"></span> ${value}`;
            }

            if (value === "Out of Stock") {
                return `<span class="indicator red"></span> ${value}`;
            }

            return value;
        }
    }
};
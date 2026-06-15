app_name = "alshajaraapp"
app_title = "Alshajaraapp"
app_publisher = "Chirag Joshi"
app_description = "Alshajara App"
app_email = "chirag.joshi@vigisolvo.com"
app_license = "mit"


fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "Alshajaraapp"]]},
    {"dt": "Property Setter", "filters": [["module", "=", "Alshajaraapp"]]},

]

doctype_js = {
    "Lead": "public/js/lead.js",
    "Quotation": "public/js/quotation.js",
    "Opportunity": "public/js/opportunity.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Purchase Order": "public/js/purchase_order.js",
    "Item": "public/js/item.js",
    "Price List": "public/js/price_list.js",
}

doctype_list_js = {
    "Quotation": "public/js/quotation_list.js",
    "Opportunity": "public/js/opportunity_list.js"
}

app_include_css = [
    "/assets/alshajaraapp/css/navbar.css",
]

after_migrate = [
    "alshajaraapp.patches.set_sales_order_purchase_order_field_order.apply_sales_order_purchase_order_field_order",
]

doc_events = {
    "Quotation": {
        "autoname": "alshajaraapp.api.quotation.set_custom_quotation_name",
        "before_insert": "alshajaraapp.api.quotation.reset_barcode_on_amend",
        "before_validate": "alshajaraapp.api.quotation.ensure_quotation_conversion_rate",
        "before_save": "alshajaraapp.api.quotation.compute_and_persist_quotation_profit",
        "after_insert": "alshajaraapp.api.quotation.generate_quotation_barcode",
        "on_submit": "alshajaraapp.quotation.quotation.create_purchase_orders_for_shortages",
    },
    "Sales Order": {
        "before_insert": "alshajaraapp.api.comman.reset_document_barcode_on_amend",
        "after_insert": "alshajaraapp.api.comman.generate_document_barcode",
        "on_submit": "alshajaraapp.sales_order.sales_order.create_purchase_orders_for_shortages",
    },
    "Sales Invoice": {
        "before_insert": "alshajaraapp.api.comman.reset_document_barcode_on_amend",
        "after_insert": "alshajaraapp.api.comman.generate_document_barcode",
    },
    "Delivery Note": {
        "before_insert": "alshajaraapp.api.comman.reset_document_barcode_on_amend",
        "after_insert": "alshajaraapp.api.comman.generate_document_barcode",
    },
    "Purchase Order": {
        "before_insert": "alshajaraapp.api.comman.reset_document_barcode_on_amend",
        "after_insert": "alshajaraapp.api.comman.generate_document_barcode",
    },
    "Purchase Invoice": {
        "before_insert": "alshajaraapp.api.comman.reset_document_barcode_on_amend",
        "after_insert": "alshajaraapp.api.comman.generate_document_barcode",
    },
    "Purchase Receipt": {
        "before_insert": "alshajaraapp.api.comman.reset_document_barcode_on_amend",
        "after_insert": "alshajaraapp.api.comman.generate_document_barcode",
    },
    "Request for Quotation": {
        "before_insert": "alshajaraapp.api.comman.reset_document_barcode_on_amend",
        "after_insert": "alshajaraapp.api.comman.generate_document_barcode",
    },
    "Payment Entry": {
        "before_insert": "alshajaraapp.api.comman.reset_document_barcode_on_amend",
        "after_insert": "alshajaraapp.api.comman.generate_document_barcode",
    },
    "Comment": {
        "after_insert": "alshajaraapp.api.todo_comment.update_todo_latest_comment"
    }
}

override_whitelisted_methods = {
    "erpnext.selling.doctype.quotation.quotation.make_sales_order":
        "alshajaraapp.api.quotation.make_sales_order_with_shipping_status",
    "erpnext.crm.doctype.opportunity.opportunity.make_quotation":
        "alshajaraapp.api.opportunity.make_quotation",
    "erpnext.buying.doctype.supplier_quotation.supplier_quotation.make_purchase_order":
        "alshajaraapp.api.supplier_quotation.make_purchase_order",
    "erpnext.crm.doctype.lead.lead.make_opportunity":
        "alshajaraapp.api.opportunity.custom_make_opportunity"
}



# app_include_js = [
#     "/assets/alshajaraapp/js/quotation_list.js"
# ]


# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "alshajaraapp",
# 		"logo": "/assets/alshajaraapp/logo.png",
# 		"title": "Alshajaraapp",
# 		"route": "/alshajaraapp",
# 		"has_permission": "alshajaraapp.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/alshajaraapp/css/alshajaraapp.css"
# app_include_js = "/assets/alshajaraapp/js/alshajaraapp.js"

# include js, css files in header of web template
# web_include_css = "/assets/alshajaraapp/css/alshajaraapp.css"
# web_include_js = "/assets/alshajaraapp/js/alshajaraapp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "alshajaraapp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "alshajaraapp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "alshajaraapp.utils.jinja_methods",
# 	"filters": "alshajaraapp.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "alshajaraapp.install.before_install"
# after_install = "alshajaraapp.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "alshajaraapp.uninstall.before_uninstall"
# after_uninstall = "alshajaraapp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "alshajaraapp.utils.before_app_install"
# after_app_install = "alshajaraapp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "alshajaraapp.utils.before_app_uninstall"
# after_app_uninstall = "alshajaraapp.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "alshajaraapp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"alshajaraapp.tasks.all"
# 	],
# 	"daily": [
# 		"alshajaraapp.tasks.daily"
# 	],
# 	"hourly": [
# 		"alshajaraapp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"alshajaraapp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"alshajaraapp.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "alshajaraapp.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "alshajaraapp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "alshajaraapp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["alshajaraapp.utils.before_request"]
# after_request = ["alshajaraapp.utils.after_request"]

# Job Events
# ----------
# before_job = ["alshajaraapp.utils.before_job"]
# after_job = ["alshajaraapp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"alshajaraapp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

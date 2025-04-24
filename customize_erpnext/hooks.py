app_name = "customize_erpnext"
app_title = "Customize Erpnext"
app_publisher = "IT Team - TIQN"
app_description = "Customize Erpnext"
app_email = "it@tiqn.com.vn"
app_license = "mit"

# Sau khi sửa file hook.py chạy các lệnh sau:
#  
#  bench --site erp-sonnt.tiqn.local clear-cache 
#  bench build
#  bench --site erp-sonnt.tiqn.local migrate
#  bench restart

# Apps
# ------------------

# In hooks.py or using Customize Form
custom_fields = {
    "Stock Entry Multi Work Orders": [
        {
            "fieldname": "stock_entries",
            "fieldtype": "Long Text",
            "label": "Created Stock Entries",
            "read_only": 1,
            "hidden": 0,
            "insert_after": "color"
        }
    ],
    "Stock Entry": [
        {
            "fieldname": "multi_work_order",
            "fieldtype": "Link",
            "label": "Multi Work Order",
            "options": "Stock Entry Multi Work Orders",
            "insert_after": "work_order"
        }
    ]
}

# Thêm hook xử lý trước khi import
data_import_before_insert = {
    "Item Attribute Value": "customize_erpnext.override_methods.handle_import_attr_colors.handle_item_attribute_value_import"
}

# Trong hooks.py
data_import_before_import = [
    "customize_erpnext.override_methods.item_attribute_import.before_import"
]

data_import_after_import = [
    "customize_erpnext.override_methods.item_attribute_import.after_import"
]
# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "customize_erpnext",
# 		"logo": "/assets/customize_erpnext/logo.png",
# 		"title": "Customize Erpnext",
# 		"route": "/customize_erpnext",
# 		"has_permission": "customize_erpnext.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/customize_erpnext/css/customize_erpnext.css"
# app_include_js = "/assets/customize_erpnext/js/customize_erpnext.js"

# include js, css files in header of web template
# web_include_css = "/assets/customize_erpnext/css/customize_erpnext.css"
# web_include_js = "/assets/customize_erpnext/js/customize_erpnext.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "customize_erpnext/public/scss/website"

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
# app_include_icons = "customize_erpnext/public/icons.svg"

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
# 	"methods": "customize_erpnext.utils.jinja_methods",
# 	"filters": "customize_erpnext.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "customize_erpnext.install.before_install"
# after_install = "customize_erpnext.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "customize_erpnext.uninstall.before_uninstall"
# after_uninstall = "customize_erpnext.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "customize_erpnext.utils.before_app_install"
# after_app_install = "customize_erpnext.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "customize_erpnext.utils.before_app_uninstall"
# after_app_uninstall = "customize_erpnext.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "customize_erpnext.notifications.get_notification_config"

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
# 		"customize_erpnext.tasks.all"
# 	],
# 	"daily": [
# 		"customize_erpnext.tasks.daily"
# 	],
# 	"hourly": [
# 		"customize_erpnext.tasks.hourly"
# 	],
# 	"weekly": [
# 		"customize_erpnext.tasks.weekly"
# 	],
# 	"monthly": [
# 		"customize_erpnext.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "customize_erpnext.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "customize_erpnext.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "customize_erpnext.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["customize_erpnext.utils.before_request"]
# after_request = ["customize_erpnext.utils.after_request"]

# Job Events
# ----------
# before_job = ["customize_erpnext.utils.before_job"]
# after_job = ["customize_erpnext.utils.after_job"]

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
# 	"customize_erpnext.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }


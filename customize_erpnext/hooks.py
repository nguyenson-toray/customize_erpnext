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


# ------------------
# Customize các js script cho các DocType mặc định của erpnext
doctype_js = {
    "Stock Entry": [
        "public/js/custom_scripts/stock_entry.js",
        "public/js/custom_scripts/stock_entry_quick_import.js"
    ],
    "BOM": "public/js/custom_scripts/bom.js",
    "Item": [
        "public/js/custom_scripts/item.js",
        "public/js/custom_scripts/item_show_multiple_variants_dialog.js"
    ],
    "Material Request" :  "public/js/custom_scripts/material_request.js",
    "Purchase Order" :  "public/js/custom_scripts/purchase_order.js",
    "Item Attribute": [
        "public/js/custom_scripts/item_attribute.js",
        "public/js/custom_scripts/item_attribute_import.js"
    ],
    "Item Attribute Value": "public/js/custom_scripts/item_attribute.js",
    "Sales Order": "public/js/custom_scripts/sales_order_sum_qty.js",
    "Production Plan" : "public/js/custom_scripts/production_plan.js",
    "Stock Reconciliation" : "public/js/custom_scripts/stock_reconciliation.js",
    # Thêm các doctype khác  
}

# List view customizations
doctype_list_js = {
    "Item": "public/js/custom_scripts/item_list.js",
    "Stock Entry": "public/js/custom_scripts/stock_entry_list.js",
}
 
# Hướng dẫn sử dụng fixtures để export từ site A và import vào site B
#  Site A
    # 1 : Chỉnh sửa Doctype, field, workspace Web UI
    # 2 : export ra thư mục fixture chứa các file json : bench --site erp-sonnt.tiqn.local export-fixtures
    #     Commit & push lên git
#  Site B
    # 1 : Pull code về
    # 2 : Chạy lệnh bench --site erp.tiqn.local clear-cache
    # 3 : Chạy lệnh bench --site erpt.tiqn.local migrate    
    # hoặc cho 1 app cụ thể : bench --site erp.tiqn.local import-fixtures --app customize_erpnext  
fixtures = [ 
     {
        "doctype": "Custom Field",
        "filters": [
            [
                "dt",
                "in",
                [
                    "Stock Entry",
                    "Sales Order Item", 
                    "Sales Order", 
                    "BOM Item", 
                    "Material Request Item",
                    "Production Plan",
                    "Employee",
                    "Stock Entry Detail",
                    "Stock Reconciliation",
                    "Stock Reconciliation Item",
                    "Stock Ledger Entry",
                    "Customer"
                ]
            ],
            [
                "fieldname",
                "like",
                "custom%"  # Lấy tất cả field có fieldname bắt đầu bằng "custom"
            ]
        ]
    },
    # Custom Workspace
    {
        "doctype": "Workspace",
        "filters": [
            # Chỉ export một số workspace cụ thể
            ["name", "in", ["Stock"]] 
            # Để trống filter nếu muốn export tất cả
        ]
    },
    # Property Setter
    {
        "doctype": "Property Setter",
        "filters": [
            ["doc_type", "in", [
                "Item",
                "Stock Entry Detail",
                "Stock Reconciliation",
                "Stock Reconciliation Item"
                ]]
        ]
    },
    # List View Settings
    {
        "doctype": "List View Settings",
        "filters": {
            "name": ["in", [
                "Item",
                "Stock Entry", 
                "Stock Reconciliation"
                # Add your doctypes here
            ]]
        }
    },
    {
        "doctype": "Print Format",
        "filters": {
            "module": "Customize Erpnext"
        }
    }
]



data_import_before_import = [
    "customize_erpnext.override_methods.item_attribute_import.before_import"
]


# Scheduler Events

scheduler_events = {
    "daily": [
        # Daily attendance completion - chạy lúc 6:00 AM mỗi ngày
        "customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.auto_daily_attendance_completion",
        
        # Auto submit Custom Attendance - chạy lúc 7:00 AM mỗi ngày  
        "customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.auto_submit_custom_attendance"
    ],
    
    "hourly": [
        # Smart auto update - chỉ chạy khi shift kết thúc + tolerance
        "customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.smart_auto_update_custom_attendance"
    ],
    
    # Cron-based schedules (optional - có thể customize thời gian cụ thể)
    "cron": {
        # Daily completion lúc 3:00 AM
        "0 3 * * *": [
            "customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.auto_daily_attendance_completion"
        ],
        
        # Auto submit lúc 6:00 AM
        "0 6 * * *": [
            "customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.auto_submit_custom_attendance"
        ],
        
        # Smart auto update mỗi 30 phút (có thể adjust)
        "*/30 * * * *": [
            "customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.smart_auto_update_custom_attendance"
        ]
    }
}
 
# DocType Class
# ---------------
# Override standard doctype classes
# override_doctype_class = {
#     "Stock Reconciliation": "customize_erpnext.override_methods.stock_reconciliation.custom_stock_reconciliation.CustomStockReconciliation"
# }
# Document Events
doc_events = {
    "Employee Checkin": {
        "on_update": "customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.on_checkin_update",
        "after_insert": "customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.on_checkin_creation",
    },
    
    "Shift Type": {
        "on_update": "customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.on_shift_update"
    },
    # Add custom_invoice_number field of Stock Entry and Stock Reconciliation to Stock Ledger Entry
    "Stock Entry": {
        "on_submit": "customize_erpnext.api.stock_ledger.update_stock_ledger_invoice_number_receive_date.update_stock_ledger_invoice_number_receive_date"
    },
    "Stock Reconciliation": {
        "on_submit": "customize_erpnext.api.stock_ledger.update_stock_ledger_invoice_number_receive_date.update_stock_ledger_invoice_number_receive_date"
    }
}
 

# Fixtures (for initial setup)
# fixtures = [
#     {
#         "doctype": "Custom Field",
#         "filters": {
#             "dt": ["in", ["Employee"]]
#         }
#     }
# ]

# boot_session = "customize_erpnext.override_methods.employee_checkin_or.apply_monkey_patch"
# Hook on document methods and events
# doc_events = {
#     # "Item": {
#     #     "after_insert": "customize_erpnext.doc_events.item.update_item_variant" 
#     # }
# } 
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

# after_install = "customize_erpnext.setup.remove_depends_on"
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
#     "hrms.hr.doctype.employee_checkin.employee_checkin.calculate_working_hours": "customize_erpnext.override_methods.employee_checkin_or.calculate_working_hours"
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

# Chạy khi session boot lên
# boot_session = "customize_erpnext.override_methods.employee_checkin_or.apply_monkey_patch"


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




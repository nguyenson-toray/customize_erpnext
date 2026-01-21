app_name = "customize_erpnext"
app_title = "Customize Erpnext"
app_publisher = "IT Team - TIQN"
app_description = "Customize Erpnext"
app_email = "it@tiqn.com.vn"
app_license = "mit"

# Override HRMS app_home to fix redirect after login
# HRMS sets app_home = "/desk/people" but this route doesn't exist
# This setting ensures users are redirected to /desk instead
app_home = "/desk"

add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/erpnext/images/erpnext-logo.svg",
		"title": app_title,
		"route": "/desk",
		"has_permission": "erpnext.check_app_permission",
	}
]

# Customize JS scripts for default ERPNext DocTypes
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
    "Material Request": "public/js/custom_scripts/material_request.js",
    "Purchase Order": "public/js/custom_scripts/purchase_order.js",
    "Item Attribute": [
        "public/js/custom_scripts/item_attribute.js",
        "public/js/custom_scripts/item_attribute_import.js"
    ],
    "Item Attribute Value": "public/js/custom_scripts/item_attribute.js",
    "Sales Order": "public/js/custom_scripts/sales_order_sum_qty.js",
    "Production Plan": "public/js/custom_scripts/production_plan.js",
    "Stock Reconciliation": "public/js/custom_scripts/stock_reconciliation.js",
    "Employee": [
        "public/js/fingerprint_scanner_dialog.js",
        "public/js/shared_fingerprint_sync.js",
        "public/js/custom_scripts/employee.js"
    ],
    "Employee Checkin": "public/js/custom_scripts/employee_checkin.js",
    "Attendance": "public/js/custom_scripts/attendance.js",
    "Shift Type": "public/js/custom_scripts/shift_type.js",
}

# List view customizations
doctype_list_js = {
    "Item": "public/js/custom_scripts/item_list.js",
    "Stock Entry": "public/js/custom_scripts/stock_entry_list.js",
    "Employee": [
        "public/js/fingerprint_scanner_dialog.js",
        "public/js/shared_fingerprint_sync.js",
        "public/js/custom_scripts/employee_list.js"
    ],
    "Employee Checkin": "public/js/custom_scripts/employee_checkin_list.js",
    "Attendance": "public/js/custom_scripts/attendance_list.js",
}

# Fixtures Configuration
# Usage:
#   Export: bench --site erp-sonnt.tiqn.local export-fixtures
#   Import: bench --site erp.tiqn.local migrate
#   Import specific app: bench --site erp.tiqn.local import-fixtures --app customize_erpnext
fixtures = [
    # Custom fields starting with "custom%"
    {
        "doctype": "Custom Field",
        "filters": [
            ["dt", "in", [
                "Stock Entry",
                "Sales Order Item",
                "Sales Order",
                "BOM Item",
                "Material Request Item",
                "Production Plan",
                "Employee",
                "Employee Checkin",
                "Stock Entry Detail",
                "Stock Reconciliation",
                "Stock Reconciliation Item",
                "Stock Ledger Entry",
                "Customer",
                "Shift Type",
                "Attendance",
                "Leave Application"
            ]],
            ["fieldname", "like", "custom%"]
        ]
    },
    # Property customizations
    {
        "doctype": "Property Setter",
        "filters": [
            ["doc_type", "in", [
                "Item",
                "Stock Entry Detail",
                "Stock Reconciliation",
                "Stock Reconciliation Item",
                "Employee",
                "Employee Checkin"
            ]]
        ]
    },
    # List view settings
    {
        "doctype": "List View Settings",
        "filters": {
            "name": ["in", [
                "Item",
                "Stock Entry",
                "Stock Reconciliation",
                "Shift Name"
            ]]
        }
    },
    # Custom print formats
    {
        "doctype": "Print Format",
        "filters": {
            "module": "Customize Erpnext"
        }
    },
    # Workflow configurations
    {
        "doctype": "Workflow",
        "filters": []  # Export all workflows
    },
    {
        "doctype": "Workflow State",
        "filters": []  # Export all workflow states
    },
    {
        "doctype": "Workflow Action Master",
        "filters": []  # Export all workflow actions
    },
    {
        "doctype": "Workflow Transition",
        "filters": []  # Export all workflow transitions
    },
    {
        "doctype": "Assignment Rule",
        "filters": []
    },
    # Workspace customizations
    # NOTE: ERPNext v16 - Khi import sẽ OVERWRITE hoàn toàn workspace gốc
    {
        "doctype": "Workspace",
        "filters": [
            ["name", "in", ["HR", "Stock", "TIQN App"]]
        ]
    },
    # Workspace Sidebar customizations (v16+)
    {
        "doctype": "Workspace Sidebar",
        "filters": [
            ["name", "in", [
                "Shift & Attendance",  # HRMS sidebar with custom reports
                "Stock",  # Stock sidebar with custom reports
                "TIQN App"  # TIQN App sidebar
            ]]
        ]
    },
    # Custom Reports
    # WHY NEEDED:
    # - Workspace Sidebar exports LINKS/REFERENCES to reports (label, icon, position)
    # - Report fixtures export DEFINITION of report (metadata, permissions, settings)
    # - Need BOTH for sidebar links to work properly
    # NOTE: Script Report code (Python/JS) is NOT exported, only metadata
    {
        "doctype": "Report",
        "filters": [
            ["name", "in", [
                "Shift Attendance Customize",
                "Overtime Registration",
                "Stock Ledger Customize",
                "Stock Balance Customize",
            ]]
        ]
    }
]

# Data import hooks
data_import_before_import = [
    "customize_erpnext.override_methods.item_attribute_import.before_import"
]

# Scheduler Events
scheduler_events = {
    "cron": {
        # Daily Shift Attendance Report - Every day at 08:15 AM
        "15 8 * * *": [
            # Shift Attendance Report - Every day at 08:15 AM
            "customize_erpnext.customize_erpnext.report.shift_attendance_customize.scheduler.send_daily_attendance_report_scheduled"
        ],
        # Sunday overtime alert - Monday at 08:00 AM
        "0 8 * * 1": [
            # Disable Daily Timesheet
            # "customize_erpnext.customize_erpnext.doctype.daily_timesheet.scheduler.send_sunday_overtime_alert_scheduled"
        ],
        # Daily Vehicle Trips - Create pickup at 05:30 AM every day
        # "30 5 * * *": [
        #     "customize_erpnext.customize_erpnext.doctype.vehicle_trip.daily_trips.create_daily_trips_pickup"
        # ],
         # Daily Vehicle Trips - Create dropoff at 16:45 AM every day
        # "45 16 * * *": [
        #     "customize_erpnext.customize_erpnext.doctype.vehicle_trip.daily_trips.create_daily_trips_dropoff"
        # ],

        # Smart auto update mỗi 2 giờ
        # "0 */2 * * *": [
        #     "customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.scheduler_jobs.smart_auto_update_custom_attendance"
        # ]
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
    # Employee Checkin Events
    # - Update checkin log_type (IN/OUT)
    # - Auto-update HRMS Attendance based on checkins
    "Employee Checkin": {
        "on_update": [
            "customize_erpnext.overrides.employee_checkin.employee_checkin.update_employee_checkin",
            "customize_erpnext.overrides.employee_checkin.employee_checkin.update_attendance_on_checkin_update"
        ],
        "after_insert": [
            "customize_erpnext.overrides.employee_checkin.employee_checkin.update_employee_checkin",
            "customize_erpnext.overrides.employee_checkin.employee_checkin.update_attendance_on_checkin_insert"
        ],
        "after_delete": [
            "customize_erpnext.overrides.employee_checkin.employee_checkin.update_attendance_on_checkin_delete"
        ],
    },

    # Overtime Registration Events
    # - Update HRMS Attendance when overtime is submitted/cancelled/updated
    "Overtime Registration": {
        "on_submit": [
            "customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_hooks.update_attendance_on_overtime_change"
        ],
        "on_cancel": [
            "customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_hooks.update_attendance_on_overtime_change"
        ],
        "on_update_after_submit": [
            "customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_hooks.update_attendance_on_overtime_change"
        ]
    },

    # Employee Events
    # - Validate employee changes
    # - Auto-update Attendance when maternity tracking changes
    # - Sync to MongoDB
    # - Set default holiday list
    # - Prevent deletion
    "Employee": {
        "validate": [
            "customize_erpnext.overrides.employee.employee.check_maternity_tracking_changes_for_attendance",
            "customize_erpnext.api.employee.employee_validation.validate_employee_changes"
        ],
        "on_update": [
            "customize_erpnext.overrides.employee.employee.auto_update_attendance_on_maternity_change",
        ],
        "after_insert": [
            "customize_erpnext.api.employee.erpnext_mongodb.sync_employee_to_mongodb",
            "customize_erpnext.api.employee.auto_assignment.set_default_holiday_list"
        ],
        "on_trash": [
            "customize_erpnext.api.employee.employee_validation.prevent_employee_deletion",
            "customize_erpnext.api.employee.erpnext_mongodb.delete_employee_from_mongodb"
        ]
    },

    # Shift Type Events
    # - Update related attendance records when shift type changes
    "Shift Type": {
        "on_update": "customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.on_shift_update"
    },

    # Stock Entry Events
    # - Add custom_invoice_number and custom_receive_date to Stock Ledger Entry
    "Stock Entry": {
        "on_submit": "customize_erpnext.api.stock_ledger.update_stock_ledger_invoice_number_receive_date.update_stock_ledger_invoice_number_receive_date"
    },

    # Stock Reconciliation Events
    # - Add custom_invoice_number and custom_receive_date to Stock Ledger Entry
    "Stock Reconciliation": {
        "on_submit": "customize_erpnext.api.stock_ledger.update_stock_ledger_invoice_number_receive_date.update_stock_ledger_invoice_number_receive_date"
    },

    # Overtime Request Events
    # - Custom permission check
    "Overtime Request": {
        "has_permission": "customize_erpnext.overrides.overtime_request_permission",
    },

    # Item Events
    # - Auto-add barcode when item is created or updated
    "Item": {
        "validate": "customize_erpnext.api.bulk_update_scripts.item_update_barcode.auto_add_barcode_on_item_save"
    },
}

# CSS/JS Includes
# Include Cropper.js library for image cropping
app_include_css = [
    "https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.css"
]

app_include_js = [
    "/assets/customize_erpnext/js/fingerprint_scanner_dialog.js",
    "https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.js"
]

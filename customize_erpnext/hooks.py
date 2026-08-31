app_name = "customize_erpnext"
app_title = "Customize Erpnext"
app_publisher = "IT Team - TIQN"
app_description = "Customize Erpnext"
app_email = "it@tiqn.com.vn"
app_license = "mit"



# Customize JS scripts for default ERPNext DocTypes
doctype_js = {
    "Stock Entry": [
        "public/js/custom_scripts/stock_entry.js",
        "public/js/custom_scripts/stock_entry_quick_import.js",
        "public/js/custom_scripts/serial_batch_selector_custom.js"
    ],
    "BOM": "public/js/custom_scripts/bom.js",
    "Item": [
        "public/js/custom_scripts/item.js",
        "public/js/custom_scripts/item_show_multiple_variants_dialog.js"
    ],
    "Material Request": "public/js/custom_scripts/material_request.js",
    "Purchase Order": "public/purchase_order.js",
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
    "Attendance Request": "public/js/custom_scripts/attendance_request.js",
    "Batch": "public/js/custom_scripts/batch.js",
    "Packing List": "public/js/packing_list_scale.js",
    "Salary Structure Assignment": "public/js/custom_scripts/salary_structure_assignment.js",
    "Leave Control Panel": "public/js/custom_scripts/leave_control_panel.js",
    # Cùng 1 file cho 2 doctype: HRMS include chung hrms/hr/employee_property_update.js
    # (xem override_doctype_class "Employee Promotion" / "Employee Transfer")
    "Employee Promotion": "public/js/custom_scripts/employee_property_update_override.js",
    "Employee Transfer": "public/js/custom_scripts/employee_property_update_override.js",
}

# List view customizations
doctype_list_js = {
    "CCTV Tracking": "network/doctype/cctv_tracking/cctv_tracking_list.js",
    "Item": "public/js/custom_scripts/item_list.js",
    "Stock Entry": "public/js/custom_scripts/stock_entry_list.js",
    "Employee": [
        "public/js/fingerprint_scanner_dialog.js",
        "public/js/shared_fingerprint_sync.js",
        "public/js/custom_scripts/employee_list.js"
    ],
    "Employee Checkin": "public/js/custom_scripts/employee_checkin_list.js",
    "Attendance": "public/js/custom_scripts/attendance_list.js",
    # Nút "Bulk Create from Missing Check-ins" + dialog đề xuất giờ + in form ký
    "Attendance Request": "public/js/custom_scripts/attendance_request_list.js",
    "Shift Assignment": "public/js/custom_scripts/shift_assignment_list.js",
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
                "Attendance Request",
                "Stock Entry Detail",
                "Stock Reconciliation",
                "Stock Reconciliation Item",
                "Stock Ledger Entry",
                "Customer",
                "Shift Type",
                "Attendance",
                "Leave Type",
                "Leave Application",
                "Job Applicant",
                "Designation",
                "Batch",
                "Employee Maternity",
                "Employment Type",
                "Salary Structure Assignment",
                "Salary Slip",
                "Employee Education",
                # custom_section / custom_group: Employee Internal Work History gốc chỉ
                # có branch/department/designation nên timeline thiếu 2 cấp tổ chức này
                "Employee Internal Work History"
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
                 "Stock Entry",
                "Stock Entry Detail",
                "Stock Reconciliation",
                "Stock Reconciliation Item",
                "Employee",
                "Employee Checkin",
                "Attendance",
                # reason.options được mở rộng thêm 4 lý do bổ sung giờ công
                # (xem override_doctype_class "Attendance Request")
                "Attendance Request",
                "Leave Type",
                # Leave Application có 7 Property Setter trong DB (half_day.depends_on,
                # field_order, naming_series HR-LAP-.YYYY.-, 4 × in_list_view) mà trước đây
                # không được export → mất trắng khi deploy sang site khác.
                "Leave Application",
                "Employee Education",
                # branch bỏ khỏi grid + chốt độ rộng cột để chỗ cho Section/Group
                "Employee Internal Work History"
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
    # NOTE: only export standard=No formats here. standard=Yes formats are
    # auto-saved as app source code under customize_erpnext/print_format/ (dev mode),
    # so including them here would duplicate them.
    {
        "doctype": "Print Format",
        "filters": {
            "module": "Customize Erpnext",
            "standard": "No"
        }
    },
    # Workflow configurations
    # {
    #     "doctype": "Workflow",
    #     "filters": []  # Export all workflows
    # },
    # {
    #     "doctype": "Workflow State",
    #     "filters": []  # Export all workflow states
    # },
    # {
    #     "doctype": "Workflow Action Master",
    #     "filters": []  # Export all workflow actions
    # },
    # {
    #     "doctype": "Workflow Transition",
    #     "filters": []  # Export all workflow transitions
    # },
    # {
    #     "doctype": "Assignment Rule",
    #     "filters": []
    # },
    # Workspace Sidebar customizations (v16+)
    {
        "doctype": "Workspace Sidebar",
        "filters": [
            ["name", "in", [
                # "HR Setup",  # HRMS sidebar with custom reports
                # Bản HRMS thiếu chính link "Attendance" (chỉ có trong card ở thân
                # workspace) nên bộ chọn sidebar không bao giờ về được đây — xem
                # sidebar_resolution_fix.bundle.js
                "Shift & Attendance",
                "Stock",  # Stock sidebar with custom reports
                "Uniform Control",  # Uniform Control module sidebar

                # "TIQN App",  # TIQN App sidebar
                # "Health Check Up"
            ]]
        ] 
    },
    {
        "doctype": "Workspace",
        "filters": [
            ["name", "in", [
                "HR Setup",
                "Shift & Attendance",  # HRMS workspace: Attendance Machine card + Shift Attendance Customize report link
            ]]
        ]
    },
    # ⚠ ĐÃ BỎ fixture "Report" (18/08/2026) — ĐỪNG THÊM LẠI.
    # Cả 4 report (Shift Attendance Customize, Overtime Registration, Stock Ledger/Balance
    # Customize) đều `is_standard = "Yes"` và đã có file .json trong thư mục module. Frappe
    # tự nạp chúng khi migrate vì "Report" nằm trong IMPORTABLE_DOCTYPES (frappe/model/sync.py).
    #
    # Fixture chỉ tạo NGUỒN THỨ HAI cho cùng một bản ghi, và nó chạy SAU bước đồng bộ file
    # module nên luôn thắng. Sự cố thật: sửa role trong file module của Shift Attendance
    # Customize xuống còn System Manager, migrate hai lần đều bị fixture lật lại đủ 5 role.
    #
    # Ghi chú cũ "Need BOTH for sidebar links to work properly" là SAI với report is_standard=Yes:
    # link sidebar trỏ theo TÊN report, tên đã có sẵn từ file module.
    #
    # Nay file .json trong thư mục module là nguồn DUY NHẤT.
    # Desktop Icons
    # Export custom desktop icons for apps/modules
    # {
    #     "doctype": "Desktop Icon",
    #     "filters": [
    #         ["name", "in", ["TIQN App", "Employee Photos", "QR Code Generator", "Job Portal", "Shoe Rack", "Sync Logs", "Health Check Up"]]
    #     ]
    # },
    # # Workspace Sidebars for custom External link icons
    # {
    #     "doctype": "Workspace Sidebar",
    #     "filters": [
    #         ["name", "in", ["Job Portal", "Employee Photos", "QR Code Generator", "Shoe Rack", "Sync Logs","Health Check Up"]]
    #     ]
    # }
]

# After migrate hooks
# - Fix broken Desktop Icon link_to fields (Accounting, LMS)
# - Add custom links to HRMS workspaces (People, Shift & Attendance)
# - Drop orphan database tables
# after_migrate = [
#     "customize_erpnext.workspace_setup.setup_workspace_links",
#     # "customize_erpnext.workspace_setup.drop_orphan_tables",
# ]

# Data import hooks
data_import_before_import = [
    "customize_erpnext.override_methods.item_attribute_import.before_import"
]

# Scheduler Events
scheduler_events = {
    "hourly": [
        # Delete attendance Excel export files older than 45 minutes
        "customize_erpnext.customize_erpnext.report.shift_attendance_customize.shift_attendance_customize.cleanup_export_files",
    ],
    "cron": {
         # Chạy mỗi phút - Giải phóng RAM rembg sau 30 phút không dùng rembg để edit ảnh thẻ
        "* * * * *": [
            "customize_erpnext.api.employee.employee_utils.cleanup_rembg_sessions"
        ],
        # The 08:15 Shift Attendance Report was retired on 2026-08-14: the 08:20 job
        # below sends the same workbook to the HR list, and its two body-only
        # anomaly lists became sheets 3 and 4 of that workbook. Sending both meant
        # HR got two mails carrying an identical attachment built twice.
        # Daily Attendance Report - Every day at 08:20 AM.
        # Recipients come from Attendance Calculation Setting (Manager / HR);
        # an empty list means that audience is simply not sent to.
        "20 8 * * *": [
            "customize_erpnext.api.daily_attendance_email.send_daily_attendance_email_scheduled"
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

        # Auto mark employees as Left - Every day at 00:00
        "0 0 * * *": [
            "customize_erpnext.overrides.employee.employee.auto_mark_employees_as_left",
            # Labor Contract - materialize next contract stage due soon + mark overdue Upcoming
            # TẠM TẮT: chờ setup xong phần lương (Salary Structure + SSA) rồi mới bật lại.
            # Xem doctype/labor_contract/labor_contract.md mục 10.
            # "customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.process_labor_contracts_daily",
        ],
        # Recalculate maternity status - 00:10, tức là SAU auto_mark_employees_as_left.
        # Thứ tự này bắt buộc: người tới ngày nghỉ việc phải được chuyển sang `Left`
        # trước, rồi maternity mới đóng giai đoạn của họ trong cùng một đêm.
        "10 0 * * *": [
            "customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity.scheduled_calculate_all_maternity_statuses",
        ],
        # Weekly attendance recalculation - polled hourly, gated by
        # Attendance Calculation Setting (enable + weekdays + run-time hour).
        # When it fires (and day-of-month >= 5): set process_attendance_after =
        # 26th of previous month for all shift types, then force bulk recalc.
        "0 * * * *": [
            "customize_erpnext.overrides.shift_type.shift_type_optimized.weekly_recalculate_attendance_scheduled"
        ],
        # NVR / CCTV Monitor - Every day at 07:00 (gap_days=1, min_gap=10)
        "0 7 * * *": [
            "customize_erpnext.network.utils.monitor_runner.run_all_nvr_daily"
        ],
        # Uniform Control - Weekly alert every Monday at 08:30 AM
        "30 8 * * 1": [
            "customize_erpnext.uniform_control.api.uniform_scheduler.send_weekly_uniform_alert"
        ],
        # Attendance machines - Sync clocks every Monday at 05:00 AM
        "0 5 * * 1": [
            "customize_erpnext.api.biometric_sync.sync_all_machine_times_scheduled"
        ],
    }
}
 
# DocType Class
# ---------------
# Override standard doctype classes
# override_doctype_class = {
#     "Stock Reconciliation": "customize_erpnext.override_methods.stock_reconciliation.custom_stock_reconciliation.CustomStockReconciliation"
# }
override_doctype_class = {
    # Nghỉ thai sản = Employee.status Inactive, nhưng KHÔNG khoá tài khoản User.
    # Core disable User khi status != Active; nghỉ thai sản thì vẫn cần đăng nhập
    # xem phiếu lương / đơn nghỉ. Kế thừa EmployeeMaster của HRMS (HRMS cũng
    # override "Employee") để không mất phần autoname của HRMS.
    "Employee": "customize_erpnext.overrides.employee.employee_override.CustomEmployee",

    # Fix timeout khi cancel maternity leave (~6 tháng / ~180 ngày)
    # Skip HRMS cancel_attendance() loop đồng bộ, dùng background job thay thế
    "Leave Application": "customize_erpnext.overrides.leave_application.leave_application.CustomLeaveApplication",

    # Ngày công chuẩn = ngày trong kỳ - Chủ Nhật. Ngày lễ nhà nước VẪN tính công
    # (nghỉ có lương) nên không trừ. HRMS gốc trừ cả hai -> kỳ Tết ra 18 ngày
    # thay vì 27, sai đơn giá ngày. Xem overrides/payroll_docs/PAYROLL_SETUP.md mục 2.2.
    "Salary Slip": "customize_erpnext.overrides.salary_slip.salary_slip.CustomSalarySlip",

    # Attendance Request cũng dùng để YÊU CẦU BỔ SUNG giờ check in/out bị thiếu
    # (quên quét vân tay, máy lỗi, ngày làm việc đầu tiên). Chế độ suy từ `reason`:
    # 4 lý do lấy từ Employee Checkin.custom_reason_for_manual_check_in -> tạo
    # Employee Checkin + chạy lại engine tính công. Work From Home / On Duty giữ
    # nguyên hành vi HRMS gốc. Xem docs/attendance_request_supplement_plan.md
    "Attendance Request": "customize_erpnext.overrides.attendance_request.attendance_request.CustomAttendanceRequest",

    # Thuyên chuyển / thăng chức: chỉ cho đổi 6 field tổ chức, và dựng lại
    # Employee.internal_work_history từ TOÀN BỘ doc đã submit thay vì append.
    # HRMS append nên import dữ liệu quá khứ sẽ ghi đè giá trị hiện tại của
    # Employee bằng giá trị cũ. Xem overrides/employee_property/work_history.py
    "Employee Promotion": "customize_erpnext.overrides.employee_property.employee_promotion.CustomEmployeePromotion",
    "Employee Transfer": "customize_erpnext.overrides.employee_property.employee_transfer.CustomEmployeeTransfer",
}
# Khấu trừ theo pháp luật VN (BHXH/BHYT/BHTN, đoàn phí, thuế TNCN).
# Móc vào hook `apply_regional_deductions` có sẵn của HRMS — chạy sau khi gross_pay đã
# chốt, trước set_net_pay(). Khớp region qua Company.country = "Vietnam".
# Formula của Salary Structure không đọc được Settings/DB nên phần này phải là Python.
# Xem overrides/payroll_docs/PLAN_PAYROLL_SETTINGS.md mục 2.
regional_overrides = {
    "Vietnam": {
        "hrms.payroll.doctype.salary_slip.salary_slip.apply_regional_deductions":
            "customize_erpnext.overrides.payroll.vn_deductions.apply_regional_deductions",
    }
}

# Document Events
doc_events = {
    # Batch Events
    # - Populate custom_color from the item's Color attribute
    # - Auto-generate batch_id (template|color|lot|roll) on Excel/Data Import when empty
    "Batch": {
        "before_insert": [
            "customize_erpnext.api.batch.batch_utils.set_batch_defaults"
        ]
    },

    # Employee Checkin Events
    # - Update checkin log_type (IN/OUT)
    # - Auto-update HRMS Attendance based on checkins
    # Attendance-recalc hooks are GATED by Attendance Calculation Setting →
    # "Recalc Attendance on Checkin Save/Delete" (default OFF = no-op)
    "Employee Checkin": {
        "on_update": [
            "customize_erpnext.overrides.employee_checkin.employee_checkin.update_employee_checkin",
            "customize_erpnext.overrides.employee_checkin.employee_checkin.update_attendance_on_checkin_update",
        ],
        "after_insert": [
            "customize_erpnext.overrides.employee_checkin.employee_checkin.update_employee_checkin",
            "customize_erpnext.overrides.employee_checkin.employee_checkin.update_attendance_on_checkin_insert",
        ],
        "after_delete": [
            "customize_erpnext.overrides.employee_checkin.employee_checkin.update_attendance_on_checkin_delete",
        ],
    },

    # Overtime Registration Events — gated by Attendance Calculation Setting
    # "Recalc Attendance on OT Submit/Cancel" (default OFF).
    # on_update/on_trash only act on DRAFTS and only when include_draft_ot is
    # ON (drafts count toward attendance → edits/deletes must recalc too).
    # (no on_update_after_submit: no field has allow_on_submit, the event
    #  never fires — re-add together with allow_on_submit if post-submit
    #  edits are ever enabled)
    "Overtime Registration": {
        "on_submit": [
            "customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_hooks.update_attendance_on_overtime_change"
        ],
        "on_cancel": [
            "customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_hooks.update_attendance_on_overtime_change"
        ],
        "on_update": [
            "customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_hooks.update_attendance_on_overtime_draft_change"
        ],
        "on_trash": [
            "customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_hooks.update_attendance_on_overtime_draft_change"
        ]
    },

    # Employee Events
    # - Validate employee changes
    # - Sync to MongoDB
    # - Set default holiday list
    # - Prevent deletion
    # - Auto-create Uniform Profile on new employee
    "Employee": {
        "before_insert": [
            "customize_erpnext.api.employee.employee_validation.before_insert_employee"
        ],
        "validate": [
            "customize_erpnext.api.employee.employee_validation.validate_employee_changes",
        ],
        "after_insert": [
            # "customize_erpnext.api.employee.erpnext_mongodb.sync_employee_to_mongodb",
            # ĐÃ BỎ set_default_holiday_list: nó ghi vào field cũ Employee.holiday_list
            # mà HRMS v16.15+ không còn dùng (đã chuyển sang doctype Holiday List
            # Assignment gán ở cấp Company). Module chấm công cũng đã đọc theo Company.
            # "customize_erpnext.uniform_control.api.onboarding.create_uniform_profile_on_employee_insert",
            # Auto-create the first probationary Labor Contract (skipped during bulk import)
            # TẠM TẮT: chờ setup xong phần lương (Salary Structure + SSA) rồi mới bật lại.
            # Xem doctype/labor_contract/labor_contract.md mục 10.
            # "customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.create_initial_contract_on_employee_insert",
        ],
        "on_trash": [
            "customize_erpnext.api.employee.employee_validation.prevent_employee_deletion",
            # "customize_erpnext.api.employee.erpnext_mongodb.delete_employee_from_mongodb"
        ]
    },

    # Employee Maternity Events
    # - Auto-update Attendance when maternity date ranges change (UI + Data Import)
    # - Gated by Attendance Calculation Setting "Recalc Attendance on Maternity Save/Delete" (default OFF)
    # - on_update fires after both insert and save — no separate after_insert hook needed
    "Employee Maternity": {
        "on_update": "customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity.on_maternity_update",
        "on_trash":  "customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity.on_maternity_delete",
    },

    # Stock Entry Events
    # - Chặn Submit nếu dòng items thiếu Invoice Number (chốt chặn server-side)
    # - Add custom_invoice_number and custom_receive_date to Stock Ledger Entry
    "Stock Entry": {
        "autoname": "customize_erpnext.api.stock_entry.naming.autoname",
        "before_submit": "customize_erpnext.api.stock_entry.stock_entry_validation.validate_invoice_numbers",
        "on_submit": "customize_erpnext.api.stock_ledger.update_stock_ledger_invoice_number_receive_date.update_stock_ledger_invoice_number_receive_date"
    },

    # Stock Reconciliation Events
    # - Add custom_invoice_number and custom_receive_date to Stock Ledger Entry
    "Stock Reconciliation": {
        "on_submit": "customize_erpnext.api.stock_ledger.update_stock_ledger_invoice_number_receive_date.update_stock_ledger_invoice_number_receive_date"
    },

    # Item Events
    # - Auto-add barcode when item is created or updated
    "Item": {
        "validate": "customize_erpnext.api.bulk_update_scripts.item_update_barcode.auto_add_barcode_on_item_save"
    },
     "Shoe Rack": {
        "validate": "customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.validate",
        "on_update": [
            "customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.on_update",
            # Sync shoe_rack_location on Employee Uniform Profile
            "customize_erpnext.uniform_control.api.shoe_rack_sync.sync_profiles_on_rack_update",
        ],
        # "before_insert": "customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.before_insert"
    },

    # Leave Application Events
    # - Handle dual leave cancellation (update attendance when LA cancelled)
    # CRITICAL: must run BEFORE cancel — HRMS on_cancel calls cancel_attendance()
    # (controller method chạy trước doc_events hook), nếu để on_cancel thì swap
    # LA2→LA1 không bao giờ chạy vì attendance đã bị cancel (docstatus=2)
    # Salary Structure Assignment Events
    # - custom_si_base tự tính = lương HĐLĐ + phụ cấp thuộc diện đóng BH
    #   (cho phép tick custom_si_base_override để nhập tay theo mức đã đăng ký BHXH)
    "Salary Structure Assignment": {
        "validate": "customize_erpnext.overrides.salary_structure_assignment.salary_structure_assignment.set_si_base"
    },

    "Leave Application": {
        "before_cancel": [
            "customize_erpnext.overrides.leave_application.leave_application.on_leave_application_cancel",
        ],
    }

}

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# Cropper.js KHÔNG include toàn cục nữa — chỉ /employee-photos (www) tự
# lazy-load bản self-host tại /assets/customize_erpnext/cropperjs/ khi cần crop
app_include_js = [
    "/assets/customize_erpnext/js/fingerprint_scanner_dialog.js",
    # Ẩn field bị chặn theo perm_level khỏi dialog "Export Data" (UI only, server vẫn chặn thật)
    "/assets/customize_erpnext/js/hide_restricted_export_fields.js",
    "csv_bom_fix.bundle.js",
    # Sidebar workspace v16: chọn sidebar tất định cho mọi route
    # (search/URL trực tiếp vốn ra sidebar khác với khi click từ workspace)
    "sidebar_resolution_fix.bundle.js"
]

# Đánh dấu sidebar nào là bản auto-generate từ Module Def — boot gốc trộn chung
# với Workspace Sidebar thật nên client không phân biệt được (xem boot.py)
extend_bootinfo = "customize_erpnext.overrides.workspace_sidebar.boot.mark_auto_generated_sidebars"

# Include CSS and JS files in web pages (including web forms)
web_include_css = [
    "/assets/customize_erpnext/css/job_application_form.css"
]

web_include_js = [
    "/assets/customize_erpnext/js/job_application_form.js"
]


# Methods callable directly in Jinja templates (print formats, web pages).
# Dùng thay cho frappe.call() trong print format: frappe.call đi qua execute_cmd
# nên đòi hỏi HTTP request context (render từ console/scheduler sẽ lỗi).
jinja = {
    "methods": [
        "customize_erpnext.api.qr_label_print.generate_qr_code_base64",
        # Số tiền bằng chữ / định dạng VND cho print format.
        # money_in_words_vi và so_tien_bang_chu là cùng một hàm (alias).
        "customize_erpnext.api.vn_number_words.money_in_words_vi",
        "customize_erpnext.api.vn_number_words.so_tien_bang_chu",
        "customize_erpnext.api.vn_number_words.format_vnd",
    ],
}

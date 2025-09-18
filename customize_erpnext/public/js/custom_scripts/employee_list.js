console.log('Employee list customization loaded successfully');
// import apps/customize_erpnext/customize_erpnext/public/js/shared_fingerprint_sync.js

frappe.listview_settings['Employee'] = {
    onload: function (listview) {
        console.log('Employee listview onload triggered');
        // Add individual menu items under Actions
        listview.page.add_menu_item(__('Scan Fingerprint'), function () {
            show_get_fingerprint_dialog();
        });

        listview.page.add_menu_item(__('Sync Fingerprint From ERP To Attendance Machines'), function () {
            show_multi_employee_sync_dialog(listview);
        });
    }
};

function show_get_fingerprint_dialog() {
    // Simple employee selector dialog that uses shared FingerprintScannerDialog
    let d = new frappe.ui.Dialog({
        title: __('🔍 Chọn Nhân Viên Để Quét Vân Tay'),
        fields: [
            {
                fieldname: 'employee_section',
                fieldtype: 'Section Break',
                label: __('Thông Tin Nhân Viên')
            },
            {
                fieldname: 'employee',
                fieldtype: 'Link',
                label: __('Nhân Viên'),
                options: 'Employee',
                reqd: 1,
                get_query: function () {
                    return {
                        filters: {
                            status: 'Active'
                        },
                        order_by: 'employee_name asc'
                    };
                },
                description: __('Chọn nhân viên cần quét vân tay từ danh sách')
            }
        ],
        primary_action_label: __('🔍 Bắt Đầu Quét'),
        primary_action(values) {
            if (!values.employee) {
                frappe.msgprint({
                    title: __('⚠️ Thiếu Thông Tin'),
                    message: __('Vui lòng chọn nhân viên trước khi quét vân tay.'),
                    indicator: 'orange'
                });
                return;
            }

            // Get employee name for display
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Employee',
                    fieldname: 'employee_name',
                    filters: { name: values.employee }
                },
                callback: function(r) {
                    d.hide();
                    // Use shared FingerprintScannerDialog - same as Employee form
                    if (window.FingerprintScannerDialog && window.FingerprintScannerDialog.showForEmployee) {
                        window.FingerprintScannerDialog.showForEmployee(values.employee, r.message?.employee_name);
                    } else {
                        frappe.msgprint({
                            title: __('🚫 Lỗi Tải Module'),
                            message: __('Không thể tải module máy quét vân tay. Vui lòng làm mới trang và thử lại.'),
                            indicator: 'red'
                        });
                    }
                }
            });
        }
    });

    d.show();

    // Style the dialog
    d.$wrapper.find('.modal-dialog').addClass('modal-lg');
    d.$wrapper.find('.modal-content').css({
        'border-radius': '12px',
        'box-shadow': '0 10px 30px rgba(0,0,0,0.2)'
    });
    d.$wrapper.find('.modal-header').css({
        'background': 'linear-gradient(135deg, #007bff 0%, #0056b3 100%)',
        'color': 'white',
        'border-bottom': 'none',
        'border-radius': '12px 12px 0 0'
    });
}

// All fingerprint scanning functions removed - now using shared FingerprintScannerDialog

function show_multi_employee_sync_dialog(listview) {
    // Get selected employees
    const selected_employees = listview.get_checked_items();

    if (selected_employees.length === 0) {
        frappe.msgprint({
            title: __('No Employees Selected'),
            message: __('Please select at least one employee from the list to sync fingerprints to attendance machines.'),
            indicator: 'orange'
        });
        return;
    }

    // Confirm action for multiple employees
    if (selected_employees.length > 1) {
        frappe.confirm(
            __('You have selected {0} employees. Do you want to sync fingerprints for all of them to attendance machines?', [selected_employees.length]),
            function () {
                // User confirmed, proceed with sync
                const employees = selected_employees.map(emp => ({
                    employee_id: emp.name,
                    employee_name: emp.employee_name || emp.name
                }));

                // Use shared sync dialog for multi-employee sync
                window.showSharedSyncDialog(employees, {
                    multi_employee: true,
                    source: 'employee_list'
                });
            }
        );
    } else {
        // Single employee selected
        const employee = selected_employees[0];
        const emp_data = {
            employee_id: employee.name,
            employee_name: employee.employee_name || employee.name
        };

        // Use shared sync dialog for single employee
        window.showSharedSyncDialog([emp_data], {
            source: 'employee_list'
        });
    }
}

function show_sync_fingerprint_from_attendance_machine_to_erp_dialog() {
    frappe.msgprint({
        title: __('Sync Fingerprint Data'),
        message: __('show_sync_fingerprint_from_attendance_machine_to_erp_dialog() will synchronize fingerprint data from attendance devices to ERP. Implementation will be completed in the next phase.'),
        indicator: 'blue'
    });
}


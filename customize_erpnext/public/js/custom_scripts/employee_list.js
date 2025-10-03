console.log('Employee list customization loaded successfully');
// import apps/customize_erpnext/customize_erpnext/public/js/shared_fingerprint_sync.js

frappe.listview_settings['Employee'] = {
    onload: function (listview) {
        console.log('Employee listview onload triggered');
        // Add individual menu items under Actions
        // Add Employee Card menu item
        listview.page.add_menu_item(__('Generate Employee Cards'), function () {
            print_employee_cards(listview);
        });
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
                callback: function (r) {
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

function show_employee_search_dialog() {
    const d = new frappe.ui.Dialog({
        title: __('Search Employees for Card Generation'),
        fields: [
            {
                fieldname: 'search_info',
                fieldtype: 'HTML',
                options: '<p style="margin-bottom: 10px;">' + __('Enter employee codes (one per line)') + '</p>'
            },
            {
                fieldname: 'employee_codes',
                fieldtype: 'Small Text',
                label: __('Employee Codes'),
                reqd: 1,
                description: __('Enter employee codes (name field), separated by new lines. Example:<br>TIQN-0001<br>TIQN-0002<br>TIQN-0003')
            },
            {
                fieldname: 'page_size',
                fieldtype: 'Select',
                label: __('Page Size'),
                options: ['A4', 'A5'],
                default: 'A4',
                description: __('Select page size for the cards')
            },
            {
                fieldname: 'with_barcode',
                fieldtype: 'Check',
                label: __('With Barcode'),
                default: 0,
                description: __('Include Code39 barcode below employee photo')
            }
        ],
        primary_action_label: __('Generate Cards'),
        primary_action: function (values) {
            if (!values.employee_codes || !values.employee_codes.trim()) {
                frappe.msgprint(__('Please enter at least one employee code'));
                return;
            }

            d.hide();

            // Split by new line and clean up
            const employee_codes = values.employee_codes
                .split('\n')
                .map(code => code.trim())
                .filter(code => code.length > 0);

            if (employee_codes.length === 0) {
                frappe.msgprint(__('Please enter at least one employee code'));
                return;
            }

            if (employee_codes.length > 50) {
                frappe.msgprint({
                    title: __('Too Many Employees'),
                    message: __('Please enter maximum 50 employees at a time. You entered {0} employees.', [employee_codes.length]),
                    indicator: 'orange'
                });
                return;
            }

            // Show loading
            frappe.show_alert({
                message: __('Searching for employees...'),
                indicator: 'blue'
            });

            // Search for employees
            frappe.call({
                method: 'customize_erpnext.api.employee.employee_utils.search_employees_by_codes',
                args: {
                    employee_codes: employee_codes
                },
                callback: function (r) {
                    if (r.message && r.message.length > 0) {
                        // Found employees, generate cards
                        const employee_ids = r.message.map(emp => emp.name);

                        frappe.show_alert({
                            message: __('Found {0} employees. Generating cards...', [employee_ids.length]),
                            indicator: 'blue'
                        });

                        generate_cards_for_employees(employee_ids, values.with_barcode, values.page_size || 'A4');
                    } else {
                        frappe.msgprint({
                            title: __('No Employees Found'),
                            message: __('No employees found matching the provided codes.'),
                            indicator: 'orange'
                        });
                    }
                },
                error: function () {
                    frappe.msgprint({
                        title: __('Error'),
                        message: __('An error occurred while searching for employees.'),
                        indicator: 'red'
                    });
                }
            });
        }
    });

    d.show();
    d.$wrapper.find('.modal-dialog').css('max-width', '600px');

    // Force reset to A4 default each time dialog opens
    d.set_value('page_size', 'A4');
}

function generate_cards_for_employees(employee_ids, with_barcode, page_size) {
    frappe.call({
        method: 'customize_erpnext.api.employee.employee_utils.generate_employee_cards_pdf',
        args: {
            employee_ids: employee_ids,
            with_barcode: with_barcode ? 1 : 0,
            page_size: page_size || 'A4'
        },
        callback: function (r) {
            if (r.message && r.message.pdf_url) {
                frappe.show_alert({
                    message: __('Employee cards generated successfully'),
                    indicator: 'green'
                });

                // Open PDF in new window
                window.open(r.message.pdf_url, '_blank');
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Failed to generate employee cards PDF'),
                    indicator: 'red'
                });
            }
        },
        error: function (r) {
            frappe.msgprint({
                title: __('Error'),
                message: __('An error occurred while generating employee cards: {0}', [r.message || 'Unknown error']),
                indicator: 'red'
            });
        }
    });
}

function print_employee_cards(listview) {
    // Get selected employees
    const selected_employees = listview.get_checked_items();

    if (selected_employees.length === 0) {
        // Show dialog to search and select employees by name
        show_employee_search_dialog();
        return;
    }

    // Limit to 50 employees to avoid performance issues
    if (selected_employees.length > 50) {
        frappe.msgprint({
            title: __('Too Many Employees'),
            message: __('Please select maximum 50 employees at a time. You selected {0} employees.', [selected_employees.length]),
            indicator: 'orange'
        });
        return;
    }

    // Show dialog with page size and barcode option
    const d = new frappe.ui.Dialog({
        title: __('Generate Employee Cards'),
        fields: [
            {
                fieldname: 'employee_count',
                fieldtype: 'HTML',
                options: `<p style="margin-bottom: 15px;">${__('Generate employee cards for {0} selected employee(s)?', [selected_employees.length])}</p>`
            },
            {
                fieldname: 'page_size',
                fieldtype: 'Select',
                label: __('Page Size'),
                options: ['A4', 'A5'],
                default: 'A4',
                description: __('Select page size for the cards')
            },
            {
                fieldname: 'with_barcode',
                fieldtype: 'Check',
                label: __('With Barcode'),
                default: 0,
                description: __('Include Code39 barcode below employee photo')
            }
        ],
        primary_action_label: __('Generate'),
        primary_action: function (values) {
            d.hide();

            // User confirmed, proceed with PDF generation
            const employee_ids = selected_employees.map(emp => emp.name);

            frappe.show_alert({
                message: __('Generating employee cards...'),
                indicator: 'blue'
            });

            frappe.call({
                method: 'customize_erpnext.api.employee.employee_utils.generate_employee_cards_pdf',
                args: {
                    employee_ids: employee_ids,
                    with_barcode: values.with_barcode ? 1 : 0,
                    page_size: values.page_size || 'A4'
                },
                callback: function (r) {
                    if (r.message && r.message.pdf_url) {
                        frappe.show_alert({
                            message: __('Employee cards generated successfully'),
                            indicator: 'green'
                        });

                        // Open PDF in new window
                        window.open(r.message.pdf_url, '_blank');
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            message: __('Failed to generate employee cards PDF'),
                            indicator: 'red'
                        });
                    }
                },
                error: function (r) {
                    frappe.msgprint({
                        title: __('Error'),
                        message: __('An error occurred while generating employee cards: {0}', [r.message || 'Unknown error']),
                        indicator: 'red'
                    });
                }
            });
        }
    });

    d.show();

    // Force reset to A4 default each time dialog opens
    d.set_value('page_size', 'A4');
}


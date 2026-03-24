console.log('Employee list customization loaded successfully');
// import apps/customize_erpnext/customize_erpnext/public/js/shared_fingerprint_sync.js

frappe.listview_settings['Employee'] = {
    onload: function (listview) {
        console.log('Employee listview onload triggered');
        // Add individual menu items under Actions
        // Add Employee Card menu item
        listview.page.add_menu_item(__('1 Bulk Update Employee Photo'), function () {
            show_update_employee_photo_dialog(listview);
        });
        listview.page.add_menu_item(__('2 Generate Employee Cards'), function () {
            print_employee_cards(listview);
        });
        listview.page.add_menu_item(__('3 Scan Fingerprint'), function () {
            show_get_fingerprint_dialog(listview);
        });

        listview.page.add_menu_item(__('4.1 Sync Fingerprint From ERP To Attendance Machines'), function () {
            show_multi_employee_sync_dialog(listview);
        });

        listview.page.add_menu_item(__('4.2 Sync Fingerprint From Attendance Machines to Other & ERP'), function () {
            show_sync_fingerprint_from_machines_dialog(listview);
        });
        listview.page.add_menu_item(__('4.2 Sync Fingerprint From Attendance Machines to Other & ERP'), function () {
            show_sync_fingerprint_from_machines_dialog(listview);
        });
        listview.page.add_menu_item(__('4.3 Delete fingerprint Data of Left Employees From Attendance Machines'), function () {
            show_delete_left_employees_dialog();
        });
        listview.page.add_menu_item(__('5 Bulk Update Holiday List'), function () {
            show_bulk_update_holiday_dialog(listview);
        });

        listview.page.add_menu_item(__('6 Generate Employee List PDF'), function () {
            show_generate_employee_list_pdf_dialog(listview);
        })

    }
};

function show_generate_employee_list_pdf_dialog(listview) {
    // Get selected employees
    const selected_employees = listview.get_checked_items();

    let d = new frappe.ui.Dialog({
        title: __('Generate Employee List PDF'),
        fields: [
            {
                fieldname: 'scope_section',
                fieldtype: 'Section Break',
                label: __('Phạm Vi Tạo PDF')
            },
            {
                fieldname: 'select_scope',
                fieldtype: 'Select',
                label: __('Chọn Phạm Vi'),
                options: [
                    { label: 'Tất cả nhân viên Active', value: 'all_active' },
                    { label: 'Chỉ những nhân viên đã chọn', value: 'selected' },
                    { label: 'Theo khoảng mã số nhân viên', value: 'id_range' }
                ],
                default: selected_employees.length === 0 ? 'all_active' : 'selected',
                onchange: function () {
                    update_scope_display();
                }
            },
            {
                fieldname: 'employee_range',
                fieldtype: 'Section Break',
                label: __('Khoảng Mã Số Nhân Viên'),
                depends_on: 'eval:doc.select_scope == "id_range"',
                collapsible: 0
            },
            {
                fieldname: 'id_prefix',
                fieldtype: 'Data',
                label: __('Tiền tố (Prefix)'),
                default: 'TIQN-',
                description: __('Tiền tố mã số nhân viên, ví dụ: TIQN-'),
                depends_on: 'eval:doc.select_scope == "id_range"'
            },
            {
                fieldname: 'id_start',
                fieldtype: 'Data',
                label: __('Mã số bắt đầu'),
                placeholder: '0001',
                description: __('Mã số nhân viên bắt đầu (không bao gồm tiền tố)'),
                depends_on: 'eval:doc.select_scope == "id_range"'
            },
            {
                fieldname: 'col_break1',
                fieldtype: 'Column Break',
                depends_on: 'eval:doc.select_scope == "id_range"'
            },
            {
                fieldname: 'id_end',
                fieldtype: 'Data',
                label: __('Mã số kết thúc'),
                placeholder: '0100',
                description: __('Mã số nhân viên kết thúc (không bao gồm tiền tố)'),
                depends_on: 'eval:doc.select_scope == "id_range"'
            },
            {
                fieldname: 'range_help',
                fieldtype: 'HTML',
                depends_on: 'eval:doc.select_scope == "id_range"',
                options: `
                    <div class="alert alert-info" style="font-size:12px;margin-top:8px">
                        <i class="fa fa-info-circle"></i>
                        <b>Ví dụ:</b> Nếu nhập ID Start = "0001" và ID End = "0100",
                        hệ thống sẽ tạo PDF cho tất cả nhân viên có mã từ TIQN-0001 đến TIQN-0100.
                    </div>
                `
            },
            {
                fieldname: 'info_section',
                fieldtype: 'Section Break'
            },
            {
                fieldname: 'employee_info',
                fieldtype: 'HTML'
            },
            {
                fieldname: 'options_section',
                fieldtype: 'Section Break',
                label: __('Tùy Chọn Báo Cáo')
            },
            {
                fieldname: 'company_name',
                fieldtype: 'Data',
                label: __('Tên Công Ty (Tiêu đề)'),
                default: 'CÔNG TY TNHH TORAY INTERNATIONAL VIET NAM - CHI NHÁNH QUẢNG NGÃI'
            },
            {
                fieldname: 'include_section',
                fieldtype: 'Check',
                label: __('Hiển thị cột Tổ/Section'),
                default: 1
            },
            {
                fieldname: 'include_department',
                fieldtype: 'Check',
                label: __('Hiển thị cột Bộ phận'),
                default: 0
            },

            {
                fieldname: 'column_break_1',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'include_notes',
                fieldtype: 'Check',
                label: __('Hiển thị cột Ghi chú'),
                default: 1
            },
            {
                fieldname: 'page_size',
                fieldtype: 'Select',
                label: __('Kích thước trang'),
                options: ['A4', 'Letter'],
                default: 'A4'
            },
            {
                fieldname: 'orientation',
                fieldtype: 'Select',
                label: __('Hướng giấy'),
                options: ['Portrait', 'Landscape'],
                default: 'Portrait'
            }
        ],
        size: 'large',
        primary_action_label: __('Tạo PDF'),
        primary_action(values) {
            // Validate inputs
            if (values.select_scope === 'id_range') {
                if (!values.id_start || !values.id_end) {
                    frappe.msgprint({
                        title: __('Thiếu Thông Tin'),
                        message: __('Vui lòng điền cả mã số bắt đầu và mã số kết thúc.'),
                        indicator: 'orange'
                    });
                    return;
                }

                // Check if input is numeric
                if (!/^\d+$/.test(values.id_start) || !/^\d+$/.test(values.id_end)) {
                    frappe.msgprint({
                        title: __('Định Dạng Không Hợp Lệ'),
                        message: __('Mã số nhân viên phải là các chữ số (không bao gồm tiền tố).'),
                        indicator: 'orange'
                    });
                    return;
                }

                // Convert to numbers for comparison
                const start_num = parseInt(values.id_start, 10);
                const end_num = parseInt(values.id_end, 10);

                // Check valid range
                if (start_num > end_num) {
                    frappe.msgprint({
                        title: __('Khoảng Không Hợp Lệ'),
                        message: __('Mã số bắt đầu phải nhỏ hơn hoặc bằng mã số kết thúc.'),
                        indicator: 'orange'
                    });
                    return;
                }

                // Check if range is too large
                if (end_num - start_num > 1000) {
                    frappe.confirm(
                        __('Khoảng mã số nhân viên bạn chọn rất lớn ({0} nhân viên). Bạn có chắc chắn muốn tiếp tục?', [end_num - start_num + 1]),
                        () => {
                            // User confirmed, proceed
                            generatePDF(values);
                        }
                    );
                    return;
                }
            } else if (values.select_scope === 'selected' && selected_employees.length === 0) {
                frappe.msgprint({
                    title: __('Chưa Chọn Nhân Viên'),
                    message: __('Vui lòng chọn ít nhất một nhân viên hoặc chọn phạm vi khác.'),
                    indicator: 'orange'
                });
                return;
            }

            // All validations passed, proceed to generate PDF
            generatePDF(values);
        }
    });

    // Function to generate PDF based on selected scope and values
    function generatePDF(values) {
        // Hide dialog
        d.hide();

        // Show loading message
        frappe.show_alert({
            message: __('Đang tạo PDF danh sách nhân viên...'),
            indicator: 'blue'
        });

        // Prepare employee scope
        let employees;
        let scope_description;

        if (values.select_scope === 'all_active') {
            employees = 'all';
            scope_description = 'Tất cả nhân viên Active';
        } else if (values.select_scope === 'selected') {
            employees = selected_employees.map(emp => emp.name);
            scope_description = `${selected_employees.length} nhân viên đã chọn`;
        } else if (values.select_scope === 'id_range') {
            // Generate a list of employee IDs in the range
            const start_num = parseInt(values.id_start, 10);
            const end_num = parseInt(values.id_end, 10);
            const prefix = values.id_prefix || 'TIQN-';

            // Create array of IDs
            employees = [];
            for (let i = start_num; i <= end_num; i++) {
                // Format number with leading zeros
                const padded_num = String(i).padStart(values.id_start.length, '0');
                employees.push(`${prefix}${padded_num}`);
            }

            scope_description = `Nhân viên từ ${prefix}${values.id_start} đến ${prefix}${values.id_end}`;
        }

        // Call server method to generate PDF
        frappe.call({
            method: 'customize_erpnext.api.employee.employee_utils.generate_employee_list_pdf',
            args: {
                employees: employees,
                company_name: values.company_name,
                include_department: values.include_department ? 1 : 0,
                include_section: values.include_section ? 1 : 0,
                include_notes: values.include_notes ? 1 : 0,
                page_size: values.page_size,
                orientation: values.orientation
            },
            freeze: true,
            freeze_message: __('Đang tạo PDF...'),
            callback: function (r) {
                if (r.message && r.message.success) {
                    frappe.show_alert({
                        message: __('Tạo PDF thành công!'),
                        indicator: 'green'
                    });

                    // Get file URL and download directly
                    if (r.message.file_url) {
                        // Open PDF in a new tab
                        const site_url = frappe.urllib.get_base_url();
                        const file_url = site_url + r.message.file_url;

                        // Create and click an invisible link to download
                        const a = document.createElement('a');
                        a.href = file_url;
                        a.target = '_blank';
                        a.download = r.message.filename || 'Employee_List.pdf';
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);

                        frappe.show_alert({
                            message: __('PDF đã sẵn sàng! Đang mở file...'),
                            indicator: 'green'
                        }, 4);
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            message: __('Không tìm thấy URL file trong phản hồi'),
                            indicator: 'red'
                        });
                    }
                } else {
                    frappe.msgprint({
                        title: __('Error'),
                        message: r.message?.error || __('Không thể tạo PDF danh sách nhân viên'),
                        indicator: 'red'
                    });
                }
            },
            error: function (err) {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Đã xảy ra lỗi khi tạo PDF: {0}', [err.message || 'Lỗi không xác định']),
                    indicator: 'red'
                });
            }
        });
    }

    // Function to update display based on scope selection
    function update_scope_display() {
        let scope_type = d.get_value('select_scope');

        if (scope_type === 'all_active') {
            // Fetch count of active employees
            frappe.call({
                method: 'frappe.client.get_count',
                args: {
                    doctype: 'Employee',
                    filters: {
                        status: 'Active'
                    }
                },
                callback: function (r) {
                    const total_active = r.message || 0;
                    let info_html = `
                        <div class="alert alert-info">
                            <i class="fa fa-info-circle"></i>
                            <strong> Tất Cả Nhân Viên Active</strong><br>
                            PDF sẽ bao gồm tất cả <strong>${total_active}</strong> nhân viên đang hoạt động trong hệ thống.
                        </div>
                    `;
                    d.fields_dict.employee_info.$wrapper.html(info_html);
                }
            });
        } else if (scope_type === 'selected') {
            if (selected_employees.length > 0) {
                let info_html = `
                    <div class="alert alert-success">
                        <i class="fa fa-check-circle"></i>
                        <strong> Nhân Viên Đã Chọn</strong><br>
                        PDF sẽ chỉ bao gồm <strong>${selected_employees.length}</strong> nhân viên đã chọn từ danh sách.
                    </div>
                `;
                d.fields_dict.employee_info.$wrapper.html(info_html);
            } else {
                let info_html = `
                    <div class="alert alert-warning">
                        <i class="fa fa-exclamation-triangle"></i>
                        <strong> Chưa Chọn Nhân Viên</strong><br>
                        Vui lòng tick checkbox để chọn nhân viên từ danh sách hoặc chọn phạm vi khác.
                    </div>
                `;
                d.fields_dict.employee_info.$wrapper.html(info_html);
            }
        } else if (scope_type === 'id_range') {
            let id_prefix = d.get_value('id_prefix') || 'TIQN-';
            let id_start = d.get_value('id_start') || '????';
            let id_end = d.get_value('id_end') || '????';

            let info_html = `
                <div class="alert alert-info">
                    <i class="fa fa-filter"></i>
                    <strong> Theo Khoảng Mã Số</strong><br>
                    PDF sẽ bao gồm nhân viên có mã số từ <strong>${id_prefix}${id_start}</strong> đến <strong>${id_prefix}${id_end}</strong>.
                    <br><small>Hệ thống sẽ lọc các mã nhân viên trong khoảng này có trạng thái Active.</small>
                </div>
            `;
            d.fields_dict.employee_info.$wrapper.html(info_html);

            // Set up event listeners for range fields to update the info display
            d.fields_dict.id_prefix.$input.on('input', function () {
                update_scope_display();
            });

            d.fields_dict.id_start.$input.on('input', function () {
                update_scope_display();
            });

            d.fields_dict.id_end.$input.on('input', function () {
                update_scope_display();
            });
        }
    }

    // Initial update
    update_scope_display();

    // Show dialog
    d.show();
    d.$wrapper.find('.modal-dialog').addClass('modal-lg');
}

function show_bulk_update_holiday_dialog(listview) {
    // Get selected employees
    const selected_employees = listview.get_checked_items();

    // Lấy danh sách Holiday List
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Holiday List',
            fields: ['name', 'holiday_list_name', 'from_date', 'to_date', 'total_holidays'],
            filters: {},
            order_by: 'from_date desc',
            limit_page_length: 999
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                show_holiday_selection_dialog(selected_employees, r.message, listview);
            } else {
                frappe.msgprint({
                    title: __('Không Tìm Thấy Holiday List'),
                    message: __('Không tìm thấy Holiday List nào trong hệ thống.'),
                    indicator: 'red'
                });
            }
        }
    });
}

function show_holiday_selection_dialog(employees, holiday_lists, listview) {
    let employee_names = employees.map(e => e.name);
    let apply_to_all = false;

    let d = new frappe.ui.Dialog({
        title: __('Update Holiday List'),
        fields: [
            {
                fieldname: 'apply_to_all_section',
                fieldtype: 'Section Break',
                label: __('Apply To')
            },
            {
                fieldname: 'apply_to_all',
                fieldtype: 'Check',
                label: __('Apply to ALL Active Employees'),
                default: 0,
                onchange: function () {
                    apply_to_all = d.get_value('apply_to_all');
                    update_employee_display();
                }
            },
            {
                fieldname: 'info_section',
                fieldtype: 'Section Break'
            },
            {
                fieldname: 'employee_info',
                fieldtype: 'HTML'
            },
            {
                fieldname: 'section_1',
                fieldtype: 'Section Break',
                label: __('Employee List')
            },
            {
                fieldname: 'employee_list',
                fieldtype: 'HTML'
            },
            {
                fieldname: 'section_2',
                fieldtype: 'Section Break',
                label: __('Select Holiday List')
            },
            {
                fieldname: 'holiday_list',
                fieldtype: 'Link',
                label: __('Holiday List'),
                options: 'Holiday List',
                reqd: 1,
                get_query: function () {
                    return {
                        filters: {}
                    };
                },
                onchange: function () {
                    const selected_holiday = d.get_value('holiday_list');
                    if (selected_holiday) {
                        const holiday_info = holiday_lists.find(h => h.name === selected_holiday);
                        if (holiday_info) {
                            let info_html = `
                                <div class="alert alert-info" style="margin-top:10px">
                                    <strong>${holiday_info.holiday_list_name || holiday_info.name}</strong><br>
                                    <small>
                                        ${__('From')}: ${holiday_info.from_date} → ${__('To')}: ${holiday_info.to_date}<br>
                                        ${__('Total Holidays')}: <strong>${holiday_info.total_holidays || 0}</strong>
                                    </small>
                                </div>
                            `;
                            d.fields_dict.holiday_info.$wrapper.html(info_html);
                        }
                    }
                }
            },
            {
                fieldname: 'column_break_1',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'holiday_info',
                fieldtype: 'HTML'
            }
        ],
        size: 'large',
        primary_action_label: __('Update Now'),
        primary_action(values) {
            if (!values.holiday_list) {
                frappe.msgprint({
                    title: __('Missing Information'),
                    message: __('Please select a Holiday List before updating.'),
                    indicator: 'orange'
                });
                return;
            }

            // Xác định scope cập nhật
            let target_employees = [];
            let scope_text = '';

            if (apply_to_all) {
                target_employees = 'all';  // Flag for backend to process
                scope_text = __('ALL Active Employees in the system');
            } else {
                if (employee_names.length === 0) {
                    frappe.msgprint({
                        title: __('No Employee Selected'),
                        message: __('Please select at least one employee or check "Apply to ALL Active Employees".'),
                        indicator: 'orange'
                    });
                    return;
                }
                target_employees = employee_names;
                scope_text = `<strong>${employee_names.length}</strong> ${__('selected employees')}`;
            }

            // Confirm action
            frappe.confirm(
                __('Are you sure you want to update Holiday List <strong>{0}</strong> for {1}?',
                    [values.holiday_list, scope_text]),
                function () {
                    d.hide();

                    // Call API to update
                    frappe.call({
                        method: 'customize_erpnext.api.employee.employee_utils.bulk_update_employee_holiday_list',
                        args: {
                            employees: target_employees,
                            holiday_list: values.holiday_list
                        },
                        freeze: true,
                        freeze_message: __('Updating Holiday List...'),
                        callback: function (r) {
                            if (r.message && r.message.success) {
                                // Show success message
                                frappe.msgprint({
                                    title: __('Update Successful'),
                                    message: r.message.message,
                                    indicator: 'green'
                                });

                                // Show summary
                                frappe.show_alert({
                                    message: __('Updated {0}/{1} employees',
                                        [r.message.updated_count, r.message.total_count]),
                                    indicator: 'green'
                                }, 10);

                                // Refresh list
                                listview.refresh();

                                // Clear selected items
                                listview.clear_checked_items();
                            }
                        },
                        error: function (r) {
                            frappe.msgprint({
                                title: __('Error'),
                                message: r.message || __('An error occurred while updating Holiday List'),
                                indicator: 'red'
                            });
                        }
                    });
                }
            );
        }
    });

    // Function để cập nhật hiển thị
    function update_employee_display() {
        if (apply_to_all) {
            // Lấy tổng số nhân viên Active
            frappe.call({
                method: 'frappe.client.get_count',
                args: {
                    doctype: 'Employee',
                    filters: {
                        status: 'Active'
                    }
                },
                callback: function (r) {
                    const total_active = r.message || 0;

                    let info_html = `
                        <div class="alert alert-danger">
                            <i class="fa fa-exclamation-triangle"></i>
                            <strong> ${__('WARNING: APPLYING TO ALL')}</strong><br>
                            ${__('You are about to apply to')} <strong>${total_active}</strong> ${__('Active employees in the system!')}
                        </div>
                    `;
                    d.fields_dict.employee_info.$wrapper.html(info_html);

                    let placeholder_html = `
                        <div style="padding:30px;text-align:center;border:2px dashed var(--border-color);border-radius:8px">
                            <i class="fa fa-users" style="font-size:36px;color:var(--text-muted);margin-bottom:12px"></i>
                            <h4>${__('Apply to ALL Employees')}</h4>
                            <p class="text-muted">
                                ${__('Total')}: <strong>${total_active}</strong> ${__('Active employees')}<br>
                                <small>${__('Uncheck the checkbox above to apply only to selected employees')}</small>
                            </p>
                        </div>
                    `;
                    d.fields_dict.employee_list.$wrapper.html(placeholder_html);
                }
            });
        } else {
            // Hiển thị thông tin nhân viên đã chọn
            d.fields_dict.employee_info.$wrapper.html('');

            if (employees.length === 0) {
                let no_selection_html = `
                    <div style="padding:30px;text-align:center;border:2px dashed var(--border-color);border-radius:8px">
                        <i class="fa fa-hand-pointer-o" style="font-size:36px;color:var(--text-muted);margin-bottom:12px"></i>
                        <h4 class="text-muted">${__('No employees selected')}</h4>
                        <p class="text-muted">
                            ${__('Please check the checkboxes to select employees from the list')}<br>
                            ${__('or check "Apply to ALL Active Employees"')}
                        </p>
                    </div>
                `;
                d.fields_dict.employee_list.$wrapper.html(no_selection_html);
            } else {
                render_employee_list(employees);
            }
        }
    }

    // Function render danh sách nhân viên
    function render_employee_list(emp_list) {
        let employee_html = `
            <div style="max-height:320px;overflow-y:auto;border:1px solid var(--border-color);border-radius:8px">
                <table class="table table-sm table-hover mb-0" style="font-size:13px">
                    <thead style="position:sticky;top:0;background:var(--bg-color);z-index:1">
                        <tr>
                            <th style="padding:8px">#</th>
                            <th style="padding:8px">${__('Employee ID')}</th>
                            <th style="padding:8px">${__('Employee Name')}</th>
                            <th style="padding:8px">${__('Current Holiday List')}</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        emp_list.forEach((emp, index) => {
            employee_html += `
                <tr>
                    <td class="text-muted" style="padding:8px">${index + 1}</td>
                    <td style="padding:8px">
                        <span class="indicator-pill blue">${emp.name}</span>
                    </td>
                    <td style="padding:8px"><strong>${emp.employee_name || emp.name}</strong></td>
                    <td style="padding:8px">
                        ${emp.holiday_list
                    ? `<span class="indicator-pill green">${emp.holiday_list}</span>`
                    : `<span class="indicator-pill orange">${__('Not Assigned')}</span>`}
                    </td>
                </tr>
            `;
        });

        employee_html += `
                    </tbody>
                </table>
            </div>
        `;

        d.fields_dict.employee_list.$wrapper.html(employee_html);
    }

    // Initial display
    update_employee_display();

    // Show dialog
    d.show();
    d.$wrapper.find('.modal-dialog').addClass('modal-lg');
}

function show_get_fingerprint_dialog(listview) {
    // If exactly one employee is selected, skip the dialog and open scanner directly
    const selected = listview ? listview.get_checked_items() : [];
    if (selected.length === 1) {
        const emp = selected[0];
        if (window.FingerprintScannerDialog && window.FingerprintScannerDialog.showForEmployee) {
            window.FingerprintScannerDialog.showForEmployee(emp.name, emp.employee_name || emp.name);
        } else {
            frappe.msgprint({
                title: __('Lỗi Tải Module'),
                message: __('Không thể tải module máy quét vân tay. Vui lòng làm mới trang và thử lại.'),
                indicator: 'red'
            });
        }
        return;
    }

    // No selection or multiple → show dialog to pick one employee
    let d = new frappe.ui.Dialog({
        title: __('Chọn Nhân Viên Để Quét Vân Tay'),
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
        primary_action_label: __('Bắt Đầu Quét'),
        primary_action(values) {
            if (!values.employee) {
                frappe.msgprint({
                    title: __('Thiếu Thông Tin'),
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
                            title: __('Lỗi Tải Module'),
                            message: __('Không thể tải module máy quét vân tay. Vui lòng làm mới trang và thử lại.'),
                            indicator: 'red'
                        });
                    }
                }
            });
        }
    });

    d.show();
    d.$wrapper.find('.modal-dialog').addClass('modal-lg');
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

// ---------------------------------------------------------------------------
// 4.2. Sync Fingerprint From Attendance Machines to Other & ERP
// ---------------------------------------------------------------------------

function show_sync_fingerprint_from_machines_dialog(listview) {
    const selected_employees = listview.get_checked_items();
    frappe.show_alert({ message: __('Loading machines…'), indicator: 'blue' });
    frappe.call({
        method: 'customize_erpnext.api.biometric_sync.get_attendance_machines',
        callback: function (r) {
            if (!r.message || r.message.status !== 'success') {
                frappe.msgprint({ title: __('Error'), message: __('Failed to load attendance machines'), indicator: 'red' });
                return;
            }
            _fp_show_config_dialog(selected_employees, r.message.machines);
        },
        error: function () {
            frappe.msgprint({ title: __('Error'), message: __('Failed to load attendance machines'), indicator: 'red' });
        }
    });
}

function _fp_show_config_dialog(selected_employees, machines) {
    const emp_count = selected_employees.length;
    const def_master = machines.find(m => m.master_device) || machines[0];
    const def_master_name = def_master ? def_master.name : '';

    // --- Employee banner ---
    let emp_info_html;
    if (emp_count > 1) {
        const list = selected_employees.slice(0, 5)
            .map(e => `<strong>${e.employee_name || e.name}</strong> (${e.name})`).join(', ');
        const more = emp_count > 5 ? ` <span class="text-muted">… +${emp_count - 5} more</span>` : '';
        emp_info_html = `<div class="alert alert-info d-flex align-items-start" style="margin-bottom:0;padding:10px 14px">
            <i class="fa fa-users" style="font-size:17px;margin-right:10px;margin-top:1px;flex-shrink:0"></i>
            <div><strong>${emp_count} employees selected:</strong> ${list}${more}</div>
        </div>`;
    } else if (emp_count === 1) {
        const e = selected_employees[0];
        emp_info_html = `<div class="alert alert-info d-flex align-items-center" style="margin-bottom:0;padding:10px 14px">
            <i class="fa fa-user" style="font-size:17px;margin-right:10px;flex-shrink:0"></i>
            <div><strong>${e.employee_name || e.name}</strong> <span class="text-muted">(${e.name})</span></div>
        </div>`;
    } else {
        emp_info_html = `<div class="alert alert-warning" style="margin-bottom:0;padding:10px 14px">
            <i class="fa fa-exclamation-triangle"></i> No employees selected — enter IDs below.
        </div>`;
    }

    // --- Master dropdown ---
    const master_opts = machines.map(m =>
        `<option value="${m.name}"${m.name === def_master_name ? ' selected' : ''}>` +
        `${m.name}${m.device_name ? ' — ' + m.device_name : ''} (${m.ip_address || ''})</option>`
    ).join('');

    // --- Target list (read-only, always all machines except master) ---
    function build_target_list(exclude) {
        const targets = machines.filter(m => m.name !== exclude);
        if (!targets.length) {
            return `<div class="text-muted" style="padding:8px 4px">No other machines available</div>`;
        }
        return targets.map(m => {
            const meta = [m.device_name, m.ip_address].filter(Boolean).join(' · ');
            return `<div class="d-flex align-items-center" style="padding:6px 4px;border-bottom:1px solid #f0f0f0">
                <i class="fa fa-check-circle text-success" style="margin-right:8px;flex-shrink:0"></i>
                <strong style="margin-right:8px">${m.name}</strong>
                <span class="text-muted" style="font-size:12px">${meta}</span>
            </div>`;
        }).join('');
    }

    const config_html = `<div style="padding:2px 0">
        <div style="margin-bottom:12px">${emp_info_html}</div>

        <div style="margin-bottom:14px">
            <label class="text-muted" style="font-size:12px;margin-bottom:4px;display:block">
                Additional Employee IDs <span style="font-weight:normal">(one per line, optional)</span>
            </label>
            <textarea id="fp_extra_emp" class="form-control" rows="2"
                placeholder="TIQN-0001&#10;TIQN-0002" style="font-size:13px;resize:vertical"></textarea>
        </div>

        <div style="display:flex;gap:16px;margin-bottom:14px;align-items:flex-end">
            <div style="flex:1;min-width:0">
                <label class="text-muted" style="font-size:12px;margin-bottom:4px;display:block">
                    <i class="fa fa-star text-warning"></i>
                    <strong>Master Machine</strong>
                    <span style="font-weight:normal"> — source of fingerprint data</span>
                </label>
                <select id="fp_master_sel" class="form-control" style="font-size:13px">
                    ${master_opts}
                </select>
            </div>
            <div style="flex:0 0 auto;padding-bottom:4px">
                <label style="display:flex;align-items:center;gap:7px;cursor:pointer;
                              font-weight:normal;margin:0;white-space:nowrap">
                    <input type="checkbox" id="fp_sync_to_erp" checked style="width:15px;height:15px">
                    <span style="font-size:13px">Sync to ERPNext</span>
                </label>
            </div>
        </div>

        <div>
            <label class="text-muted" style="font-size:12px;margin-bottom:6px;display:block">
                <i class="fa fa-arrow-right text-info"></i>
                <strong>Target Machines</strong>
                <span style="font-weight:normal"> — all machines except master (auto)</span>
            </label>
            <div id="fp_target_list" style="border:1px solid #dee2e6;border-radius:6px;
                 padding:4px 8px;background:#f8f9fa;max-height:220px;overflow-y:auto">
                ${build_target_list(def_master_name)}
            </div>
        </div>
    </div>`;

    const d = new frappe.ui.Dialog({
        title: __('Sync Fingerprint: Machine → Machine & ERP'),
        fields: [{ fieldname: 'cfg', fieldtype: 'HTML', options: config_html }],
        primary_action_label: __('Start Sync'),
        primary_action: function () {
            _fp_on_submit(d, selected_employees, machines);
        },
    });
    d.show();
    d.$wrapper.find('.modal-dialog').addClass('modal-xl');

    // Master change → update target list display (always all except new master)
    d.$wrapper.find('#fp_master_sel').on('change', function () {
        d.$wrapper.find('#fp_target_list').html(build_target_list($(this).val()));
    });
}

function _fp_on_submit(d, selected_employees, machines) {
    const emp_set = new Set();
    selected_employees.forEach(e => emp_set.add(e.name));
    const manual_text = d.$wrapper.find('#fp_extra_emp').val() || '';
    manual_text.split('\n').map(s => s.trim()).filter(Boolean).forEach(s => emp_set.add(s));
    const employee_ids = [...emp_set];

    if (!employee_ids.length) {
        frappe.msgprint({ title: __('Missing Info'), message: __('No employees selected'), indicator: 'orange' });
        return;
    }

    const master_machine = d.$wrapper.find('#fp_master_sel').val();
    if (!master_machine) {
        frappe.msgprint({ title: __('Missing Info'), message: __('No master machine selected'), indicator: 'orange' });
        return;
    }

    // Always all machines except master — no user selection needed
    const target_machines = machines.map(m => m.name).filter(n => n !== master_machine);
    const sync_to_erp = d.$wrapper.find('#fp_sync_to_erp').is(':checked') ? 1 : 0;

    if (!target_machines.length && !sync_to_erp) {
        frappe.msgprint({ title: __('Missing Info'), message: __('No other machines available and ERP sync is off'), indicator: 'orange' });
        return;
    }

    d.get_primary_btn().prop('disabled', true).text('Processing…');

    frappe.call({
        method: 'customize_erpnext.api.biometric_sync.resolve_employee_device_ids',
        args: { employee_ids_json: JSON.stringify(employee_ids) },
        callback: function (r) {
            if (!r.message || r.message.status !== 'success') {
                d.get_primary_btn().prop('disabled', false).text('Start Sync');
                frappe.msgprint({ title: __('Error'), message: __('Could not fetch employee info'), indicator: 'red' });
                return;
            }
            const resolved = r.message.employees;
            const with_id = resolved.filter(e => e.attendance_device_id);
            const without_id = resolved.filter(e => !e.attendance_device_id);
            const user_ids = with_id.map(e => e.attendance_device_id);
            const employees_for_sync = with_id.map(e => ({ employee_id: e.employee_id, employee_name: e.employee_name }));

            if (!user_ids.length) {
                d.get_primary_btn().prop('disabled', false).text('Start Sync');
                frappe.msgprint({ title: __('Error'), message: __('None of the selected employees have an Attendance Device ID'), indicator: 'red' });
                return;
            }

            if (sync_to_erp) {
                frappe.call({
                    method: 'customize_erpnext.api.biometric_sync.check_employees_fingerprints_in_erp',
                    args: { employee_ids_json: JSON.stringify(with_id.map(e => e.employee_id)) },
                    callback: function (r2) {
                        const existing = (r2.message && r2.message.existing) || {};
                        const conflicts = Object.entries(existing);
                        const _do = () => _fp_start_sync(d, master_machine, target_machines, user_ids, employees_for_sync, sync_to_erp, without_id);
                        if (conflicts.length) {
                            const list = conflicts.map(([id, cnt]) => `${id} (${cnt} fingerprints)`).join(', ');
                            frappe.confirm(
                                `<b>${conflicts.length} employee(s)</b> already have fingerprint data in ERPNext:<br><i>${list}</i><br><br>Continuing will <b class="text-danger">overwrite</b> existing data. Confirm?`,
                                _do,
                                () => { d.get_primary_btn().prop('disabled', false).text('Start Sync'); }
                            );
                        } else {
                            _do();
                        }
                    },
                    error: function () {
                        d.get_primary_btn().prop('disabled', false).text('Start Sync');
                        frappe.msgprint({ title: __('Error'), message: __('Could not check existing ERP fingerprint data'), indicator: 'red' });
                    }
                });
            } else {
                _fp_start_sync(d, master_machine, target_machines, user_ids, employees_for_sync, sync_to_erp, without_id);
            }
        },
        error: function () {
            d.get_primary_btn().prop('disabled', false).text('Start Sync');
            frappe.msgprint({ title: __('Error'), message: __('Could not fetch employee info'), indicator: 'red' });
        }
    });
}

function _fp_start_sync(d, master_machine, target_machines, user_ids, employees_for_sync, sync_to_erp, skipped) {
    if (!sync_to_erp) {
        // No ERP sync — skip background job, go directly to device sync
        d.hide();
        _fp_show_progress_dialog(null, master_machine, target_machines, employees_for_sync, user_ids.length, skipped, sync_to_erp);
        return;
    }

    // ERP sync: enqueue background job (machine sync done from frontend after)
    frappe.call({
        method: 'customize_erpnext.api.biometric_sync.sync_fingerprints',
        args: {
            master_machine_name: master_machine,
            target_machine_names_json: '[]',
            user_ids_json: JSON.stringify(user_ids),
            sync_to_erp: sync_to_erp,
        },
        callback: function (r) {
            if (!r.message || r.message.status !== 'success') {
                d.get_primary_btn().prop('disabled', false).text('Start Sync');
                frappe.msgprint({ title: __('Error'), message: r.message && r.message.message || __('Failed to submit sync request'), indicator: 'red' });
                return;
            }
            const job_id = r.message.job_id;
            d.hide();
            _fp_show_progress_dialog(job_id, master_machine, target_machines, employees_for_sync, user_ids.length, skipped, sync_to_erp);
        },
        error: function () {
            d.get_primary_btn().prop('disabled', false).text('Start Sync');
            frappe.msgprint({ title: __('Error'), message: __('Failed to submit sync request'), indicator: 'red' });
        }
    });
}

function _fp_show_progress_dialog(job_id, master_machine, target_machines, employees_for_sync, total_users, skipped, sync_to_erp) {
    const dest_names = [...target_machines, ...(sync_to_erp ? ['ERPNext'] : [])];
    const skipped_html = (skipped && skipped.length)
        ? `<div class="alert alert-warning" style="margin-bottom:10px">
               <i class="fa fa-exclamation-triangle"></i>
               Skipped ${skipped.length} employee(s) with no Attendance Device ID:
               ${skipped.map(e => `<code>${e.employee_id}</code>`).join(' ')}
           </div>`
        : '';

    const prog_html = `
        <div class="alert alert-info" style="margin-bottom:15px">
            <div class="d-flex align-items-start">
                <i class="fa fa-info-circle" style="font-size:20px;margin-right:10px;margin-top:2px"></i>
                <div>
                    <strong>Master:</strong> ${master_machine}
                    &rarr; <strong>Target(s):</strong> ${dest_names.join(', ') || '(none)'}<br>
                    <strong>Total users:</strong> ${total_users}
                </div>
            </div>
        </div>
        ${skipped_html}
        <div style="margin-bottom:15px">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <strong>Overall Progress</strong>
                <span id="fp_phase_text" class="text-muted" style="font-size:13px">Starting...</span>
            </div>
            <div class="progress mb-2" style="height:25px">
                <div id="fp_prog_bar" class="progress-bar progress-bar-striped progress-bar-animated"
                     role="progressbar" style="width:0%">0%</div>
            </div>
        </div>
        <div id="fp_results_wrap" style="height:300px;overflow-y:auto;padding:15px;border-radius:8px;
             background:#f8f9fa;border:1px solid #dee2e6;font-family:monospace;font-size:13px">
            <div class="text-info">Waiting for sync results...</div>
        </div>`;

    const prog_d = new frappe.ui.Dialog({
        title: __('Fingerprint Sync Progress'),
        fields: [{ fieldname: 'prog_html', fieldtype: 'HTML', options: prog_html }],
        secondary_action_label: __('Close'),
        secondary_action: function () { prog_d.hide(); },
    });
    prog_d.show();
    prog_d.$wrapper.find('.modal-dialog').addClass('modal-xl');

    const has_erp = !!sync_to_erp;
    const has_devices = target_machines.length > 0;
    // Phase 1 (ERP sync) occupies 0 → phase1_end%; Phase 2 (device sync) phase1_end → 100%
    const phase1_end = has_erp ? (has_devices ? 50 : 100) : 0;

    if (!has_erp) {
        // No ERP sync — go straight to device sync
        _fp_do_device_sync(prog_d, employees_for_sync, target_machines, [], 0, 100);
        return;
    }

    // Phase 1: poll background job until done
    const poll = setInterval(function () {
        frappe.call({
            method: 'customize_erpnext.api.biometric_sync.get_sync_job_status',
            args: { job_id: job_id },
            callback: function (r) {
                if (!r.message || r.message.status !== 'success') return;
                const data = r.message.data;

                // Scale backend pct [0..100] → [0..phase1_end]
                const scaled_pct = Math.round((data.progress_pct || 0) * phase1_end / 100);
                _fp_update_progress(prog_d, {
                    progress_pct: scaled_pct,
                    phase: `[ERP] ${data.phase || ''}`,
                    results: data.results || [],
                    status: data.status,
                });

                if (data.status === 'done' || data.status === 'error') {
                    clearInterval(poll);
                    if (data.status === 'done' && has_devices) {
                        // Phase 2: sync to devices using ERP data
                        _fp_do_device_sync(prog_d, employees_for_sync, target_machines, data.results || [], phase1_end, 100);
                    } else {
                        _fp_finish_progress(prog_d, data.results || []);
                    }
                }
            }
        });
    }, 2000);
}

function _fp_update_progress(prog_d, data) {
    const w = prog_d.$wrapper;
    if (!w.find('#fp_prog_bar').length) return;

    const pct = data.progress_pct || 0;
    const phase = data.phase || '';
    const results = data.results || [];
    const is_done = data.status === 'done';
    const is_err = data.status === 'error';

    w.find('#fp_prog_bar')
        .css('width', pct + '%')
        .text(pct + '%')
        .toggleClass('progress-bar-success', is_done)
        .toggleClass('progress-bar-danger', is_err);
    w.find('#fp_phase_text').text(phase);

    if (results.length > 0) {
        const ok_count = results.filter(r => r.success).length;
        const err_count = results.length - ok_count;
        let log = `<div style="margin-bottom:8px">
            ${results.length} results &nbsp;·&nbsp;
            <span class="text-success">${ok_count} OK</span> &nbsp;
            <span class="text-danger">${err_count} Failed</span>
        </div>`;
        for (const res of results) {
            const cls = res.success ? 'text-success' : 'text-danger';
            const icon = res.success ? '[OK]' : '[ERR]';
            log += `<div style="margin:3px 0" class="${cls}">${icon} <strong>${res.user_id}</strong> → ${res.machine}: ${res.message}</div>`;
        }
        w.find('#fp_results_wrap').html(log);
    }
}

async function _fp_do_device_sync(prog_d, employees, target_machines, erp_results, pct_start, pct_end) {
    const total_calls = employees.length * target_machines.length;
    const all_results = [...erp_results];
    let done = 0;

    if (total_calls === 0) {
        _fp_finish_progress(prog_d, all_results);
        return;
    }

    for (const machine of target_machines) {
        for (const emp of employees) {
            await new Promise(function (resolve) {
                frappe.call({
                    method: 'customize_erpnext.api.utilities.sync_employee_to_single_machine',
                    args: { employee_id: emp.employee_id, machine_name: machine },
                    callback: function (r) {
                        done++;
                        const pct = pct_start + Math.round(done / total_calls * (pct_end - pct_start));
                        const ok = !!(r.message && r.message.success !== false && !r.exc);
                        const msg = (r.message && (r.message.message || r.message.status)) || 'OK';
                        all_results.push({ success: ok, user_id: emp.employee_id, machine: machine, message: msg });
                        _fp_update_progress(prog_d, {
                            progress_pct: pct,
                            phase: `[Device] ${emp.employee_id} → ${machine}: ${ok ? 'OK' : 'Failed'}`,
                            results: all_results,
                            status: 'running',
                        });
                        resolve();
                    },
                    error: function () {
                        done++;
                        const pct = pct_start + Math.round(done / total_calls * (pct_end - pct_start));
                        all_results.push({ success: false, user_id: emp.employee_id, machine: machine, message: 'Network error' });
                        _fp_update_progress(prog_d, {
                            progress_pct: pct,
                            phase: `[Device] ${emp.employee_id} → ${machine}: Failed`,
                            results: all_results,
                            status: 'running',
                        });
                        resolve();
                    }
                });
            });
        }
    }
    _fp_finish_progress(prog_d, all_results);
}

function _fp_finish_progress(prog_d, results) {
    const ok_count = results.filter(r => r.success).length;
    const err_count = results.length - ok_count;
    _fp_update_progress(prog_d, {
        progress_pct: 100,
        phase: `Done — ${ok_count} OK, ${err_count} failed`,
        results: results,
        status: 'done',
    });
    prog_d.$wrapper.find('#fp_prog_bar').removeClass('progress-bar-animated progress-bar-striped');
}

// ---------------------------------------------------------------------------
// 4.3. Delete fingerprint Data of Left Employees From Attendance Machines
// ---------------------------------------------------------------------------

function show_delete_left_employees_dialog() {
    const config_html = `<div style="padding:2px 0">
        <div class="alert alert-warning d-flex align-items-start" style="margin-bottom:16px">
            <i class="fa fa-exclamation-triangle" style="font-size:18px;margin-right:10px;margin-top:2px;flex-shrink:0"></i>
            <div>
                <strong>Important:</strong><br>
                • Active employees will <strong>never</strong> be deleted.<br>
                • ERPNext fingerprints will <strong>never</strong> be deleted — kept as backup, can re-sync anytime.<br>
                • Only deletes from attendance machines employees who have <strong>left</strong> past the threshold.
            </div>
        </div>

        <div style="display:flex;gap:20px;align-items:flex-end;margin-bottom:16px;flex-wrap:wrap">
            <div style="flex:0 0 auto">
                <label class="text-muted" style="font-size:12px;margin-bottom:4px;display:block">
                    <i class="fa fa-calendar"></i> Days after <code>relieving_date</code> before deleting
                </label>
                <select id="del_delay_days" class="form-control" style="font-size:13px;width:auto;min-width:120px">
                    <option value="15">15 days</option>
                    <option value="30">30 days</option>
                    <option value="45" selected>45 days (default)</option>
                    <option value="60">60 days</option>
                </select>
            </div>
            <div style="flex:0 0 auto;padding-bottom:4px">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:normal;margin:0">
                    <input type="checkbox" id="del_include_unmatched" style="width:15px;height:15px">
                    <span style="font-size:13px">
                        Also delete user_ids <strong>not matched</strong> to any Employee in ERPNext
                    </span>
                </label>
            </div>
        </div>

        <div class="text-muted" style="font-size:12px;padding:6px 0">
            <i class="fa fa-info-circle"></i>
            Click <strong>Scan</strong> to scan all enabled machines and preview the users that will be deleted.
        </div>
    </div>`;

    const d = new frappe.ui.Dialog({
        title: __('Delete Left Employees From Machines'),
        fields: [{ fieldname: 'cfg', fieldtype: 'HTML', options: config_html }],
        primary_action_label: __('Scan All Machines'),
        primary_action: function () {
            const delay_days = parseInt(d.$wrapper.find('#del_delay_days').val()) || 45;
            const include_unmatched = d.$wrapper.find('#del_include_unmatched').is(':checked') ? 1 : 0;

            d.get_primary_btn().prop('disabled', true).text(__('Scanning...'));
            frappe.show_alert({ message: __('Scanning machines…'), indicator: 'blue' });

            frappe.call({
                method: 'customize_erpnext.api.biometric_sync.get_left_employees_on_machines',
                args: { delay_days, include_unmatched },
                callback: function (r) {
                    d.hide();
                    if (!r.message || r.message.status !== 'success') {
                        frappe.msgprint({
                            title: __('Error'),
                            message: r.message ? r.message.message : 'Scan failed',
                            indicator: 'red',
                        });
                        return;
                    }
                    _del_show_preview_dialog(r.message, { delay_days, include_unmatched });
                },
                error: function () {
                    d.get_primary_btn().prop('disabled', false).text(__('Scan All Machines'));
                    frappe.msgprint({ title: __('Error'), message: __('Scan request failed'), indicator: 'red' });
                },
            });
        },
    });
    d.show();
    d.$wrapper.find('.modal-dialog').css('max-width', '640px');
}

function _del_show_preview_dialog(scan_result, config) {
    const users = scan_result.users_to_delete || [];
    const machines_scanned = scan_result.machines_scanned || [];
    const failed_machines = machines_scanned.filter(m => !m.success);

    // --- Machines scan summary ---
    const machines_html = machines_scanned.map(m => {
        const icon = m.success
            ? `<i class="fa fa-check-circle text-success"></i>`
            : `<i class="fa fa-times-circle text-danger"></i>`;
        const info = m.success
            ? `${m.total_users} users`
            : `<span class="text-danger">${m.error || 'Error'}</span>`;
        return `<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 6px 2px 0;
                    font-size:12px;padding:2px 6px;background:#f0f0f0;border-radius:4px">
            ${icon} <strong>${m.machine}</strong> (${info})
        </span>`;
    }).join('');

    // --- Users table ---
    let table_html = '';
    if (!users.length) {
        table_html = `<div class="alert alert-success">
            <i class="fa fa-check-circle"></i>
            <strong>No users to delete</strong> with the current settings.
        </div>`;
    } else {
        const left_count = users.filter(u => u.reason_type === 'left_employee').length;
        const unmatched_count = users.filter(u => u.reason_type === 'unmatched').length;

        const rows = users.map((u, idx) => {
            const group_tag = u.custom_group
                ? `<span class="badge badge-info" style="font-size:11px;margin-left:4px">${u.custom_group}</span>`
                : '';
            const emp_cell = u.employee_id
                ? `<strong>${u.employee_name || ''}</strong><br>
                   <small class="text-muted">${u.employee_id}</small>${group_tag}`
                : `<span class="text-muted fst-italic">— not in ERPNext</span>`;
            const reason_badge = u.reason_type === 'left_employee'
                ? `<span class="badge bg-warning text-dark" style="font-size:11px">Left</span>`
                : `<span class="badge bg-secondary text-white" style="font-size:11px">Unmatched</span>`;
            const rd_cell = u.relieving_date
                ? `${u.relieving_date}<br><small class="text-danger">+${u.days_since_relieving}d</small>`
                : '—';
            const machine_tags = (u.machines || []).map(m =>
                `<span style="display:inline-block;font-size:11px;padding:1px 5px;
                    background:#e9ecef;border-radius:3px;margin:1px 2px 1px 0">${m}</span>`
            ).join('');
            return `<tr>
                <td style="text-align:center;width:36px;padding:6px 4px">
                    <input type="checkbox" class="del-user-chk" data-idx="${idx}" checked
                        style="width:14px;height:14px;cursor:pointer">
                </td>
                <td style="padding:6px 8px"><strong>${u.user_id}</strong></td>
                <td style="padding:6px 8px">${emp_cell}</td>
                <td style="padding:6px 8px">${reason_badge}<br><small class="text-muted">${u.reason}</small></td>
                <td style="padding:6px 8px;white-space:nowrap">${rd_cell}</td>
                <td style="padding:6px 8px">${machine_tags}</td>
            </tr>`;
        }).join('');

        table_html = `
        <div class="d-flex align-items-center justify-content-between" style="margin-bottom:8px">
            <div style="font-size:13px">
                <span class="badge bg-danger text-white" style="font-size:12px">${users.length} users to delete</span>
                &nbsp;
                ${left_count ? `<span class="badge bg-warning text-dark" style="font-size:11px">${left_count} Left employee</span>&nbsp;` : ''}
                ${unmatched_count ? `<span class="badge bg-secondary text-white" style="font-size:11px">${unmatched_count} Unmatched</span>` : ''}
            </div>
            <div style="font-size:12px">
                <a href="#" id="del_select_all" style="margin-right:10px">Select all</a>
                <a href="#" id="del_deselect_all">Deselect all</a>
            </div>
        </div>
        <div style="max-height:340px;overflow-y:auto;border:1px solid #dee2e6;border-radius:6px">
            <table class="table table-sm table-hover" style="margin-bottom:0;font-size:13px">
                <thead style="position:sticky;top:0;background:#f8f9fa;z-index:1">
                    <tr>
                        <th style="width:36px;text-align:center;padding:6px 4px"></th>
                        <th style="padding:6px 8px">User ID</th>
                        <th style="padding:6px 8px">Employee</th>
                        <th style="padding:6px 8px">Reason</th>
                        <th style="padding:6px 8px;white-space:nowrap">Relieving Date</th>
                        <th style="padding:6px 8px">Machines</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    }

    const failed_warn = failed_machines.length
        ? `<div class="alert alert-warning" style="margin-bottom:12px;font-size:13px">
               <i class="fa fa-exclamation-triangle"></i>
               <strong>${failed_machines.length} machine(s) unreachable:</strong>
               ${failed_machines.map(m => `<code>${m.machine}</code>`).join(', ')}
           </div>`
        : '';

    const preview_html = `<div style="padding:2px 0">
        <div style="margin-bottom:12px">
            <div class="text-muted" style="font-size:12px;margin-bottom:6px">
                <i class="fa fa-server"></i> Machines scanned:
            </div>
            <div style="flex-wrap:wrap;display:flex">${machines_html}</div>
        </div>
        ${failed_warn}
        <div class="text-muted" style="font-size:12px;margin-bottom:8px">
            <i class="fa fa-info-circle"></i>
            Today: <strong>${scan_result.today}</strong> &nbsp;|&nbsp;
            Threshold: <strong>${config.delay_days} days</strong> &nbsp;|&nbsp;
            Total unique user IDs on devices: <strong>${scan_result.total_unique_user_ids}</strong> &nbsp;|&nbsp;
            Kept (Active / within threshold): <strong>${scan_result.users_to_keep_count}</strong>
        </div>
        ${table_html}
        <div class="alert alert-info d-flex align-items-start" style="margin-top:14px;margin-bottom:0;font-size:13px">
            <i class="fa fa-lock" style="margin-right:8px;margin-top:2px;flex-shrink:0"></i>
            <div>ERPNext fingerprint records will <strong>not</strong> be deleted
            — kept as backup and can be re-synced to devices at any time.</div>
        </div>
    </div>`;

    const prev_d = new frappe.ui.Dialog({
        title: __('Confirm Delete — Users To Be Removed From Machines'),
        fields: [{ fieldname: 'preview', fieldtype: 'HTML', options: preview_html }],
        primary_action_label: users.length ? __('Delete Selected') : __('Close'),
        primary_action: function () {
            if (!users.length) { prev_d.hide(); return; }

            // Collect checked users
            const checked_indices = [];
            prev_d.$wrapper.find('.del-user-chk:checked').each(function () {
                checked_indices.push(parseInt($(this).data('idx')));
            });
            if (!checked_indices.length) {
                frappe.show_alert({ message: __('No users selected'), indicator: 'orange' });
                return;
            }

            const selected_users = checked_indices.map(i => users[i]);
            const unique_machines = [...new Set(selected_users.flatMap(u => u.machines || []))];

            frappe.confirm(
                __('Delete <strong>{0} user(s)</strong> from <strong>{1} machine(s)</strong>?<br>' +
                   '<small class="text-muted">ERPNext fingerprint records will be kept as backup.</small>',
                   [selected_users.length, unique_machines.length]),
                function () {
                    prev_d.hide();
                    _del_start_delete(selected_users);
                }
            );
        },
        secondary_action_label: __('Back'),
        secondary_action: function () {
            prev_d.hide();
            show_delete_left_employees_dialog();
        },
    });
    prev_d.show();
    prev_d.$wrapper.find('.modal-dialog').addClass('modal-xl');

    // Select/deselect all handlers
    prev_d.$wrapper.on('click', '#del_select_all', function (e) {
        e.preventDefault();
        prev_d.$wrapper.find('.del-user-chk').prop('checked', true);
    });
    prev_d.$wrapper.on('click', '#del_deselect_all', function (e) {
        e.preventDefault();
        prev_d.$wrapper.find('.del-user-chk').prop('checked', false);
    });
}

function _del_start_delete(selected_users) {
    frappe.call({
        method: 'customize_erpnext.api.biometric_sync.delete_users_from_machines',
        args: { users_json: JSON.stringify(selected_users) },
        callback: function (r) {
            if (!r.message || r.message.status !== 'success') {
                frappe.msgprint({
                    title: __('Error'),
                    message: (r.message && r.message.message) || 'Failed to start delete job',
                    indicator: 'red',
                });
                return;
            }
            const job_id = r.message.job_id;
            const total_ops = selected_users.reduce((n, u) => n + (u.machines || []).length, 0);
            const unique_machines = [...new Set(selected_users.flatMap(u => u.machines || []))];
            _del_show_progress_dialog(job_id, selected_users.length, total_ops, unique_machines);
        },
        error: function () {
            frappe.msgprint({ title: __('Error'), message: __('Failed to submit delete job'), indicator: 'red' });
        },
    });
}

function _del_show_progress_dialog(job_id, user_count, total_ops, machines) {
    const prog_html = `
        <div class="alert alert-danger d-flex align-items-start" style="margin-bottom:15px">
            <i class="fa fa-trash" style="font-size:20px;margin-right:10px;margin-top:2px"></i>
            <div>
                Deleting <strong>${user_count} users</strong> from
                <strong>${machines.length} machine(s)</strong>: ${machines.join(', ')}<br>
                <small class="text-muted">ERPNext fingerprint records are not affected.</small>
            </div>
        </div>
        <div style="margin-bottom:15px">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <strong>Delete Progress</strong>
                <span id="fp_phase_text" class="text-muted" style="font-size:13px">Starting...</span>
            </div>
            <div class="progress mb-2" style="height:25px">
                <div id="fp_prog_bar" class="progress-bar progress-bar-striped progress-bar-animated bg-danger"
                     role="progressbar" style="width:0%">0%</div>
            </div>
        </div>
        <div id="fp_results_wrap" style="height:300px;overflow-y:auto;padding:15px;border-radius:8px;
             background:#f8f9fa;border:1px solid #dee2e6;font-family:monospace;font-size:13px">
            <div class="text-info">Waiting for results...</div>
        </div>`;

    const prog_d = new frappe.ui.Dialog({
        title: __('Delete Progress'),
        fields: [{ fieldname: 'prog_html', fieldtype: 'HTML', options: prog_html }],
        secondary_action_label: __('Close'),
        secondary_action: function () { prog_d.hide(); },
    });
    prog_d.show();
    prog_d.$wrapper.find('.modal-dialog').addClass('modal-xl');

    const poll = setInterval(function () {
        frappe.call({
            method: 'customize_erpnext.api.biometric_sync.get_sync_job_status',
            args: { job_id },
            callback: function (r) {
                if (!r.message || r.message.status !== 'success') return;
                const data = r.message.data;

                _fp_update_progress(prog_d, {
                    progress_pct: data.progress_pct || 0,
                    phase: data.phase || '',
                    results: data.results || [],
                    status: data.status,
                });

                if (data.status === 'done' || data.status === 'error') {
                    clearInterval(poll);
                    _fp_finish_progress(prog_d, data.results || []);
                }
            },
        });
    }, 1500);
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
                fieldname: 'max_length_font_20',
                fieldtype: 'Int',
                label: __('Max Length for Font 20pt'),
                default: 20,
                description: __('Names shorter than this will use 20pt font (default: 20)')
            },
            {
                fieldname: 'name_font_size',
                fieldtype: 'Select',
                label: __('Font Size for Long Names (pt)'),
                options: ['19', '18', '17', '16'],
                default: '18',
                description: __('Font size for names >= max length (default: 18pt)')
            },
            {
                fieldname: 'with_barcode',
                fieldtype: 'Check',
                label: __('With Barcode'),
                default: 0,
                description: __('Include Code39 barcode below employee photo')
            },
            {
                fieldname: 'output_type',
                fieldtype: 'Select',
                label: __('Output Type'),
                options: ['pdf', 'html'],
                default: 'pdf',
                description: __('pdf: tải xuống PDF ngay | html: mở tab mới, có thể chỉnh sửa & in')
            },
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

                        generate_cards_for_employees(employee_ids, values.with_barcode, values.page_size || 'A4', values.name_font_size || 18, values.max_length_font_20 || 20, values.output_type || 'pdf');
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

function generate_cards_for_employees(employee_ids, with_barcode, page_size, name_font_size, max_length_font_20, output_type, card_border_radius) {
    output_type = output_type || 'html';
    const common_args = {
        employee_ids: employee_ids,
        with_barcode: with_barcode ? 1 : 0,
        page_size: page_size || 'A4',
        name_font_size: name_font_size || 18,
        max_length_font_20: max_length_font_20 || 20,
        card_border_radius: card_border_radius !== undefined ? card_border_radius : 1
    };

    if (output_type === 'html') {
        frappe.call({
            method: 'customize_erpnext.api.employee.employee_utils.generate_employee_cards_html_api',
            args: common_args,
            freeze: true,
            freeze_message: __('Generating employee cards...'),
            callback: function (r) {
                if (r.message && r.message.html) {
                    frappe.show_alert({ message: __('Opening HTML in new tab...'), indicator: 'green' });
                    open_employee_cards_html_tab(r.message.html);
                } else {
                    frappe.msgprint({ title: __('Error'), message: __('Failed to generate employee cards HTML'), indicator: 'red' });
                }
            },
            error: function (r) {
                frappe.msgprint({ title: __('Error'), message: __('An error occurred: {0}', [r.message || 'Unknown error']), indicator: 'red' });
            }
        });
    } else {
        frappe.call({
            method: 'customize_erpnext.api.employee.employee_utils.generate_employee_cards_pdf',
            args: common_args,
            callback: function (r) {
                if (r.message && r.message.pdf_data && r.message.pdf_filename) {
                    frappe.show_alert({ message: __('Employee cards generated successfully'), indicator: 'green' });
                    const linkSource = `data:application/pdf;base64,${r.message.pdf_data}`;
                    const downloadLink = document.createElement('a');
                    downloadLink.href = linkSource;
                    downloadLink.download = r.message.pdf_filename;
                    downloadLink.click();
                } else {
                    frappe.msgprint({ title: __('Error'), message: __('Failed to generate employee cards PDF'), indicator: 'red' });
                }
            },
            error: function (r) {
                frappe.msgprint({ title: __('Error'), message: __('An error occurred: {0}', [r.message || 'Unknown error']), indicator: 'red' });
            }
        });
    }
}

function open_employee_cards_html_tab(html) {
    const inject = `
<style>
    #ec-toolbar {
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 9999;
        background: #f8f9fa;
        border-bottom: 1px solid #dee2e6;
        padding: 6px 16px;
        display: flex;
        align-items: center;
        gap: 10px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        font-size: 13px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }
    #ec-toolbar .tb-title {
        font-weight: 600;
        color: #343a40;
    }
    #ec-toolbar .tb-sep {
        color: #ced4da;
        font-size: 18px;
        line-height: 1;
    }
    #ec-toolbar label { color: #495057; }
    #ec-fs {
        width: 54px;
        padding: 3px 6px;
        border: 1px solid #ced4da;
        border-radius: 4px;
        font-size: 13px;
        text-align: center;
    }
    #ec-fs-hint { color: #6c757d; font-size: 12px; }
    #ec-btn-apply {
        padding: 4px 14px;
        background: #0d6efd;
        color: #fff;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 13px;
    }
    #ec-btn-apply:hover { background: #0b5ed7; }
    #ec-msg {
        color: #dc3545;
        font-size: 12px;
        display: none;
    }
    #ec-btn-print {
        padding: 4px 16px;
        background: #198754;
        color: #fff;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 13px;
    }
    #ec-btn-print:hover { background: #146c43; }
    @media screen { body { padding-top: 44px; } }
    @media print {
        #ec-toolbar { display: none !important; }
        body { padding-top: 0 !important; margin: 0 !important; }
    }
</style>
<div id="ec-toolbar">
    <span class="tb-title">Employee Cards Preview</span>
    <span class="tb-sep">|</span>
    <label for="ec-fs">Font size:</label>
    <input id="ec-fs" type="number" value="18" min="6" max="72">
    <span style="color:#495057">pt</span>
    <button id="ec-btn-apply" onmousedown="event.preventDefault()" onclick="applyFS()">Apply</button>
    <span id="ec-msg">Select text first</span>
    <span class="tb-sep">|</span>
    <span id="ec-fs-hint">Select text, set size, click Apply (or Enter)</span>
    <span style="flex:1"></span>
    <button id="ec-btn-print" onclick="window.print()">Print</button>
</div>
<script>
function applyFS() {
    var pt = parseInt(document.getElementById('ec-fs').value, 10);
    var msg = document.getElementById('ec-msg');
    if (!pt || pt < 1) return;
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
        msg.style.display = 'inline';
        setTimeout(function() { msg.style.display = 'none'; }, 2500);
        return;
    }
    msg.style.display = 'none';
    var range = sel.getRangeAt(0);
    // Flatten existing font-size spans inside selection to avoid nesting conflicts
    var frag = range.extractContents();
    var tmp = document.createElement('div');
    tmp.appendChild(frag);
    tmp.querySelectorAll('span[style]').forEach(function(s) {
        s.style.fontSize = '';
        if (!s.getAttribute('style')) s.removeAttribute('style');
    });
    var span = document.createElement('span');
    span.style.fontSize = pt + 'pt';
    while (tmp.firstChild) span.appendChild(tmp.firstChild);
    range.insertNode(span);
    sel.removeAllRanges();
    var newRange = document.createRange();
    newRange.selectNodeContents(span);
    sel.addRange(newRange);
}
document.getElementById('ec-fs').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); applyFS(); }
});
</script>`;

    const editable_html = html
        .replace(/<body([^>]*)>/, (_m, attrs) => `<body${attrs} contenteditable="true">${inject}`);

    const tab = window.open('', '_blank');
    if (!tab) {
        frappe.msgprint({ title: __('Popup Blocked'), message: __('Please allow popups for this site and try again.'), indicator: 'orange' });
        return;
    }
    tab.document.open();
    tab.document.write(editable_html);
    tab.document.close();
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
            // ── Info ─────────────────────────────────────────────
            {
                fieldname: 'info_section',
                fieldtype: 'Section Break',
                label: __('Thông Tin')
            },
            {
                fieldname: 'employee_count',
                fieldtype: 'HTML',
                options: `<p style="margin: 4px 0 2px;">${__('Tạo thẻ cho {0} nhân viên đã chọn.', [selected_employees.length])}</p>`
            },
            // ── Page & Output ─────────────────────────────────────
            {
                fieldname: 'settings_section',
                fieldtype: 'Section Break',
                label: __('Thiết Lập Trang')
            },
            {
                fieldname: 'page_size',
                fieldtype: 'Select',
                label: __('Kích thước trang'),
                options: ['A4', 'A5'],
                default: 'A4'
            },
            {
                fieldname: 'output_type',
                fieldtype: 'Select',
                label: __('Kiểu xuất'),
                options: ['html', 'pdf'],
                default: 'html',
                description: __('HTML: Mở tab mới, chỉnh sửa & in | PDF: Tải file PDF')
            },
            {
                fieldname: 'col_break_1',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'with_barcode',
                fieldtype: 'Check',
                label: __('Hiển thị Barcode'),
                default: 0,
                description: __('Thêm barcode Code39 dưới ảnh nhân viên')
            },
            {
                fieldname: 'card_border_radius',
                fieldtype: 'Check',
                label: __('Bo góc thẻ (2mm)'),
                default: 0,
                description: __('Áp dụng border-radius: 2mm cho viền thẻ')
            },
            // ── Font ─────────────────────────────────────────────
            {
                fieldname: 'font_section',
                fieldtype: 'Section Break',
                label: __('Font Chữ')
            },
            {
                fieldname: 'max_length_font_20',
                fieldtype: 'Int',
                label: __('Ngưỡng dùng font 20pt'),
                default: 20,
                description: __('Tên ngắn hơn giá trị này dùng font 20pt')
            },
            {
                fieldname: 'col_break_2',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'name_font_size',
                fieldtype: 'Select',
                label: __('Font tên dài (pt)'),
                options: ['19', '18', '17', '16'],
                default: '18',
                description: __('Cỡ chữ cho tên >= ngưỡng (mặc định: 18pt)')
            }
        ],
        size: 'large',
        primary_action_label: __('Tạo Thẻ'),
        primary_action: function (values) {
            d.hide();

            const employee_ids = selected_employees.map(emp => emp.name);

            frappe.show_alert({
                message: __('Đang tạo thẻ nhân viên...'),
                indicator: 'blue'
            });

            generate_cards_for_employees(
                employee_ids,
                values.with_barcode,
                values.page_size || 'A4',
                values.name_font_size || 18,
                values.max_length_font_20 || 20,
                values.output_type || 'html',
                values.card_border_radius ? 1 : 0
            );
        }
    });

    d.show();

    // Force reset to A4 default each time dialog opens
    d.set_value('page_size', 'A4');
}

function show_update_employee_photo_dialog(listview) {
    // Holds the FileList from the input — no pre-upload
    let selected_files = null;

    // Helper: read File as base64 data URL
    function file_to_base64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => resolve(e.target.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    let d = new frappe.ui.Dialog({
        title: __('Update Employee Photo'),
        fields: [
            {
                fieldname: 'photo_section',
                fieldtype: 'Section Break',
                label: __('Select Photos')
            },
            {
                fieldname: 'file_upload',
                fieldtype: 'HTML',
                options: `
                    <div class="form-group">
                        <label class="control-label" style="padding-right: 0px;">
                            ${__('Employee Photos')}
                        </label>
                        <input type="file" id="employee-photo-input" multiple accept="image/*"
                               class="form-control" style="height: auto; padding: 6px 12px;">
                        <p class="help-box small text-muted">
                            ${__('Select multiple photos. File names should start with the employee code (first 9 characters). Example: TIQN-0003-Nguyen Van A.jpg')}
                        </p>
                    </div>
                `
            },
            {
                fieldname: 'upload_status',
                fieldtype: 'HTML',
                options: '<div id="upload-status" style="margin-top: 8px; min-height: 24px;"></div>'
            }
        ],
        primary_action_label: __('Process Photos'),
        primary_action(values) {
            if (!selected_files || selected_files.length === 0) {
                frappe.msgprint({
                    title: __('No Files'),
                    message: __('Please select at least one photo file.'),
                    indicator: 'orange'
                });
                return;
            }

            d.hide();
            process_employee_photos();
        }
    });

    d.show();

    // Attach event immediately after show() — no setTimeout needed
    const status_div = d.$wrapper.find('#upload-status');
    d.$wrapper.find('#employee-photo-input').on('change', function (e) {
        selected_files = e.target.files;
        const count = selected_files ? selected_files.length : 0;
        if (count > 0) {
            status_div.html(
                `<span class="indicator-pill blue">${__('Selected {0} file(s). Click "Process Photos" to continue.', [count])}</span>`
            );
        } else {
            status_div.html('');
        }
    });

    async function process_employee_photos() {
        const files = Array.from(selected_files);
        const total = files.length;

        frappe.show_alert({
            message: __('Processing {0} photo(s)...', [total]),
            indicator: 'blue'
        });

        let results = {
            success: [],
            not_found: [],
            errors: [],
            duplicates: []
        };

        let update_completed = 0;
        let results_shown = false;
        const processed_codes = new Set();

        for (const file of files) {
            const fileName = file.name;
            const employeeCode = fileName.substring(0, 9).toUpperCase();

            if (processed_codes.has(employeeCode)) {
                results.duplicates.push({ file: fileName, code: employeeCode });
                update_completed++;
                show_results_if_complete();
                continue;
            }

            processed_codes.add(employeeCode);

            // Find employee by code prefix
            await new Promise(resolve => {
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Employee',
                        filters: [['name', 'like', employeeCode + '%']],
                        fields: ['name', 'employee_name'],
                        limit: 1
                    },
                    callback: async function (r) {
                        if (r.message && r.message.length > 0) {
                            const employee = r.message[0];
                            let image_data;
                            try {
                                image_data = await file_to_base64(file);
                            } catch (err) {
                                results.errors.push({
                                    file: fileName,
                                    error: __('Failed to read file')
                                });
                                update_completed++;
                                show_results_if_complete();
                                resolve();
                                return;
                            }

                            frappe.call({
                                method: 'customize_erpnext.api.employee.employee_utils.process_employee_photo',
                                args: {
                                    employee_id: employee.name,
                                    employee_name: employee.employee_name,
                                    image_data: image_data,
                                    remove_bg: 0
                                },
                                freeze: true,
                                freeze_message: __('Processing photos...'),
                                callback: function (update_r) {
                                    if (!update_r.exc && update_r.message && update_r.message.status === 'success') {
                                        results.success.push({
                                            employee: employee.name,
                                            employee_name: employee.employee_name,
                                            file: fileName,
                                            file_url: update_r.message.file_url
                                        });
                                    } else {
                                        results.errors.push({
                                            file: fileName,
                                            error: update_r.message?.message || __('Update failed')
                                        });
                                    }
                                    update_completed++;
                                    show_results_if_complete();
                                    resolve();
                                },
                                error: function () {
                                    results.errors.push({
                                        file: fileName,
                                        error: __('Server error')
                                    });
                                    update_completed++;
                                    show_results_if_complete();
                                    resolve();
                                }
                            });
                        } else {
                            results.not_found.push({ file: fileName, code: employeeCode });
                            update_completed++;
                            show_results_if_complete();
                            resolve();
                        }
                    }
                });
            });
        }

        function show_results_if_complete() {
            if (results_shown) return;
            if (update_completed < total) return;
            results_shown = true;

            let results_html = '<div style="max-height:400px;overflow-y:auto">';

            if (results.success.length > 0) {
                results_html += `
                    <div class="alert alert-success">
                        ${__('Successfully Updated')}: <strong>${results.success.length}</strong>
                    </div>
                    <ul style="list-style:none;padding:0">
                        ${results.success.map(item => `
                            <li style="padding:6px 0;border-bottom:1px solid var(--border-color)">
                                <span class="indicator-pill green"></span>
                                <strong>${item.employee}</strong> — ${item.employee_name}
                                <br><small class="text-muted">${__('File')}: ${item.file}</small>
                            </li>
                        `).join('')}
                    </ul>`;
            }

            if (results.not_found.length > 0) {
                results_html += `
                    <div class="alert alert-warning" style="margin-top:12px">
                        ${__('Employee Not Found')}: <strong>${results.not_found.length}</strong>
                    </div>
                    <ul style="list-style:none;padding:0">
                        ${results.not_found.map(item => `
                            <li style="padding:6px 0;border-bottom:1px solid var(--border-color)">
                                <span class="indicator-pill orange"></span>
                                <strong>${item.code}</strong> — ${__('File')}: ${item.file}
                            </li>
                        `).join('')}
                    </ul>`;
            }

            if (results.duplicates.length > 0) {
                results_html += `
                    <div class="alert alert-secondary" style="margin-top:12px">
                        ${__('Duplicate Files Skipped')}: <strong>${results.duplicates.length}</strong>
                    </div>
                    <ul style="list-style:none;padding:0">
                        ${results.duplicates.map(item => `
                            <li style="padding:6px 0;border-bottom:1px solid var(--border-color)">
                                <span class="indicator-pill gray"></span>
                                <strong>${item.code}</strong> — ${item.file}
                                <small class="text-muted">(${__('already processed')})</small>
                            </li>
                        `).join('')}
                    </ul>`;
            }

            if (results.errors.length > 0) {
                results_html += `
                    <div class="alert alert-danger" style="margin-top:12px">
                        ${__('Errors')}: <strong>${results.errors.length}</strong>
                    </div>
                    <ul style="list-style:none;padding:0">
                        ${results.errors.map(item => `
                            <li style="padding:6px 0;border-bottom:1px solid var(--border-color)">
                                <span class="indicator-pill red"></span>
                                ${item.file} — ${item.error}
                            </li>
                        `).join('')}
                    </ul>`;
            }

            results_html += '</div>';

            const results_dialog = new frappe.ui.Dialog({
                title: __('Update Results'),
                fields: [{ fieldname: 'results', fieldtype: 'HTML', options: results_html }]
            });

            results_dialog.show();
            results_dialog.$wrapper.find('.modal-dialog').css('max-width', '700px');

            if (results.success.length > 0 && listview) {
                listview.refresh();
            }
        }
    }
}


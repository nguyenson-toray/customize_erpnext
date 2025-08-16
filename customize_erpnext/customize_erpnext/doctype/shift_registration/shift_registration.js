// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

// Approach tốt hơn: Ngăn chặn chọn trùng + Filter danh sách employee

frappe.ui.form.on('Shift Registration', {
    refresh: function (frm) {
        // Set default cho End Date = Today + 7 days
        if (!frm.doc.end_date) {
            var today = frappe.datetime.get_today();
            var defaultDate = frappe.datetime.add_days(today, 7);
            frm.set_value('end_date', defaultDate);
        }
        // Auto-populate requested_by with current user's employee
        if (frm.is_new() && !frm.doc.requested_by) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Employee',
                    fields: ['name'],
                    filters: {
                        'user_id': frappe.session.user
                    }
                },
                callback: function (r) {
                    if (r.message && r.message.length > 0) {
                        frm.set_value('requested_by', r.message[0].name);
                    }
                }
            });
        }

        // Calculate total employees
        frm.events.calculate_total_employees(frm);

        // Add custom button to remove empty rows
        frm.add_custom_button(__('Remove Empty Rows'), function () {
            frm.events.remove_empty_rows(frm);
        }, __('Actions'));
    },
    // Khi thay đổi begin_time, cập nhật tất cả rows hiện có
    begin_time: function (frm) {
        if (frm.doc.begin_time) {
            frm.doc.employees_list.forEach(function (row) {
                frappe.model.set_value(row.doctype, row.name, 'begin_time', frm.doc.begin_time);
            });
            frm.refresh_field('employees_list');
        }
    },

    // Khi thay đổi end_time, cập nhật tất cả rows hiện có  
    end_time: function (frm) {
        if (frm.doc.end_time) {
            frm.doc.employees_list.forEach(function (row) {
                frappe.model.set_value(row.doctype, row.name, 'end_time', frm.doc.end_time);
            });
            frm.refresh_field('employees_list');
        }
    },

    // Function để tính toán total employees
    calculate_total_employees: function (frm) {
        var total = 0;
        if (frm.doc.employees_list) {
            frm.doc.employees_list.forEach(function (row) {
                if (row.employee) {
                    total++;
                }
            });
        }
        frm.set_value('total_employees', total);
    },

    // Tính total employees khi load form
    refresh: function (frm) {
        frm.events.calculate_total_employees(frm);

        // Add custom button to remove empty rows
        frm.add_custom_button(__('Remove Empty Rows'), function () {
            frm.events.remove_empty_rows(frm);
        }, __('Actions'));
    },

    // Function to remove rows with empty employee or date
    remove_empty_rows: function (frm) {
        var rows_to_remove = [];

        if (frm.doc.employees_list) {
            frm.doc.employees_list.forEach(function (row, index) {
                if (!row.employee || !row.begin_date || !row.end_date) {
                    rows_to_remove.push(row.name);
                }
            });
        }

        // Remove rows in reverse order to avoid index issues
        rows_to_remove.reverse().forEach(function (row_name) {
            var row = frm.doc.employees_list.find(r => r.name === row_name);
            if (row) {
                frm.get_field('employees_list').grid.grid_rows_by_docname[row_name].remove();
            }
        });

        if (rows_to_remove.length > 0) {
            frm.refresh_field('employees_list');
            frm.events.calculate_total_employees(frm);
            frappe.show_alert({
                message: __('Removed {0} empty rows', [rows_to_remove.length]),
                indicator: 'blue'
            });
        } else {
            frappe.show_alert({
                message: __('No empty rows found'),
                indicator: 'orange'
            });
        }
    }
});

frappe.ui.form.on('Shift Registration Detail', {
    // Khi thêm row mới, tự động điền thông tin từ parent
    employees_list_add: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];

        // Set begin_time từ parent
        if (frm.doc.begin_time) {
            frappe.model.set_value(cdt, cdn, 'begin_time', frm.doc.begin_time);
        }

        // Set end_time từ parent  
        if (frm.doc.end_time) {
            frappe.model.set_value(cdt, cdn, 'end_time', frm.doc.end_time);
        }

        // Set begin_date và end_date từ parent
        if (frm.doc.begin_date) {
            frappe.model.set_value(cdt, cdn, 'begin_date', frm.doc.begin_date);
        }

        if (frm.doc.end_date) {
            frappe.model.set_value(cdt, cdn, 'end_date', frm.doc.end_date);
        }

        frm.refresh_field('employees_list');
        // Không cần tính total vì chưa có employee
    },

    // Khi xóa row, cập nhật total employees
    employees_list_remove: function (frm, cdt, cdn) {
        setTimeout(function () {
            frm.events.calculate_total_employees(frm);
        }, 100);
    },

    // Setup filter cho employee field
    employee: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];

        if (row.employee) {
            // Kiểm tra trùng lặp
            var selected_employees = [];
            frm.doc.employees_list.forEach(function (emp_row) {
                if (emp_row.name !== cdn && emp_row.employee) {
                    selected_employees.push(emp_row.employee);
                }
            });

            // Nếu employee đã được chọn
            if (selected_employees.includes(row.employee)) {
                frappe.msgprint({
                    title: __('Validation Error'),
                    message: __('Employee {0} has been selected multiple times in the list. Please select each employee only once.', [row.employee]),
                    indicator: 'red'
                });

                // Function để reset toàn bộ row
                setTimeout(function () {
                    // Clear tất cả thông tin trong row
                    var fields_to_clear = ['employee', 'full_name', 'group', 'department', 'designation'];

                    fields_to_clear.forEach(function (field) {
                        if (row.hasOwnProperty(field)) {
                            frappe.model.set_value(cdt, cdn, field, '');
                        }
                    });

                    // Set lại time từ parent
                    if (frm.doc.begin_time) {
                        frappe.model.set_value(cdt, cdn, 'begin_time', frm.doc.begin_time);
                    }
                    if (frm.doc.end_time) {
                        frappe.model.set_value(cdt, cdn, 'end_time', frm.doc.end_time);
                    }
                    if (frm.doc.begin_date) {
                        frappe.model.set_value(cdt, cdn, 'begin_date', frm.doc.begin_date);
                    }
                    if (frm.doc.end_date) {
                        frappe.model.set_value(cdt, cdn, 'end_date', frm.doc.end_date);
                    }

                    frm.refresh_field('employees_list');

                    // Tính lại total employees sau khi clear duplicate
                    frm.events.calculate_total_employees(frm);
                }, 100);
                return;
            }

            // Set time cho dòng hợp lệ
            if (!row.begin_time && frm.doc.begin_time) {
                frappe.model.set_value(cdt, cdn, 'begin_time', frm.doc.begin_time);
            }
            if (!row.end_time && frm.doc.end_time) {
                frappe.model.set_value(cdt, cdn, 'end_time', frm.doc.end_time);
            }

            // Tính toán total employees khi có employee được chọn
            setTimeout(function () {
                frm.events.calculate_total_employees(frm);
            }, 200);
        } else if (!row.employee) {
            // Nếu employee bị clear, cũng cần tính lại total
            setTimeout(function () {
                frm.events.calculate_total_employees(frm);
            }, 200);
        }
    },

    // Validation trước khi save form
    validate: function (frm) {
        // Always validate required fields first
        if (!validate_required_fields(frm)) {
            return false;
        }

        // Validate shift values
        if (!validate_shift_values(frm)) {
            return false;
        }

        // Synchronous validation for immediate feedback
        validate_duplicate_entries(frm);

        // Check conflicts with submitted records (asynchronous)
        check_conflicts_with_submitted_records(frm);

        calculate_total_employees(frm);
    }
});

// Optional: Thêm filter để ẩn employees đã được chọn
frappe.ui.form.on('Shift Registration Detail', {
    form_render: function (frm, cdt, cdn) {
        // Get employees đã được chọn
        var selected_employees = [];
        if (frm.doc.employees_list) {
            frm.doc.employees_list.forEach(function (row) {
                if (row.employee && row.name !== cdn) {
                    selected_employees.push(row.employee);
                }
            });
        }

        // Set filter cho employee field
        frm.set_query('employee', 'employees_list', function () {
            return {
                filters: {
                    'name': ['not in', selected_employees]
                }
            };
        });
    }
});

// Validation functions
function validate_required_fields(frm) {
    let hasErrors = false;

    for (let d of frm.doc.employees_list || []) {
        let missing_fields = [];
        if (!d.employee) missing_fields.push(__("Employee"));
        if (!d.begin_date) missing_fields.push(__("Begin Date"));
        if (!d.end_date) missing_fields.push(__("End Date"));
        if (!d.begin_time) missing_fields.push(__("Begin Time"));
        if (!d.end_time) missing_fields.push(__("End Time"));

        if (missing_fields.length > 0) {
            frappe.msgprint(__(`Row #{0}: {1} are required.`, [d.idx, missing_fields.join(', ')]));
            hasErrors = true;
        }
    }

    if (hasErrors) {
        frappe.validated = false;
        return false;
    }
    return true;
}

function validate_duplicate_entries(frm) {
    const entries = [];

    for (let d of frm.doc.employees_list || []) {
        // Skip validation if required fields are missing - handled by validate_required_fields
        if (!d.employee || !d.begin_date || !d.end_date || !d.begin_time || !d.end_time) {
            return;
        }

        entries.push({
            idx: d.idx,
            employee: d.employee,
            employee_name: d.employee_name,
            begin_date: d.begin_date,
            end_date: d.end_date,
            begin_time: d.begin_time,
            end_time: d.end_time
        });
    }

    // Check for duplicates and overlaps
    for (let i = 0; i < entries.length; i++) {
        for (let j = i + 1; j < entries.length; j++) {
            const entry1 = entries[i];
            const entry2 = entries[j];

            // Same employee
            if (entry1.employee === entry2.employee) {
                // Check for date range overlap and time overlap
                if (dates_overlap(entry1.begin_date, entry1.end_date, entry2.begin_date, entry2.end_date)) {
                    if (times_overlap(entry1.begin_time, entry1.end_time, entry2.begin_time, entry2.end_time)) {
                        frappe.validated = false;
                        frappe.msgprint(__(`Row #{0} and Row #{1}: Overlapping shift entries for employee {2}. Entry 1: {3} to {4} ({5}-{6}), Entry 2: {7} to {8} ({9}-{10})`,
                            [entry1.idx, entry2.idx, entry1.employee_name,
                            entry1.begin_date, entry1.end_date, entry1.begin_time, entry1.end_time,
                            entry2.begin_date, entry2.end_date, entry2.begin_time, entry2.end_time]));
                        return;
                    }
                }
            }
        }
    }
}

function check_conflicts_with_submitted_records(frm) {
    if (!frm.doc.employees_list || frm.doc.employees_list.length === 0) {
        return;
    }

    // Prepare data for server-side validation
    const entries_to_check = [];
    for (let d of frm.doc.employees_list) {
        if (d.employee && d.begin_date && d.end_date && d.begin_time && d.end_time) {
            entries_to_check.push({
                idx: d.idx,
                employee: d.employee,
                employee_name: d.employee_name,
                begin_date: d.begin_date,
                end_date: d.end_date,
                begin_time: d.begin_time,
                end_time: d.end_time
            });
        }
    }

    if (entries_to_check.length === 0) {
        return;
    }

    // Call server method to check conflicts
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.shift_registration.shift_registration.check_shift_conflicts',
        args: {
            entries: entries_to_check,
            current_doc_name: frm.doc.name || 'new'
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                // Found conflicts
                frappe.validated = false;

                // Show all conflicts
                for (let conflict of r.message) {
                    frappe.msgprint(__(`Row #{0}: Overlapping shift entry for employee {1} from {2} to {3} ({4}-{5}). Existing: {6} to {7} ({8}-{9}) in <a href="/app/shift-registration/{10}" target="_blank">{10}</a>`,
                        [conflict.idx, conflict.employee_name,
                        conflict.begin_date, conflict.end_date, conflict.begin_time, conflict.end_time,
                        conflict.existing_begin_date, conflict.existing_end_date, conflict.existing_begin_time, conflict.existing_end_time,
                        conflict.existing_doc]));
                }
            }
        }
    });
}

function calculate_total_employees(frm) {
    if (!frm.doc.employees_list || frm.doc.employees_list.length === 0) {
        frm.set_value('total_employees', 0);
        return;
    }

    const distinct_employees = new Set();
    frm.doc.employees_list.forEach(d => {
        if (d.employee) {
            distinct_employees.add(d.employee);
        }
    });

    frm.set_value('total_employees', distinct_employees.size);
}

// Helper function to check if two date ranges overlap
function dates_overlap(start1, end1, start2, end2) {
    try {
        const date1_start = frappe.datetime.str_to_obj(start1);
        const date1_end = frappe.datetime.str_to_obj(end1);
        const date2_start = frappe.datetime.str_to_obj(start2);
        const date2_end = frappe.datetime.str_to_obj(end2);

        // Check for overlap: start1 <= end2 && start2 <= end1
        return date1_start <= date2_end && date2_start <= date1_end;
    } catch (error) {
        return false;
    }
}

// Helper function to check if two time ranges overlap
function times_overlap(from1, to1, from2, to2) {
    // Convert time strings to Date objects for comparison
    const time1Start = new Date(`2000-01-01T${from1}`);
    const time1End = new Date(`2000-01-01T${to1}`);
    const time2Start = new Date(`2000-01-01T${from2}`);
    const time2End = new Date(`2000-01-01T${to2}`);

    // Check for overlap: start1 < end2 && start2 < end1
    // Adjacent periods (where one ends exactly when another begins) are NOT overlapping
    const condition1 = time1Start < time2End;
    const condition2 = time2Start < time1End;
    const overlap = condition1 && condition2;

    return overlap;
}

// Function to validate shift values - only allow "Shift 1" and "Shift 2"
function validate_shift_values(frm) {
    let hasErrors = false;
    const allowedShifts = [__('Shift 1'), __('Shift 2')];

    for (let d of frm.doc.employees_list || []) {
        // Skip validation if employee is empty (will be handled by other validation)
        if (!d.employee) {
            continue;
        }
        
        if (d.shift && !allowedShifts.includes(d.shift)) {
            frappe.msgprint(__('Row {0}: Only "{1}" and "{2}" are allowed. Found: {3}', [d.idx, __('Shift 1'), __('Shift 2'), d.shift]));
            hasErrors = true;
        }
    }

    if (hasErrors) {
        frappe.validated = false;
        return false;
    }
    return true;
}
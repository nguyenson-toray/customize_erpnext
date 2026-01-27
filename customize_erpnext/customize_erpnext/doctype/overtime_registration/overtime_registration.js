// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Overtime Registration", {
    refresh(frm) {
        // Hide Print button if document is not submitted
        if (frm.doc.docstatus != 1) {
            console.log("Hiding Print button for non-submitted document");
            $("button[data-original-title=Print]").hide();
            frm.page.menu.find('[data-label="Print"]').parent().parent().remove();
        }
        // Add custom styling for the form
        frm.page.add_inner_button(__('Get Employees'), function () {
            show_employee_selection_dialog(frm);
        }, __('Actions'));

        // Add button to remove empty rows
        frm.page.add_inner_button(__('Remove Empty Rows'), function () {
            remove_empty_overtime_rows(frm);
        }, __('Actions'));

        // Reset validation flags when form refreshes
        frm.maternity_check_done = false;
        frm.ot_continuity_validated = false;

        // Auto-populate requested_by with current user's employee
        if (frm.is_new() && !frm.doc.requested_by) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Employee',
                    fields: ['name', 'employee_name'],
                    filters: {
                        'user_id': frappe.session.user
                    }
                },
                callback: function (r) {
                    if (r.message && r.message.length > 0) {
                        const employee = r.message[0];
                        frm.set_value('requested_by', employee.name);
                        // Auto-fill approver based on requested_by
                        set_approver_based_on_requested_by(frm, employee.name);
                    }
                }
            });
        }

        // Set query filter for approver field (same as Leave Application)
        frm.set_query("approver", function () {
            return {
                query: "hrms.hr.doctype.department_approver.department_approver.get_approvers",
                filters: {
                    employee: frm.doc.requested_by,
                    doctype: frm.doc.doctype,
                },
            };
        });


    },
    get_employees_button(frm) {
        show_employee_selection_dialog(frm);
    },

    before_save(frm) {
        // Check for employees with maternity benefits needing time adjustment
        if (!frm.maternity_check_done) {
            let dialog_shown = check_maternity_benefit_adjustment(frm);
            if (dialog_shown) {
                return; // Stop here, dialog will handle save after user responds
            }
        }
    },

    validate(frm) {
        // Auto-remove empty rows before validation
        remove_empty_overtime_rows(frm, true);

        // Validate required fields
        if (!validate_required_fields(frm)) {
            return false;
        }

        // Validate time order: begin_time < end_time
        if (!validate_time_order(frm)) {
            return false;
        }

        // Validate duplicate rows within form
        if (!validate_duplicate_rows(frm)) {
            return false;
        }

        // Validate single post-shift entry per employee per day
        if (!validate_single_post_shift_entry(frm)) {
            return false;
        }

        // Calculate totals
        calculate_totals_and_apply_reason(frm);

        // Update registered groups summary
        update_registered_groups(frm);
    },

    requested_by(frm) {
        // Auto-fill approver when requested_by field changes
        if (frm.doc.requested_by) {
            set_approver_based_on_requested_by(frm, frm.doc.requested_by);
        } else {
            // Clear approver if requested_by is cleared
            frm.set_value('approver', '');
            frm.set_value('approver_full_name', '');
        }
    },

    approver(frm) {
        // Set approver full name when approver changes (get employee name, not user name)
        if (frm.doc.approver) {
            get_employee_name_from_user(frm, frm.doc.approver);
        } else {
            frm.set_value('approver_full_name', '');
        }
    }
});

// Global variables to store dialog state
let currentDialog = null;
let selectedEmployees = new Map(); // Store all selected employees across sessions
let currentGroupEmployees = new Map(); // Store current group's available employees

// Function to get current user's filter value based on filter_employee_by field
function get_user_filter_value(frm, callback) {
    const filterBy = frm.doc.filter_employee_by;

    if (!filterBy) {
        callback(null, null);
        return;
    }

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Employee',
            fields: ['department', 'custom_section', 'custom_group'],
            filters: {
                'user_id': frappe.session.user
            },
            limit_page_length: 1
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                const employee = r.message[0];
                const filterValue = employee[filterBy];
                callback(filterBy, filterValue);
            } else {
                callback(filterBy, null);
            }
        },
        error: function () {
            callback(filterBy, null);
        }
    });
}

function show_employee_selection_dialog(frm) {
    // Close any existing dialog first and reset state
    if (currentDialog) {
        currentDialog.hide();
        currentDialog = null;
    }

    // Generate week options
    const weekOptions = get_week_options();

    currentDialog = new frappe.ui.Dialog({
        title: __('Select Employees for Overtime Registration'),
        size: 'extra-large',
        fields: [
            {
                fieldtype: 'Section Break',
                label: 'Selection Parameters'
            },
            {
                fieldtype: 'Column Break'
            },
            {
                fieldtype: 'Link',
                fieldname: 'selected_group',
                label: 'Group',
                options: 'Group',
                reqd: 1,
                get_query: function () {
                    if (frm.doc.filter_employee_by === 'custom_group' && frm.doc.request_by_group) {
                        return {
                            filters: {
                                name: frm.doc.request_by_group
                            }
                        };
                    }
                    return {};
                }
            },
            {
                fieldtype: 'Select',
                fieldname: 'selected_week',
                label: 'Week',
                options: weekOptions,
                default: '0',
                onchange: function () {
                    const weekValue = currentDialog.get_value('selected_week');
                    update_day_labels_for_week(parseInt(weekValue) || 0);
                }
            },
            {
                fieldtype: 'Column Break'
            },
            {
                fieldtype: 'Time',
                fieldname: 'time_begin',
                label: 'Time Begin',
                default: '17:00:00'
            },
            {
                fieldtype: 'Time',
                fieldname: 'time_end',
                label: 'Time End',
                default: '19:00:00'
            },
            {
                fieldtype: 'Column Break'
            },
            {
                fieldtype: 'Small Text',
                fieldname: 'reason',
                label: 'Reason',
                reqd: 1
            },
            {
                fieldtype: 'Section Break',
                label: 'Day Selection'
            },
            {
                fieldtype: 'HTML',
                fieldname: 'day_selection_html'
            },
            {
                fieldtype: 'Section Break',
                label: 'Employee Selection'
            },
            {
                fieldtype: 'Small Text',
                fieldname: 'selected_employees_display',
                label: 'Selected Employees',
                read_only: 1,
                default: 'No employees selected'
            },
            {
                fieldtype: 'Button',
                fieldname: 'select_employees_btn',
                label: 'Select Employees',
                click: function () {
                    open_employee_selection_dialog(frm);
                }
            },
            {
                fieldtype: 'Button',
                fieldname: 'clear_employees_btn',
                label: 'Clear All Selected',
                click: function () {
                    clear_selected_employees();
                }
            }
        ],
        primary_action_label: __('OK'),
        primary_action: function () {
            save_overtime_registration_native(frm);
        }
    });

    // Store frm reference in dialog for access to lock_group field
    currentDialog.frm = frm;

    currentDialog.show();

    // Initialize dialog with native fields only
    setTimeout(() => {
        initialize_simple_dialog();
    }, 300);
}

function get_week_options() {
    const today = new Date();
    const currentDay = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - currentDay + 1);

    let options = [];

    // Current week and next 2 weeks (3 total)
    for (let i = 0; i < 3; i++) {
        const weekMonday = new Date(monday);
        weekMonday.setDate(monday.getDate() + (i * 7));

        const weekSunday = new Date(weekMonday);
        weekSunday.setDate(weekMonday.getDate() + 6);

        const mondayStr = weekMonday.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' });
        const sundayStr = weekSunday.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' });

        let weekLabel = '';
        if (i === 0) {
            weekLabel = __('Current Week') + ` (${mondayStr} - ${sundayStr})`;
        } else if (i === 1) {
            weekLabel = __('Week +1') + ` (${mondayStr} - ${sundayStr})`;
        } else {
            weekLabel = __('Week') + ` +${i} (${mondayStr} - ${sundayStr})`;
        }

        // Use simple value:label format for Frappe select
        options.push(`${i}:${weekLabel}`);
    }

    return options.join('\n');
}

function initialize_simple_dialog() {
    // Set current week as default
    currentDialog.set_value('selected_week', '0');

    // Update day labels for current week
    update_day_labels_for_week(0);

    // Update selected employees display
    update_selected_employees_display();
}

function update_day_labels_for_week(weekOffset = 0) {
    const today = new Date();
    const currentDay = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - currentDay + 1 + (weekOffset * 7));

    const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    const dayNames = [__('Monday'), __('Tuesday'), __('Wednesday'), __('Thursday'), __('Friday'), __('Saturday')];

    let day_selection_html = '<div class="row">';

    // "Select All" checkbox
    day_selection_html += `
        <div class="col-md-2">
            <div class="form-group">
                <div class="checkbox">
                    <label>
                        <input type="checkbox" class="select-all-days"> ${__('Select All')}
                    </label>
                </div>
            </div>
        </div>
    `;

    days.forEach((dayField, index) => {
        const date = new Date(monday);
        date.setDate(monday.getDate() + index);
        const dateStr = date.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' });
        const newLabel = `${dayNames[index]} ${dateStr}`;

        day_selection_html += `
            <div class="col-md-2">
                <div class="form-group">
                    <div class="checkbox">
                        <label>
                            <input type="checkbox" class="day-checkbox" data-day="${dayField}"> ${newLabel}
                        </label>
                    </div>
                </div>
            </div>
        `;
    });

    day_selection_html += '</div>';

    currentDialog.get_field('day_selection_html').$wrapper.html(day_selection_html);

    // Add event listeners
    const selectAllCheckbox = currentDialog.get_field('day_selection_html').$wrapper.find('.select-all-days');
    const dayCheckboxes = currentDialog.get_field('day_selection_html').$wrapper.find('.day-checkbox');

    selectAllCheckbox.on('change', function () {
        dayCheckboxes.prop('checked', $(this).prop('checked'));
    });

    dayCheckboxes.on('change', function () {
        if (!$(this).prop('checked')) {
            selectAllCheckbox.prop('checked', false);
        }
    });
}

function open_employee_selection_dialog(frm) {
    const groupValue = currentDialog.get_value('selected_group');
    if (!groupValue) {
        frappe.show_alert({
            message: __('Please select a group first'),
            indicator: 'orange'
        });
        return;
    }

    // Check if filtering is enabled
    if (frm.doc.filter_employee_by) {
        get_user_filter_value(frm, function (filterBy, filterValue) {
            if (!filterValue) {
                frappe.show_alert({
                    message: __('Current user does not have a valid ' + filterBy + ' value'),
                    indicator: 'red'
                });
                return;
            }

            // For custom_group filtering, check if group matches
            if (filterBy === 'custom_group' && groupValue !== filterValue) {
                frappe.show_alert({
                    message: __('You can only select employees from your own group: ') + filterValue,
                    indicator: 'red'
                });
                return;
            }

            // Proceed with dialog creation
            create_employee_list_dialog(groupValue);
        });
    } else {
        // No filtering, proceed normally
        create_employee_list_dialog(groupValue);
    }
}

function create_employee_list_dialog(groupValue) {
    // Create a new dialog every time to ensure correct z-index
    const employeeListDialog = new frappe.ui.Dialog({
        title: __("Select Employees from Group: ") + groupValue,
        size: 'large',
        fields: [
            {
                fieldtype: 'Data',
                fieldname: 'employee_search',
                label: 'Search Employees',
                placeholder: __('Type employee name or ID to filter...'),
                onchange: function () {
                    filter_employees_in_dialog(this.value, employeeListDialog);
                }
            },
            {
                fieldtype: 'Button',
                fieldname: 'clear_search',
                label: 'Clear Search',
                click: function () {
                    employeeListDialog.set_value('employee_search', '');
                    filter_employees_in_dialog('', employeeListDialog);
                }
            },
            {
                fieldtype: 'HTML',
                fieldname: 'employee_list',
                options: '<div class="text-muted" style="padding: 20px;">Loading...</div>'
            }
        ],
        primary_action_label: __('Add Selected'),
        primary_action: function () {
            add_selected_employees_from_dialog(employeeListDialog); // Pass dialog instance
            employeeListDialog.hide();
        }
    });

    employeeListDialog.show();

    // Add real-time search functionality
    setTimeout(() => {
        const searchInput = employeeListDialog.get_field('employee_search').$input;
        if (searchInput) {
            searchInput.on('input', function () {
                filter_employees_in_dialog(this.value, employeeListDialog);
            });
        }
    }, 100);

    // Load employees for the selected group
    load_employees_for_selection(groupValue, employeeListDialog);
}

// Global variable to store original employee list for filtering
let originalEmployeeList = [];

function filter_employees_in_dialog(searchTerm, dialog) {
    if (!searchTerm || searchTerm.trim() === '') {
        // Show all employees if search is empty
        render_employee_list(originalEmployeeList, dialog);
        return;
    }

    const filteredEmployees = originalEmployeeList.filter(emp => {
        const searchLower = searchTerm.toLowerCase().trim();
        const empName = (emp.employee_name || emp.name || '').toLowerCase();
        const empId = (emp.name || '').toLowerCase();

        return empName.includes(searchLower) || empId.includes(searchLower);
    });

    render_employee_list(filteredEmployees, dialog);
}

function load_employees_for_selection(groupName, dialog) {
    const field_wrapper = dialog.get_field('employee_list').$wrapper;

    if (!field_wrapper) {
        return;
    }

    // Set loading state
    field_wrapper.html('<div class="text-muted" style="padding: 20px;">Loading employees...</div>');

    const frm = currentDialog && currentDialog.frm;
    const filterBy = frm && frm.doc.filter_employee_by;

    if (filterBy) {
        get_user_filter_value(frm, function (filterBy, filterValue) {
            if (!filterValue) {
                field_wrapper.html('<p class="text-danger" style="padding: 20px;"><strong>Error:</strong><br>Current user does not have a valid ' + filterBy + ' value.</p>');
                originalEmployeeList = [];
                return;
            }

            // Build filters for employee query
            const employeeFilters = {
                'custom_group': groupName,
                'status': 'Active'
            };

            // Add filter based on filter_employee_by
            employeeFilters[filterBy] = filterValue;

            load_employees_for_selection_with_filters(employeeFilters, dialog);
        });
    } else {
        // No filtering, load all employees from group
        const employeeFilters = {
            'custom_group': groupName,
            'status': 'Active'
        };
        load_employees_for_selection_with_filters(employeeFilters, dialog);
    }
}

function load_employees_for_selection_with_filters(filters, dialog) {
    const field_wrapper = dialog.get_field('employee_list').$wrapper;

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Employee',
            fields: ['name', 'employee_name', 'custom_group', 'department', 'custom_section', 'status'],
            filters: filters,
            order_by: 'name',
            limit_page_length: 0  // Get all records
        },
        callback: function (r) {
            if (!r.message || r.message.length === 0) {
                field_wrapper.html('<p class="text-muted" style="padding: 20px;">No active employees found in this group.</p>');
                originalEmployeeList = [];
                return;
            }

            // Store original list for filtering
            originalEmployeeList = r.message;

            // Reset search field when loading new group
            dialog.set_value('employee_search', '');

            // Render the employee list
            render_employee_list(originalEmployeeList, dialog);
        },
        error: function (r) {
            field_wrapper.html('<p class="text-danger" style="padding: 20px;"><strong>Error loading employees:</strong><br>' + (r.message || 'Unknown error') + '</p>');
            originalEmployeeList = [];
        }
    });
}

function render_employee_list(employees, dialog) {
    const field_wrapper = dialog.get_field('employee_list').$wrapper;

    if (!field_wrapper) {
        return;
    }

    if (employees.length === 0) {
        field_wrapper.html('<p class="text-muted" style="padding: 20px;">No employees match your search criteria.</p>');
        return;
    }

    // Get current search term for highlighting
    const searchTerm = dialog.get_value('employee_search') || '';

    let html = '<div style="max-height: 400px; overflow-y: auto; padding: 10px; border: 1px solid #ddd;">';
    html += `<div style="margin-bottom: 15px; padding: 10px; background-color: #f8f9fa; border-radius: 4px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <label style="font-weight: bold; margin: 0;"><input type="checkbox" id="select_all_employees" style="margin-right: 8px;"> ${__('Select All Employees')}</label>
                    <small class="text-muted">${__('Showing {0} employee(s)', [employees.length])}</small>
                </div>
             </div>`;

    employees.forEach((emp) => {
        const isSelected = selectedEmployees.has(emp.name);
        const checkedAttr = isSelected ? 'checked' : '';
        const disabledAttr = isSelected ? `disabled title="${__('Already selected')}"` : '';

        // Highlight matching text
        let displayName = emp.employee_name || emp.name;
        let displayId = emp.name;

        if (searchTerm.trim()) {
            const regex = new RegExp(`(${searchTerm.trim()})`, 'gi');
            displayName = displayName.replace(regex, '<mark style="background-color: yellow; padding: 1px 2px;">$1</mark>');
            displayId = displayId.replace(regex, '<mark style="background-color: yellow; padding: 1px 2px;">$1</mark>');
        }

        // Build additional info based on available fields
        let additionalInfo = [];
        if (emp.custom_group) additionalInfo.push(`Group: ${emp.custom_group}`);
        if (emp.custom_section) additionalInfo.push(`Section: ${emp.custom_section}`);
        if (emp.department) additionalInfo.push(`Dept: ${emp.department}`);

        const infoText = additionalInfo.length > 0 ? `(${additionalInfo.join(', ')})` : '';

        html += `
            <div style="margin-bottom: 10px; padding: 12px; border: 1px solid #ddd; border-radius: 6px; background-color: ${isSelected ? '#f0f8ff' : 'white'};
">
                <label style="margin: 0; cursor: ${isSelected ? 'not-allowed' : 'pointer'}; display: block;">
                    <input type="checkbox" class="employee-checkbox" value="${emp.name}" 
                           data-name="${emp.employee_name || emp.name}" 
                           data-group="${emp.custom_group}" ${checkedAttr} ${disabledAttr}
                           style="margin-right: 8px;">
                    <strong style="color: #333;">${displayId}</strong> - ${displayName} <small class="text-muted">${infoText}</small>
                    ${isSelected ? `<br><small class="text-info"><strong>(${__('Already selected')})</strong></small>` : ''}
                </label>
            </div>
        `;
    });

    html += '</div>';

    field_wrapper.html(html);

    // Set up select all functionality
    const selectAllBtn = field_wrapper.find('#select_all_employees');

    if (selectAllBtn.length) {
        selectAllBtn.on('change', function () {
            field_wrapper.find('.employee-checkbox:not([disabled])').prop('checked', this.checked);
        });
    }
}

function add_selected_employees_from_dialog(employeeListDialog) { // Accept dialog instance
    if (!employeeListDialog) return;

    const checkedBoxes = $(employeeListDialog.body).find('.employee-checkbox:checked:not([disabled])');
    let addedCount = 0;

    checkedBoxes.each(function () {
        const checkbox = $(this);
        const empId = checkbox.val();
        const empName = checkbox.data('name');
        const empGroup = checkbox.data('group');

        if (!selectedEmployees.has(empId)) {
            selectedEmployees.set(empId, {
                name: empId,
                employee_name: empName,
                custom_group: empGroup,
                status: 'Active'
            });
            addedCount++;
        }
    });

    if (addedCount > 0) {
        update_selected_employees_display();
        frappe.show_alert({
            message: __('Added {0} employee(s) to selection', [addedCount]),
            indicator: 'green'
        });
    } else {
        frappe.show_alert({
            message: __('No new employees selected'),
            indicator: 'orange'
        });
    }
}

function clear_selected_employees() {
    if (selectedEmployees.size === 0) {
        frappe.show_alert({
            message: __('No employees selected to clear'),
            indicator: 'orange'
        });
        return;
    }

    frappe.confirm(__('Are you sure you want to clear all selected employees?'), () => {
        selectedEmployees.clear();
        update_selected_employees_display();
        frappe.show_alert({
            message: __('All selected employees cleared'),
            indicator: 'blue'
        });
    });
}

function update_selected_employees_display() {
    if (!currentDialog) return;

    let displayText = '';
    if (selectedEmployees.size === 0) {
        displayText = 'No employees selected';
    } else {
        const employeeList = Array.from(selectedEmployees.values())
            .map(emp => `${emp.name} (${emp.employee_name || emp.name})`)
            .join(', ');
        displayText = `${selectedEmployees.size} employee(s) selected: ${employeeList}`;
    }

    currentDialog.set_value('selected_employees_display', displayText);
}

function save_overtime_registration_native(frm) {
    // Validation
    if (selectedEmployees.size === 0) {
        frappe.show_alert({
            message: __('Please select at least one employee'),
            indicator: 'red'
        });
        return;
    }

    const selectedDays = [];
    currentDialog.get_field('day_selection_html').$wrapper.find('.day-checkbox:checked').each(function () {
        selectedDays.push($(this).data('day'));
    });

    if (selectedDays.length === 0) {
        frappe.show_alert({
            message: __('Please select at least one day'),
            indicator: 'red'
        });
        return;
    }

    const reason = currentDialog.get_value('reason');
    if (!reason) {
        frappe.show_alert({
            message: __('Please enter a reason for overtime'),
            indicator: 'red'
        });
        return;
    }

    const begin_time = currentDialog.get_value('time_begin');
    const end_time = currentDialog.get_value('time_end');

    // Clear existing rows
    // frm.clear_table('ot_employees');

    // Add selected employees to child table
    selectedEmployees.forEach(employee => {
        selectedDays.forEach(day => {
            const child = frm.add_child('ot_employees');
            child.employee = employee.name;
            child.employee_name = employee.employee_name || employee.name;

            const weekOffset = parseInt(currentDialog.get_value('selected_week')) || 0;
            const today = new Date();
            const currentDay = today.getDay();
            const monday = new Date(today);
            monday.setDate(today.getDate() - currentDay + 1 + (weekOffset * 7));

            const dayIndex = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'].indexOf(day);
            const date = new Date(monday);
            date.setDate(monday.getDate() + dayIndex);
            child.date = date.toISOString().split('T')[0];

            child.begin_time = begin_time;
            child.end_time = end_time;
            child.reason = reason;
        });
    });

    // Update parent fields
    frm.set_value('reason_general', reason);
    frm.set_value('total_employees', selectedEmployees.size);

    // Refresh child table
    frm.refresh_field('ot_employees');

    // Close dialog
    if (currentDialog) {
        currentDialog.hide();
    }

    frappe.show_alert({
        message: __('Successfully added {0} employee(s) for {1} day(s)', [selectedEmployees.size, selectedDays.length]),
        indicator: 'green'
    });

    // Clear selected employees after successful save
    selectedEmployees.clear();
}

// Validation functions
function validate_required_fields(frm) {
    let hasErrors = false;

    for (let d of frm.doc.ot_employees || []) {
        if (!d.date || !d.begin_time || !d.end_time) {
            frappe.msgprint(__(`Row #{0}: Employee, Date, Begin Time, and End Time are required.`, [d.idx]));
            hasErrors = true;
        }
    }

    if (hasErrors) {
        frappe.validated = false;
        return false;
    }
    return true;
}

// Validate time order: begin_time < end_time
function validate_time_order(frm) {
    for (let d of frm.doc.ot_employees || []) {
        if (d.begin_time && d.end_time) {
            // Convert time strings to Date objects for proper comparison
            const time_begin = new Date(`2000-01-01T${d.begin_time}`);
            const time_end = new Date(`2000-01-01T${d.end_time}`);

            if (time_begin >= time_end) {
                console.log(`Invalid time order in row ${d.idx}: ${d.begin_time} >= ${d.end_time}`);
                frappe.msgprint(__('Row #{0}: Giờ bắt đầu ({1}) phải nhỏ hơn giờ kết thúc ({2})', [d.idx, d.begin_time, d.end_time]));
                frappe.validated = false;
                return false;
            }
        }
    }
    return true;
}

// Validate duplicate rows within form (same employee, date, time)
function validate_duplicate_rows(frm) {
    const entries = [];

    for (let d of frm.doc.ot_employees || []) {
        if (!d.employee || !d.date || !d.begin_time || !d.end_time) {
            continue;
        }

        entries.push({
            idx: d.idx,
            employee: d.employee,
            employee_name: d.employee_name,
            date: d.date,
            begin_time: d.begin_time,
            end_time: d.end_time
        });
    }

    // Check for duplicates
    for (let i = 0; i < entries.length; i++) {
        for (let j = i + 1; j < entries.length; j++) {
            const entry1 = entries[i];
            const entry2 = entries[j];

            // Same employee and date
            if (entry1.employee === entry2.employee && entry1.date === entry2.date) {
                // Check for exact match or time overlap
                if (times_overlap(entry1.begin_time, entry1.end_time, entry2.begin_time, entry2.end_time)) {
                    frappe.msgprint(__('Row {0} và {1}: Trùng lặp OT cho nhân viên {2} ngày {3}',
                        [entry1.idx, entry2.idx, entry1.employee_name, entry1.date]));
                    frappe.validated = false;
                    return false;
                }
            }
        }
    }
    return true;
}

// Validate that each employee has only one post-shift OT entry per day in this form
// Multiple entries should be combined into one continuous entry
function validate_single_post_shift_entry(frm) {
    // Group entries by employee and date
    const employee_date_entries = {};

    for (let d of frm.doc.ot_employees || []) {
        if (!d.employee || !d.date || !d.begin_time || !d.end_time) {
            continue;
        }

        const key = `${d.employee}_${d.date}`;
        if (!employee_date_entries[key]) {
            employee_date_entries[key] = [];
        }
        employee_date_entries[key].push({
            idx: d.idx,
            employee: d.employee,
            employee_name: d.employee_name,
            date: d.date,
            begin_time: d.begin_time,
            end_time: d.end_time
        });
    }

    // Check each employee-date group
    for (let key in employee_date_entries) {
        const entries = employee_date_entries[key];

        // If only one entry, no need to check
        if (entries.length <= 1) {
            continue;
        }

        // If multiple entries, they should all be continuous (handled by Python validation)
        // But we should warn that multiple entries for same employee should be combined
        const rows = entries.map(e => e.idx).join(', ');
        const employee_name = entries[0].employee_name;
        const date = entries[0].date;

        frappe.msgprint({
            title: __('Cảnh báo'),
            message: __('Rows {0}: Nhân viên {1} có {2} dòng OT trong ngày {3}. Nên gộp thành 1 dòng liên tục.',
                [rows, employee_name, entries.length, date]),
            indicator: 'orange'
        });
        frappe.validated = false;
        return false;
    }

    return true;
}

// Validate OT time continuity with shift
function validate_ot_continuity(frm) {
    if (!frm.doc.ot_employees || frm.doc.ot_employees.length === 0) {
        return;
    }

    // Prepare entries to check
    const entries_to_check = [];
    for (let d of frm.doc.ot_employees) {
        if (d.employee && d.date && d.begin_time && d.end_time) {
            entries_to_check.push({
                idx: d.idx,
                employee: d.employee,
                employee_name: d.employee_name,
                date: d.date,
                begin_time: d.begin_time,
                end_time: d.end_time
            });
        }
    }

    if (entries_to_check.length === 0) {
        return;
    }

    // Call server to validate OT continuity
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration.validate_ot_entries_continuity',
        args: {
            entries: entries_to_check
        },
        async: false,
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                // Found errors
                frappe.validated = false;

                // Show all errors
                for (let error of r.message) {
                    frappe.msgprint({
                        title: __('Lỗi giờ tăng ca'),
                        message: __('Row {0}: <b>{1}</b> ({2}) - Ca {3}<br>{4}', [
                            error.idx,
                            error.employee_name,
                            error.employee,
                            error.shift_type,
                            error.error
                        ]),
                        indicator: 'red'
                    });
                }
            } else {
                // Validation passed, set flag
                frm.ot_continuity_validated = true;
            }
        }
    });
}

// Check for maternity benefit time adjustment
// Returns true if dialog was shown (save should stop), false otherwise
function check_maternity_benefit_adjustment(frm) {
    if (!frm.doc.ot_employees || frm.doc.ot_employees.length === 0) {
        frm.maternity_check_done = true;
        return false;
    }

    // Prepare entries to check
    const entries_to_check = [];
    for (let d of frm.doc.ot_employees) {
        if (d.employee && d.date && d.begin_time && d.end_time) {
            entries_to_check.push({
                idx: d.idx,
                employee: d.employee,
                employee_name: d.employee_name,
                date: d.date,
                begin_time: d.begin_time,
                end_time: d.end_time
            });
        }
    }

    if (entries_to_check.length === 0) {
        frm.maternity_check_done = true;
        return false;
    }

    let dialog_shown = false;

    // Call server to check for maternity benefits
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration.check_employees_with_maternity_benefits',
        args: {
            entries: entries_to_check
        },
        async: false,
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                // Found employees with maternity benefits needing adjustment
                frappe.validated = false;
                dialog_shown = true;

                // Build message with employee details including period dates and shift info
                let employee_list = r.message.map(emp =>
                    `• Row ${emp.idx}: <b>${emp.employee_name}</b> (${emp.employee}) - ${emp.benefit_type}<br>
                     &nbsp;&nbsp;&nbsp;Giai đoạn: ${emp.from_date} - ${emp.to_date} | Ca: ${emp.shift_type} | Ngày OT: ${emp.date}`
                ).join('<br>');

                // Get shift end times for display (use first employee's times as example)
                let shift_end = r.message[0].shift_end;
                let adjusted_shift_end = r.message[0].adjusted_shift_end;

                let dialog = new frappe.ui.Dialog({
                    title: __('Điều chỉnh giờ tăng ca cho nhân viên có chế độ thai sản'),
                    fields: [
                        {
                            fieldtype: 'HTML',
                            options: `
                                <div style="margin-bottom: 15px;">
                                    <p>Các nhân viên sau đang trong giai đoạn <b>mang thai</b> hoặc <b>nuôi con nhỏ</b> và có giờ bắt đầu tăng ca lúc ${shift_end}:</p>
                                    <div style="background-color: #f8f9fa; padding: 10px; border-radius: 4px; margin: 10px 0;">
                                        ${employee_list}
                                    </div>
                                    <p style="color: #6c757d;">
                                        <i>Những nhân viên này được phép kết thúc ca sớm hơn 1 giờ so với bình thường, do đó giờ tăng ca cũng sớm hơn 1 giờ.</i>
                                    </p>
                                    <p><b>Bạn có muốn điều chỉnh giờ bắt đầu và kết thúc sớm hơn 1 giờ không?</b></p>
                                    <p style="color: #007bff;">
                                        (${shift_end} → ${adjusted_shift_end}, giờ kết thúc cũng giảm 1 giờ tương ứng)
                                    </p>
                                </div>
                            `
                        }
                    ],
                    primary_action_label: __('Có, điều chỉnh giờ'),
                    primary_action: function () {
                        dialog.hide();
                        // Adjust times for affected employees
                        adjust_maternity_employee_times(frm, r.message);
                        // Set flag to skip maternity check on next save
                        frm.maternity_check_done = true;
                        // Save the form
                        frm.save();
                    },
                    secondary_action_label: __('Không, giữ nguyên'),
                    secondary_action: function () {
                        dialog.hide();
                        // Set flag to skip maternity check on next save
                        frm.maternity_check_done = true;
                        // Save without adjustment
                        frm.save();
                    }
                });

                dialog.show();
            } else {
                // No employees need adjustment, mark as done
                frm.maternity_check_done = true;
            }
        }
    });

    return dialog_shown;
}

// Adjust begin_time and end_time for employees with maternity benefits (-1 hour)
function adjust_maternity_employee_times(frm, employees_to_adjust) {
    // Create a map of idx to adjustment
    const adjustment_map = new Map();
    employees_to_adjust.forEach(emp => {
        adjustment_map.set(emp.idx, true);
    });

    // Adjust times in child table
    frm.doc.ot_employees.forEach(d => {
        if (adjustment_map.has(d.idx)) {
            // Subtract 1 hour from begin_time
            d.begin_time = subtract_one_hour(d.begin_time);
            // Subtract 1 hour from end_time
            d.end_time = subtract_one_hour(d.end_time);
        }
    });

    // Refresh the child table
    frm.refresh_field('ot_employees');

    frappe.show_alert({
        message: __('Đã điều chỉnh giờ tăng ca cho {0} nhân viên có chế độ thai sản', [employees_to_adjust.length]),
        indicator: 'green'
    });
}

// Helper function to subtract 1 hour from time string
function subtract_one_hour(time_str) {
    if (!time_str) return time_str;

    // Parse time string (format: HH:MM:SS or HH:MM)
    const parts = time_str.split(':');
    let hours = parseInt(parts[0]);
    let minutes = parseInt(parts[1]);
    let seconds = parts.length > 2 ? parseInt(parts[2]) : 0;

    // Subtract 1 hour
    hours = hours - 1;
    if (hours < 0) {
        hours = 23; // Wrap around to previous day
    }

    // Format back to string
    return String(hours).padStart(2, '0') + ':' +
        String(minutes).padStart(2, '0') + ':' +
        String(seconds).padStart(2, '0');
}

function validate_duplicate_employees(frm) {
    const entries = [];

    for (let d of frm.doc.ot_employees || []) {
        // Skip validation if required fields are missing - handled by validate_required_fields
        if (!d.employee || !d.date || !d.begin_time || !d.end_time) {
            return;
        }

        entries.push({
            idx: d.idx,
            employee: d.employee,
            employee_name: d.employee_name,
            date: d.date,
            begin_time: d.begin_time,
            end_time: d.end_time
        });
    }

    // Check for duplicates and overlaps
    for (let i = 0; i < entries.length; i++) {
        for (let j = i + 1; j < entries.length; j++) {
            const entry1 = entries[i];
            const entry2 = entries[j];

            // Same employee and date
            if (entry1.employee === entry2.employee && entry1.date === entry2.date) {
                // Check for exact match or time overlap
                if (times_overlap(entry1.begin_time, entry1.end_time, entry2.begin_time, entry2.end_time)) {
                    frappe.validated = false;
                    frappe.msgprint(__('Row {0} and {1}: Duplicate overtime for employee {2} on {3}',
                        [entry1.idx, entry2.idx, entry1.employee_name, entry1.date]));
                    return;
                }
            }
        }
    }
}

function check_conflicts_with_submitted_records(frm) {
    if (!frm.doc.ot_employees || frm.doc.ot_employees.length === 0) {
        return;
    }

    // Prepare data for server-side validation
    const entries_to_check = [];
    for (let d of frm.doc.ot_employees) {
        if (d.employee && d.date && d.begin_time && d.end_time) {
            entries_to_check.push({
                idx: d.idx,
                employee: d.employee,
                employee_name: d.employee_name,
                date: d.date,
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
        method: 'customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration.check_overtime_conflicts',
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
                    var doc_link = `<a href="/app/overtime-registration/${conflict.existing_doc}" target="_blank">${conflict.existing_doc}</a>`;
                    frappe.msgprint(__('Row {0}: Employee {1} already has overtime on {2} ({3}-{4}). Conflicts with {5}',
                        [conflict.idx, conflict.employee_name, conflict.date, conflict.current_from, conflict.current_to, doc_link]));
                }
            }
        }
    });
}

function calculate_totals_and_apply_reason(frm) {
    if (!frm.doc.ot_employees || frm.doc.ot_employees.length === 0) {
        frm.set_value('total_employees', 0);
        frm.set_value('total_hours', 0);
        return;
    }

    const distinct_employees = new Set();
    let total_hours = 0.0;
    const child_reasons = new Set();

    // First pass: calculate totals and gather unique, non-empty child reasons
    frm.doc.ot_employees.forEach(d => {
        if (d.employee) {
            distinct_employees.add(d.employee);
        }

        if (d.begin_time && d.end_time) {
            // Simple time difference calculation
            const from_parts = d.begin_time.split(':');
            const to_parts = d.end_time.split(':');
            const from_minutes = parseInt(from_parts[0]) * 60 + parseInt(from_parts[1]);
            const to_minutes = parseInt(to_parts[0]) * 60 + parseInt(to_parts[1]);
            const diff_hours = (to_minutes - from_minutes) / 60;
            total_hours += diff_hours;
        }

        if (d.reason && d.reason.trim()) {
            child_reasons.add(d.reason.trim());
        }
    });

    // Update totals
    frm.set_value('total_employees', distinct_employees.size);
    frm.set_value('total_hours', total_hours);

    // If general reason is empty, populate it from unique child reasons
    // Also update if child_reasons has multiple unique reasons
    if (child_reasons.size > 0 && (!frm.doc.reason_general || child_reasons.size > 1)) {
        const sorted_reasons = Array.from(child_reasons).sort();
        frm.set_value('reason_general', sorted_reasons.join(', '));
    }

    // If a general reason now exists (either provided by user or generated),
    // apply it to any child rows that have an empty reason.
    if (frm.doc.reason_general) {
        frm.doc.ot_employees.forEach(d => {
            if (!d.reason) {
                d.reason = frm.doc.reason_general;
            }
        });
        frm.refresh_field('ot_employees');
    }
}

function update_registered_groups(frm) {
    if (!frm.doc.ot_employees || frm.doc.ot_employees.length === 0) {
        frm.set_value('registered_groups', '');
        return;
    }

    const distinct_groups = new Set();

    // Collect unique groups from all rows
    frm.doc.ot_employees.forEach(d => {
        if (d.group && d.group.trim()) {
            distinct_groups.add(d.group.trim());
        }
    });

    // Update registered groups summary
    if (distinct_groups.size > 0) {
        const sorted_groups = Array.from(distinct_groups).sort();
        frm.set_value('registered_groups', sorted_groups.join(', '));
    } else {
        frm.set_value('registered_groups', '');
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

// Function to remove rows with empty employee
function remove_empty_overtime_rows(frm, silent = false) {
    var rows_to_remove = [];

    if (frm.doc.ot_employees) {
        frm.doc.ot_employees.forEach(function (row, index) {
            if (!row.employee) {
                rows_to_remove.push(row.name);
            }
        });
    }

    // Remove rows in reverse order to avoid index issues
    rows_to_remove.reverse().forEach(function (row_name) {
        var row = frm.doc.ot_employees.find(r => r.name === row_name);
        if (row) {
            frm.get_field('ot_employees').grid.grid_rows_by_docname[row_name].remove();
        }
    });

    if (rows_to_remove.length > 0) {
        frm.refresh_field('ot_employees');

        if (!silent) {
            frappe.show_alert({
                message: __('Removed {0} empty rows', [rows_to_remove.length]),
                indicator: 'blue'
            });
        }
    } else if (!silent) {
        frappe.show_alert({
            message: __('No empty rows found'),
            indicator: 'orange'
        });
    }
}

// Function to auto-fill approver based on requested_by employee using HRMS pattern
function set_approver_based_on_requested_by(frm, employee) {
    if (!employee) {
        return;
    }

    // Use the same method as Leave Application
    frappe.call({
        method: 'hrms.hr.doctype.leave_application.leave_application.get_leave_approver',
        args: {
            employee: employee
        },
        callback: function (r) {
            if (r && r.message) {
                frm.set_value('approver', r.message);

                // Set the approver full name (get employee name, not user name)
                if (r.message) {
                    get_employee_name_from_user(frm, r.message);
                }
            } else {
                frm.set_value('approver', '');
                frm.set_value('approver_full_name', '');
            }
        },
        error: function (r) {
            frm.set_value('approver', '');
            frm.set_value('approver_full_name', '');
        }
    });
}

// Helper function to get employee name from user ID for approver_full_name field
function get_employee_name_from_user(frm, user_id) {
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Employee',
            fieldname: 'employee_name',
            filters: {
                'user_id': user_id
            }
        },
        callback: function (emp_r) {
            if (emp_r.message && emp_r.message.employee_name) {
                frm.set_value('approver_full_name', emp_r.message.employee_name);
            } else {
                // Fallback to user's full name if no employee record found
                frm.set_value('approver_full_name', frappe.user.full_name(user_id));
            }
        },
        error: function (r) {
            // Fallback to user's full name on error
            frm.set_value('approver_full_name', frappe.user.full_name(user_id));
        }
    });
}

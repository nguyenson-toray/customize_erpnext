// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Overtime Registration", {
    refresh(frm) {
        // Add custom styling for the form
        frm.page.add_inner_button(__('Get Employees'), function () {
            show_employee_selection_dialog(frm);
        }, __('Actions'));

        // Add button to remove empty rows
        frm.page.add_inner_button(__('Remove Empty Rows'), function () {
            remove_empty_overtime_rows(frm);
        }, __('Actions'));

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

    validate(frm) {
        // Auto-remove empty rows before validation
        remove_empty_overtime_rows(frm, true);

        // Always validate required fields first
        if (!validate_required_fields(frm)) {
            return false;
        }

        // Synchronous validation for immediate feedback
        validate_duplicate_employees(frm);

        // Check conflicts with submitted records (asynchronous)
        check_conflicts_with_submitted_records(frm);

        calculate_totals_and_apply_reason(frm);

        // Update registered groups summary when saving
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

function get_dialog_html() {
    return `
        <div class="overtime-dialog">
            <!-- Top Panel -->
            <div class="top-panel" style="padding: 15px; border-bottom: 2px solid #e9ecef; margin-bottom: 15px; background-color: #f8f9fa;">
                <div class="row">
                    <div class="col-md-2">
                        <div class="form-group">
                            <label class="control-label">Group <span class="text-danger">*</span></label>
                            <select class="form-control" id="group_select" required>
                                <option value="">Select Group...</option>
                            </select>
                        </div>
                        <div class="form-group" style="margin-top: 10px;">
                            <label class="control-label">Week <span class="text-danger">*</span></label>
                            <select class="form-control" id="week_select" required>
                                <option value="">Select Week...</option>
                            </select>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="form-group">
                            <label class="control-label">Select Days <span class="text-danger">*</span></label>
                            <div class="day-checkboxes" style="display: flex; flex-wrap: wrap; gap: 15px; margin-top: 8px;">
                                <label class="checkbox-inline">
                                    <input type="checkbox" id="all_days" class="day-checkbox-control"> <strong>All</strong>
                                </label>
                                <div id="individual_days"></div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="form-group">
                            <label class="control-label">Time Period</label>
                            <div class="row">
                                <div class="col-md-6">
                                    <label class="control-label" style="font-size: 12px; margin-bottom: 5px;">Begin Time</label>
                                    <input type="time" class="form-control" id="time_from" value="17:00">
                                </div>
                                <div class="col-md-6">
                                    <label class="control-label" style="font-size: 12px; margin-bottom: 5px;">End Time</label>
                                    <input type="time" class="form-control" id="time_to" value="19:00">
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="row" style="margin-top: 10px;">
                    <div class="col-md-12">
                        <div class="form-group">
                            <label class="control-label">Reason <span class="text-danger">*</span></label>
                            <input type="text" class="form-control" id="reason_input" placeholder="Enter reason for overtime" required>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Main Content Panel -->
            <div class="main-content" style="min-height: 450px;">
                <div class="row">
                    <!-- Left Panel - Available Employees -->
                    <div class="col-md-5">
                        <div class="panel panel-default">
                            <div class="panel-heading" style="background-color: #f1f3f4;">
                                <h4 class="panel-title">Available Employees</h4>
                                <small class="text-muted">Select group to load employees</small>
                            </div>
                            <div class="panel-body" style="height: 400px; overflow-y: auto; padding: 10px;">
                                <div id="available_employees">
                                    <div class="empty-state text-center text-muted" style="padding: 50px 20px;">
                                        <i class="fa fa-users fa-3x" style="opacity: 0.3;"></i>
                                        <p style="margin-top: 15px;">Select a group to load employees</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Center Panel - Move Buttons -->
                    <div class="col-md-2" style="display: flex; align-items: center; justify-content: center; flex-direction: column;">
                        <button type="button" class="btn btn-primary btn-sm move-btn" id="move_right" style="margin-bottom: 15px; width: 80px; height: 40px;">
                            <i class="fa fa-arrow-right"></i><br>
                            <small>Add</small>
                        </button>
                        <button type="button" class="btn btn-default btn-sm move-btn" id="move_left" style="width: 80px; height: 40px;">
                            <i class="fa fa-arrow-left"></i><br>
                            <small>Remove</small>
                        </button>
                    </div>

                    <!-- Right Panel - Selected Employees -->
                    <div class="col-md-5">
                        <div class="panel panel-default">
                            <div class="panel-heading" style="background-color: #e8f5e8;">
                                <h4 class="panel-title" id="selected_count_header">Selected Employees (0)</h4>
                                <small class="text-muted">Selected employees will accumulate across groups</small>
                            </div>
                            <div class="panel-body" style="height: 400px; overflow-y: auto; padding: 10px;">
                                <div id="selected_employees">
                                    <div class="empty-state text-center text-muted" style="padding: 50px 20px;">
                                        <i class="fa fa-check-circle fa-3x" style="opacity: 0.3;"></i>
                                        <p style="margin-top: 15px;">No employees selected</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Summary Panel -->
            <div class="summary-panel" style="margin-top: 15px; padding: 15px; background-color: #f8f9fa; border-radius: 4px;">
                <div class="row">
                    <div class="col-md-6">
                        <strong>Summary:</strong>
                        <span id="summary_text">Please select employees and configure overtime details</span>
                    </div>
                    <div class="col-md-6 text-right">
                        <button type="button" class="btn btn-info btn-sm" id="refresh_available_btn">
                            <i class="fa fa-refresh"></i> Refresh Available
                        </button>
                        <button type="button" class="btn btn-warning btn-sm" id="clear_all_selected_btn">
                            <i class="fa fa-times"></i> Clear All Selected
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <style>
            .overtime-dialog .employee-item {
                padding: 10px;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin-bottom: 8px;
                cursor: pointer;
                transition: all 0.2s ease;
                background-color: white;
            }
            
            .overtime-dialog .employee-item:hover {
                border-color: #007bff;
                background-color: #f8f9ff;
                transform: translateY(-1px);
                box-shadow: 0 2px 4px rgba(0,123,255,0.1);
            }
            
            .overtime-dialog .employee-item.selected {
                border-color: #007bff;
                background-color: #e7f3ff;
                box-shadow: 0 0 0 2px rgba(0,123,255,0.25);
            }
            
            .overtime-dialog .employee-item .employee-id {
                font-weight: bold;
                color: #495057;
                font-size: 14px;
            }
            
            .overtime-dialog .employee-item .employee-name {
                color: #6c757d;
                font-size: 13px;
                margin-top: 2px;
            }
            
            .overtime-dialog .employee-item .employee-group {
                color: #28a745;
                font-size: 11px;
                margin-top: 2px;
                font-weight: 500;
            }
            
            .overtime-dialog .move-btn {
                border-radius: 8px;
                font-size: 11px;
                font-weight: bold;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            
            .overtime-dialog .move-btn:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            }
            
            .overtime-dialog .small-label {
                font-size: 11px;
                color: #6c757d;
                margin-bottom: 2px;
                display: block;
            }
            
            .overtime-dialog .day-checkboxes label {
                margin-right: 0;
                margin-bottom: 5px;
                font-size: 12px;
                font-weight: normal;
            }
            
            .overtime-dialog .empty-state {
                user-select: none;
            }
        </style>
    `;
}

function initialize_dialog() {
    // Wait for DOM elements to be available
    const checkElements = () => {
        const groupSelect = document.getElementById('group_select');
        const weekSelect = document.getElementById('week_select');

        if (!groupSelect || !weekSelect) {
            setTimeout(checkElements, 100);
            return;
        }

        // Setup event handlers FIRST before loading data
        setup_event_handlers();

        // Then load initial data
        load_groups();
        load_weeks();

        // Render current selected employees
        render_selected_employees();
    };

    checkElements();
}

function load_groups() {
    // Check if we need to filter groups based on current user
    const filterBy = currentDialog && currentDialog.frm && currentDialog.frm.doc.filter_employee_by;
    const userGroup = currentDialog && currentDialog.frm && currentDialog.frm.doc.request_by_group;

    const filters = (filterBy === 'custom_group' && userGroup) ? { 'name': userGroup } : {};

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Group',
            fields: ['name', 'group'],
            filters: filters,
            order_by: '`group` asc',
            limit_page_length: 0  // Get all records
        },
        callback: function (r) {
            const groupSelect = document.getElementById('group_select');

            if (r.message && groupSelect) {
                // Clear and rebuild options
                groupSelect.innerHTML = '';

                // Add default option
                const defaultOption = document.createElement('option');
                defaultOption.value = '';
                defaultOption.textContent = 'Select Group...';
                groupSelect.appendChild(defaultOption);

                // Add group options
                r.message.forEach(group => {
                    const displayName = group.group || group.name;
                    const option = document.createElement('option');
                    option.value = group.name;
                    option.textContent = displayName;
                    groupSelect.appendChild(option);
                });

                // Force refresh the select element
                groupSelect.disabled = false;
                groupSelect.readOnly = false;
            }
        }
    });
}

function load_weeks() {
    const weekSelect = document.getElementById('week_select');
    if (!weekSelect) return;

    const today = new Date();
    const currentDay = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - currentDay + 1);

    weekSelect.innerHTML = '<option value="">Select Week...</option>';

    // Current week and next 2 weeks
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
        } else {
            weekLabel = __('Week') + ` +${i} (${mondayStr} - ${sundayStr})`;
        }

        weekSelect.innerHTML += `<option value="${i}">${weekLabel}</option>`;
    }

    // Set current week as default
    weekSelect.value = '0';
    generate_week_dates(0);
}

function generate_week_dates(weekOffset = 0) {
    const today = new Date();
    const currentDay = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - currentDay + 1 + (weekOffset * 7));

    const days = [__('Monday'), __('Tuesday'), __('Wednesday'), __('Thursday'), __('Friday'), __('Saturday')];
    const dayAbbr = [__('Mon'), __('Tue'), __('Wed'), __('Thu'), __('Fri'), __('Sat')];

    const individualDaysContainer = document.getElementById('individual_days');
    if (!individualDaysContainer) return;

    let html = '';
    days.forEach((day, index) => {
        const date = new Date(monday);
        date.setDate(monday.getDate() + index);
        const dateStr = date.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' });
        const isoDateStr = date.toISOString().split('T')[0];

        html += `
            <label class="checkbox-inline">
                <input type="checkbox" class="day-checkbox" data-day="${day.toLowerCase()}" data-date="${isoDateStr}">
                ${dayAbbr[index]} ${dateStr}
            </label>
        `;
    });

    individualDaysContainer.innerHTML = html;
}

// Store event handlers to avoid duplicates
let eventHandlersAttached = false;

function setup_event_handlers() {
    // Don't attach handlers multiple times
    if (eventHandlersAttached) {
        return;
    }

    // Use event delegation on document to avoid conflicts
    document.addEventListener('change', function (e) {
        // Only handle events within the overtime dialog
        if (!e.target.closest('.overtime-dialog')) return;

        if (e.target.id === 'group_select') {
            const groupName = e.target.value;
            if (groupName) {
                load_available_employees(groupName);
            } else {
                clear_available_employees();
            }
        } else if (e.target.id === 'week_select') {
            const weekOffset = parseInt(e.target.value);
            if (!isNaN(weekOffset)) {
                generate_week_dates(weekOffset);
            }
        } else if (e.target.id === 'all_days') {
            const dayCheckboxes = document.querySelectorAll('.day-checkbox');
            dayCheckboxes.forEach(cb => cb.checked = e.target.checked);
        } else if (e.target.classList.contains('day-checkbox')) {
            const allChecked = Array.from(document.querySelectorAll('.day-checkbox')).every(cb => cb.checked);
            const allDaysEl = document.getElementById('all_days');
            if (allDaysEl) {
                allDaysEl.checked = allChecked;
            }
        }
    });


    // Set up click event delegation
    document.addEventListener('click', function (e) {
        // Only handle events within the overtime dialog
        if (!e.target.closest('.overtime-dialog')) return;

        // Move buttons
        if (e.target.id === 'move_right' || e.target.closest('#move_right')) {
            move_employees_to_selected();
        } else if (e.target.id === 'move_left' || e.target.closest('#move_left')) {
            remove_employees_from_selected();
        }
        // Summary panel buttons
        else if (e.target.id === 'refresh_available_btn' || e.target.closest('#refresh_available_btn')) {
            refresh_available_employees();
        } else if (e.target.id === 'clear_all_selected_btn' || e.target.closest('#clear_all_selected_btn')) {
            clear_all_selected();
        }
        // Employee selection
        else {
            const employeeItem = e.target.closest('.employee-item');
            if (employeeItem && employeeItem.closest('#available_employees')) {
                employeeItem.classList.toggle('selected');
            } else if (employeeItem && employeeItem.closest('#selected_employees')) {
                employeeItem.classList.toggle('selected');
            }
        }
    });

    eventHandlersAttached = true;
}

function load_available_employees(groupName) {
    const frm = currentDialog && currentDialog.frm;
    const filterBy = frm && frm.doc.filter_employee_by;

    if (filterBy) {
        get_user_filter_value(frm, function (filterBy, filterValue) {
            if (!filterValue) {
                frappe.show_alert({
                    message: __('Current user does not have a valid ' + filterBy + ' value'),
                    indicator: 'red'
                });
                clear_available_employees();
                return;
            }

            // Build filters for employee query
            const employeeFilters = {
                'custom_group': groupName,
                'status': 'Active'
            };

            // Add filter based on filter_employee_by
            employeeFilters[filterBy] = filterValue;

            load_employees_with_filters(employeeFilters);
        });
    } else {
        // No filtering, load all employees from group
        const employeeFilters = {
            'custom_group': groupName,
            'status': 'Active'
        };
        load_employees_with_filters(employeeFilters);
    }
}

function load_employees_with_filters(filters) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Employee',
            fields: ['name', 'employee_name', 'custom_group', 'department', 'custom_section', 'status'],
            filters: filters,
            order_by: 'employee_name asc',
            limit_page_length: 0  // Get all records
        },
        callback: function (r) {
            if (r.message) {
                currentGroupEmployees.clear();
                r.message.forEach(emp => {
                    currentGroupEmployees.set(emp.name, emp);
                });
                render_available_employees(r.message);
            } else {
                clear_available_employees();
            }
        },
        error: function (r) {
            frappe.show_alert({
                message: __('Error loading employees: ') + (r.message || 'Unknown error'),
                indicator: 'red'
            });
            clear_available_employees();
        }
    });
}

function render_available_employees(employees) {
    const container = document.getElementById('available_employees');
    if (!container) return;

    if (employees.length === 0) {
        container.innerHTML = `
            <div class="empty-state text-center text-muted" style="padding: 50px 20px;">
                <i class="fa fa-user-times fa-3x" style="opacity: 0.3;"></i>
                <p style="margin-top: 15px;">No active employees found in this group</p>
            </div>
        `;
        return;
    }

    let html = '';
    employees.forEach(emp => {
        // Don't show employees that are already selected
        if (!selectedEmployees.has(emp.name)) {
            html += create_employee_item_html(emp);
        }
    });

    if (html === '') {
        container.innerHTML = `
            <div class="empty-state text-center text-muted" style="padding: 50px 20px;">
                <i class="fa fa-check-circle fa-3x" style="opacity: 0.3;"></i>
                <p style="margin-top: 15px;">All employees from this group are already selected</p>
            </div>
        `;
    } else {
        container.innerHTML = html;
    }
}

function render_selected_employees() {
    const container = document.getElementById('selected_employees');
    if (!container) return;

    if (selectedEmployees.size === 0) {
        container.innerHTML = `
            <div class="empty-state text-center text-muted" style="padding: 50px 20px;">
                <i class="fa fa-check-circle fa-3x" style="opacity: 0.3;"></i>
                <p style="margin-top: 15px;">No employees selected</p>
            </div>
        `;
    } else {
        let html = '';
        selectedEmployees.forEach(emp => {
            html += create_employee_item_html(emp);
        });
        container.innerHTML = html;
    }

    update_selected_count();
    update_summary();
}

function create_employee_item_html(employee) {
    const statusBadge = employee.status !== 'Active' ?
        `<span class="label label-warning" style="font-size: 9px; margin-left: 5px;">${employee.status}</span>` : '';

    // Build additional info based on available fields
    let additionalInfo = [];
    if (employee.custom_group) additionalInfo.push(`Group: ${employee.custom_group}`);
    if (employee.custom_section) additionalInfo.push(`Section: ${employee.custom_section}`);
    if (employee.department) additionalInfo.push(`Dept: ${employee.department}`);

    const infoText = additionalInfo.length > 0 ? `(${additionalInfo.join(', ')})` : '';

    return `
        <div class="employee-item" data-employee-id="${employee.name}">
            <div class="employee-id">${employee.name}${statusBadge}</div>
            <div class="employee-name">${employee.employee_name || employee.name} <small class="text-muted">${infoText}</small></div>
        </div>
    `;
}

function move_employees_to_selected() {
    const selectedItems = document.querySelectorAll('#available_employees .employee-item.selected');

    if (selectedItems.length === 0) {
        frappe.show_alert({
            message: __('Please select employees to add'),
            indicator: 'orange'
        });
        return;
    }

    let addedCount = 0;
    selectedItems.forEach(item => {
        const employeeId = item.getAttribute('data-employee-id');
        const employee = currentGroupEmployees.get(employeeId);

        if (employee && !selectedEmployees.has(employeeId)) {
            selectedEmployees.set(employeeId, employee);
            addedCount++;
        }
    });

    if (addedCount > 0) {
        render_selected_employees();
        // Refresh available list to hide newly selected employees
        const groupSelect = document.getElementById('group_select');
        if (groupSelect && groupSelect.value) {
            load_available_employees(groupSelect.value);
        }

        frappe.show_alert({
            message: __('Added {0} employee(s) to selection', [addedCount]),
            indicator: 'green'
        });
    }
}

function remove_employees_from_selected() {
    const selectedItems = document.querySelectorAll('#selected_employees .employee-item.selected');

    if (selectedItems.length === 0) {
        frappe.show_alert({
            message: __('Please select employees to remove'),
            indicator: 'orange'
        });
        return;
    }

    let removedCount = 0;
    selectedItems.forEach(item => {
        const employeeId = item.getAttribute('data-employee-id');
        if (selectedEmployees.has(employeeId)) {
            selectedEmployees.delete(employeeId);
            removedCount++;
        }
    });

    if (removedCount > 0) {
        render_selected_employees();
        // Refresh available list to show newly unselected employees
        const groupSelect = document.getElementById('group_select');
        if (groupSelect && groupSelect.value) {
            load_available_employees(groupSelect.value);
        }

        frappe.show_alert({
            message: __('Removed {0} employee(s) from selection', [removedCount]),
            indicator: 'blue'
        });
    }
}

function clear_available_employees() {
    const container = document.getElementById('available_employees');
    if (container) {
        container.innerHTML = `
            <div class="empty-state text-center text-muted" style="padding: 50px 20px;">
                <i class="fa fa-users fa-3x" style="opacity: 0.3;"></i>
                <p style="margin-top: 15px;">Select a group to load employees</p>
            </div>
        `;
    }
    currentGroupEmployees.clear();
}

function clear_all_selected() {
    if (selectedEmployees.size === 0) {
        frappe.show_alert({
            message: __('No employees selected to clear'),
            indicator: 'orange'
        });
        return;
    }

    frappe.confirm(__('Are you sure you want to clear all selected employees?'), () => {
        selectedEmployees.clear();
        render_selected_employees();

        // Refresh available list
        const groupSelect = document.getElementById('group_select');
        if (groupSelect && groupSelect.value) {
            load_available_employees(groupSelect.value);
        }

        frappe.show_alert({
            message: __('All selected employees cleared'),
            indicator: 'blue'
        });
    });
}

function refresh_available_employees() {
    const groupSelect = document.getElementById('group_select');
    if (groupSelect && groupSelect.value) {
        load_available_employees(groupSelect.value);
        frappe.show_alert({
            message: __('Available employees refreshed'),
            indicator: 'blue'
        });
    } else {
        frappe.show_alert({
            message: __('Please select a group first'),
            indicator: 'orange'
        });
    }
}

function update_selected_count() {
    const header = document.getElementById('selected_count_header');
    if (header) {
        header.textContent = `Selected Employees (${selectedEmployees.size})`;
    }
}

function update_summary() {
    const summaryEl = document.getElementById('summary_text');
    if (!summaryEl) return;

    if (selectedEmployees.size === 0) {
        summaryEl.textContent = 'Please select employees and configure overtime details';
        return;
    }

    const selectedDays = document.querySelectorAll('.day-checkbox:checked').length;
    const reason = document.getElementById('reason_input')?.value || '';

    let summary = `${selectedEmployees.size} employee(s) selected`;
    if (selectedDays > 0) {
        summary += `, ${selectedDays} day(s) selected`;
    }
    if (reason) {
        summary += `, Reason: ${reason}`;
    }

    summaryEl.textContent = summary;
}

function save_overtime_registration(frm) {
    // Validation
    if (selectedEmployees.size === 0) {
        frappe.show_alert({
            message: __('Please select at least one employee'),
            indicator: 'red'
        });
        return;
    }

    const selectedDays = Array.from(document.querySelectorAll('.day-checkbox:checked'));
    if (selectedDays.length === 0) {
        frappe.show_alert({
            message: __('Please select at least one day'),
            indicator: 'red'
        });
        return;
    }

    const reason = document.getElementById('reason_input')?.value?.trim();
    if (!reason) {
        frappe.show_alert({
            message: __('Please enter a reason for overtime'),
            indicator: 'red'
        });
        return;
    }

    const timeFrom = document.getElementById('time_from')?.value;
    const timeTo = document.getElementById('time_to')?.value;

    // Clear existing rows
    frm.clear_table('ot_employees');

    // Add selected employees to child table
    selectedEmployees.forEach(employee => {
        selectedDays.forEach(dayCheckbox => {
            const child = frm.add_child('ot_employees');
            child.employee = employee.name;
            child.employee_name = employee.employee_name || employee.name;
            child.date = dayCheckbox.getAttribute('data-date');
            child.begin_time = timeFrom;
            child.end_time = timeTo;
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

// Helper function to get employee full name
function get_employee_full_name(employee_id, callback) {
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Employee',
            fieldname: 'employee_name',
            filters: {
                'name': employee_id
            }
        },
        callback: function (r) {
            if (r.message && r.message.employee_name) {
                callback(r.message.employee_name);
            } else {
                callback('');
            }
        }
    });
}

// Helper function to get approver full name from workflow actions
function get_approver_full_name(frm) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Workflow Action',
            fields: ['user'],
            filters: {
                'reference_doctype': frm.doc.doctype,
                'reference_name': frm.doc.name,
                'status': 'Approved'
            },
            order_by: 'creation desc',
            limit: 1
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                const approver_user = r.message[0].user;

                // Get the approver's employee record
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Employee',
                        fields: ['employee_name'],
                        filters: {
                            'user_id': approver_user
                        },
                        limit: 1
                    },
                    callback: function (emp_r) {
                        if (emp_r.message && emp_r.message.length > 0) {
                            frm.set_value('approver_full_name', emp_r.message[0].employee_name);
                        } else {
                            // Fallback to user's full name if no employee record
                            frappe.call({
                                method: 'frappe.client.get_value',
                                args: {
                                    doctype: 'User',
                                    fieldname: 'full_name',
                                    filters: {
                                        'name': approver_user
                                    }
                                },
                                callback: function (user_r) {
                                    if (user_r.message && user_r.message.full_name) {
                                        frm.set_value('approver_full_name', user_r.message.full_name);
                                    }
                                }
                            });
                        }
                    }
                });
            }
        }
    });
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
        error: function(r) {
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
        error: function(r) {
            // Fallback to user's full name on error
            frm.set_value('approver_full_name', frappe.user.full_name(user_id));
        }
    });
}

// Helper function to get employee name for approver full name field
function get_employee_name_for_approver(frm, employee) {
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Employee',
            fieldname: 'employee_name',
            filters: {
                'name': employee
            }
        },
        callback: function (emp_r) {
            if (emp_r.message && emp_r.message.employee_name) {
                frm.set_value('approver_full_name', emp_r.message.employee_name);
            }
        }
    });
}

// Helper function to get user full name for approver full name field (fallback)
function get_user_full_name_for_approver(frm, user) {
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'User',
            fieldname: 'full_name',
            filters: {
                'name': user
            }
        },
        callback: function (user_r) {
            if (user_r.message && user_r.message.full_name) {
                frm.set_value('approver_full_name', user_r.message.full_name);
            }
        }
    });
}



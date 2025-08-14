console.log('Employee list customization loaded successfully');

frappe.listview_settings['Employee'] = {
    onload: function (listview) {
        console.log('Employee listview onload triggered');
        // Add individual menu items under Actions
        listview.page.add_menu_item(__('Quick Add Employee'), function () {
            show_quick_add_employee_dialog();
        });

        listview.page.add_menu_item(__('Get Fingerprint'), function () {
            show_get_fingerprint_dialog();
        });

        listview.page.add_menu_item(__('Sync Attendance ID'), function () {
            show_sync_attendance_dialog();
        });
    }
};

function show_quick_add_employee_dialog() {
    // Get employee creation preview info
    frappe.call({
        method: 'customize_erpnext.api.employee.employee_utils.get_employee_creation_preview',
        callback: function (r) {
            let preview_info = '';
            if (r.message) {
                let data = r.message;
                let highest = data.highest_employee;
                preview_info = `
                    <div class="alert alert-info">
                        <div class="row">
                            <div class="col-md-6">
                                <strong>${__('Current Highest Employee')}:</strong><br>
                                ${__('Employee')}: ${highest.employee}<br>
                                ${__('Name')}: ${highest.employee_name}<br>
                                ${__('Attendance Device ID')}: ${highest.attendance_device_id || __('Not Set')}
                            </div>
                            <div class="col-md-6">
                                <strong>${__('Next Employee Will Be')}:</strong><br>
                                ${__('Employee')}: <strong style="color: green;">${data.next_employee_code}</strong><br>
                                ${__('Attendance Device ID')}: <strong style="color: green;">${data.next_attendance_device_id}</strong>
                            </div>
                        </div>
                    </div>
                `;
            }

            let d = new frappe.ui.Dialog({
                title: __('Quick Add Employees'),
                size: 'large',
                fields: [
                    {
                        label: __('Current Status'),
                        fieldname: 'preview_info',
                        fieldtype: 'HTML',
                        options: preview_info
                    },
                    {
                        label: __('Instructions'),
                        fieldname: 'instructions',
                        fieldtype: 'HTML',
                        options: `
                            <div class="text-muted">
                                <p><strong>${__('Format')}:</strong> ${__('full_name; gender; date_of_birth; [date_of_joining]')}</p>
                                <p><strong>${__('Notes')}:</strong></p>
                                <ul>
                                    <li>${__('Each employee on a separate line')}</li>
                                    <li>${__('Full name will be split into first and last name automatically')}</li>
                                    <li>${__('Gender')}: ${__('Male, Female, or Other')}</li>
                                    <li>${__('Date format')}: ${__('dd/mm/yyyy')}</li>
                                    <li>${__('Date of joining is optional - if not provided, today\'s date will be used')}</li>
                                    <li>${__('Employee code (TIQN-XXXX) and Attendance Device ID will be auto-generated')}</li>
                                </ul>
                                <p><strong>${__('Example')}:</strong></p>
                                <code>
                                    Nguyễn Văn A; Male; 15/05/1990; 01/08/2024<br>
                                    Trần Thị B; Female; 20/03/1985<br> 
                                </code>
                            </div>
                        `
                    },
                    {
                        label: __('Employee Data'),
                        fieldname: 'employee_data',
                        fieldtype: 'Long Text',
                        reqd: 1,
                        description: __('Enter employee data in the format specified above')
                    }
                ],
                primary_action_label: __('Create Employees'),
                primary_action(values) {
                    if (!values.employee_data) {
                        frappe.msgprint(__('Please enter employee data'));
                        return;
                    }

                    frappe.call({
                        method: 'customize_erpnext.api.employee.employee_utils.create_employees_bulk',
                        args: {
                            employees_data: values.employee_data
                        },
                        callback: function (r) {
                            if (r.message) {
                                let result = r.message;
                                let message = `<p><strong>${__('Successfully created {0} employees', [result.success])}:</strong></p>`;

                                if (result.created_employees && result.created_employees.length > 0) {
                                    message += '<ul>';
                                    result.created_employees.forEach(emp => {
                                        message += `<li><strong>${emp.employee}</strong> - ${emp.employee_name} (${__('Device ID')}: ${emp.attendance_device_id})</li>`;
                                    });
                                    message += '</ul>';
                                }

                                if (result.errors && result.errors.length > 0) {
                                    message += `<p><strong>${__('Errors')}:</strong></p><ul>`;
                                    result.errors.forEach(error => {
                                        message += `<li class="text-danger">${error}</li>`;
                                    });
                                    message += '</ul>';
                                }

                                frappe.msgprint({
                                    title: __('Bulk Employee Creation Results'),
                                    message: message,
                                    indicator: 'green'
                                });

                                d.hide();
                                cur_list.refresh();
                            }
                        }
                    });
                }
            });

            d.show();
        }
    });
}

function show_get_fingerprint_dialog() {
    let d = new frappe.ui.Dialog({
        title: __('Get Fingerprint'),
        fields: [
            {
                label: __('Employee'),
                fieldname: 'employee',
                fieldtype: 'Link',
                options: 'Employee',
                reqd: 1,
                onchange: function () {
                    let employee = d.get_value('employee');
                    if (employee) {
                        frappe.call({
                            method: 'customize_erpnext.api.employee.employee_utils.get_employee_fingerprint_data',
                            args: {
                                employee_id: employee
                            },
                            callback: function (r) {
                                if (r.message) {
                                    let data = r.message;
                                    d.set_value('employee_name', data.employee_name);
                                    d.set_value('attendance_device_id', data.attendance_device_id);
                                }
                            }
                        });
                    }
                }
            },
            {
                label: __('Employee Name'),
                fieldname: 'employee_name',
                fieldtype: 'Data',
                read_only: 1
            },
            {
                label: __('Attendance Device ID'),
                fieldname: 'attendance_device_id',
                fieldtype: 'Data',
                read_only: 1
            },
            {
                label: __('Finger Selection'),
                fieldname: 'finger_selection',
                fieldtype: 'Select',
                options: [
                    '',
                    __('Left Thumb'),
                    __('Left Index'),
                    __('Left Middle'),
                    __('Left Ring'),
                    __('Left Little'),
                    __('Right Thumb'),
                    __('Right Index'),
                    __('Right Middle'),
                    __('Right Ring'),
                    __('Right Little')
                ].join('\n'),
                reqd: 1
            },
            {
                label: __('Instructions'),
                fieldname: 'fingerprint_instructions',
                fieldtype: 'HTML',
                options: `
                    <div class="text-muted">
                        <p><strong>${__('Fingerprint Collection Process')}:</strong></p>
                        <ol>
                            <li>${__('Select an employee')}</li>
                            <li>${__('Choose the finger to scan')}</li>
                            <li>${__('Click "Start Fingerprint Capture" to begin the process')}</li>
                            <li>${__('Additional functionality will be implemented later')}</li>
                        </ol>
                    </div>
                `
            }
        ],
        primary_action_label: __('Start Fingerprint Capture'),
        primary_action(values) {
            if (!values.employee) {
                frappe.msgprint(__('Please select an employee'));
                return;
            }

            if (!values.finger_selection) {
                frappe.msgprint(__('Please select a finger'));
                return;
            }

            frappe.msgprint({
                title: __('Fingerprint Capture'),
                message: __('Fingerprint capture functionality will be implemented in the next phase. Selected: {0} - {1}', [values.employee_name, values.finger_selection]),
                indicator: 'blue'
            });
        }
    });

    d.show();
}

function show_sync_attendance_dialog() {
    frappe.msgprint({
        title: __('Sync Attendance ID'),
        message: __('This functionality will synchronize attendance data and fingerprint data to attendance devices. Implementation will be completed in the next phase.'),
        indicator: 'blue'
    });
}
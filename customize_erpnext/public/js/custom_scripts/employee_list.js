console.log('Employee list customization loaded successfully');

frappe.listview_settings['Employee'] = {
    onload: function (listview) {
        console.log('Employee listview onload triggered');
        // Add individual menu items under Actions
        listview.page.add_menu_item(__('Get Fingerprint'), function () {
            show_get_fingerprint_dialog();
        });

        listview.page.add_menu_item(__('Sync Attendance ID'), function () {
            show_sync_attendance_dialog();
        });
    }
};


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
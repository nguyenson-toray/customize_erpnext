// import apps/customize_erpnext/customize_erpnext/public/js/utilities.js

// Store original employee value to prevent naming series interference
window.original_employee_code = null;

frappe.ui.form.on('Employee', {
    refresh: function (frm) {
        if (frm.is_new()) {

            // Auto-populate employee code and attendance device ID for new employees
            if (!frm.doc.employee || !frm.doc.employee.startsWith('TIQN-')) {
                frappe.call({
                    method: 'customize_erpnext.api.employee.employee_utils.get_next_employee_code',
                    callback: function (r) {
                        if (r.message) {
                            frm.set_value('employee', r.message);
                            // Store the original value
                            window.original_employee_code = r.message;

                            // Update naming series to prevent duplicates
                            let employee_num = parseInt(r.message.replace('TIQN-', '')) - 1;
                            frappe.call({
                                method: 'customize_erpnext.api.employee.employee_utils.set_series',
                                args: {
                                    prefix: 'TIQN-',
                                    current_highest_id: employee_num
                                },
                                callback: function(series_r) {
                                    if (series_r.message) {
                                        console.log('Series update result:', series_r.message);
                                    }
                                }
                            });
                            // console log for debugging next employee code, current series
                            console.log('Next Employee Code:', r.message);
                            console.log('Current Series:', employee_num);
                        }
                    }
                });

            } else {
                // Store existing value
                window.original_employee_code = frm.doc.employee;
            }

            if (!frm.doc.attendance_device_id) {
                frappe.call({
                    method: 'customize_erpnext.api.employee.employee_utils.get_next_attendance_device_id',
                    callback: function (r) {
                        if (r.message) {
                            frm.set_value('attendance_device_id', r.message);
                        }
                    }
                });
            }
        } else {
            // For existing employees, store current value
            window.original_employee_code = frm.doc.employee;
        }
    },

    employee: function (frm) {
        // Store the employee value whenever it changes
        if (frm.doc.employee && frm.doc.employee.startsWith('TIQN-')) {
            window.original_employee_code = frm.doc.employee;
        }
    },

    before_save: function (frm) {
        // Ensure employee code follows TIQN-XXXX format
        if (frm.doc.employee && !frm.doc.employee.startsWith('TIQN-')) {
            frappe.msgprint(__('Employee code should follow TIQN-XXXX format'));
            frappe.validated = false;
            return;
        }

        // Check for duplicate employee code
        if (frm.doc.employee) {
            frappe.call({
                method: 'customize_erpnext.api.employee.employee_utils.check_duplicate_employee',
                args: {
                    employee_code: frm.doc.employee,
                    current_doc_name: frm.doc.name
                },
                async: false,
                callback: function (r) {
                    if (r.message && r.message.exists) {
                        frappe.msgprint(__('Employee code {0} already exists in the system', [frm.doc.employee]));
                        frappe.validated = false;
                    }
                }
            });
        }

        // Check for duplicate attendance device ID
        if (frm.doc.attendance_device_id) {
            frappe.call({
                method: 'customize_erpnext.api.employee.employee_utils.check_duplicate_attendance_device_id',
                args: {
                    attendance_device_id: frm.doc.attendance_device_id,
                    current_doc_name: frm.doc.name
                },
                async: false,
                callback: function (r) {
                    if (r.message && r.message.exists) {
                        frappe.msgprint(__('Attendance Device ID {0} already exists in the system', [frm.doc.attendance_device_id]));
                        frappe.validated = false;
                    }
                }
            });
        }

        // set employee_name = first_name + " " + midile_name + " " + last_name
        if (frm.doc.first_name && frm.doc.middle_name && frm.doc.last_name) {
            frm.set_value('first_name', toProperCase(frm.doc.first_name));
            frm.set_value('middle_name', toProperCase(frm.doc.middle_name));
            frm.set_value('last_name', toProperCase(frm.doc.last_name));
            frm.set_value('employee_name',
                [frm.doc.first_name, frm.doc.middle_name, frm.doc.last_name].filter(Boolean).join(' ')
            );
        }
        // check if employee_name icluding numbers throw error
        if (frm.doc.employee_name && /\d/.test(frm.doc.employee_name)) {
            frappe.msgprint(__('Employee name should not contain numbers'));
            frappe.validated = false;
        }
    },

    // after_save: function (frm) {
    //     // Restore original employee code if it was changed and rename document
    //     if (window.original_employee_code &&
    //         frm.doc.employee !== window.original_employee_code &&
    //         window.original_employee_code.startsWith('TIQN-')) {

    //         console.log('Employee code changed from', window.original_employee_code, 'to', frm.doc.employee);
    //         console.log('Restoring original employee code and renaming document...');

    //         // First restore the employee field value
    //         frappe.call({
    //             method: 'frappe.client.set_value',
    //             args: {
    //                 doctype: 'Employee',
    //                 name: frm.doc.name,
    //                 fieldname: 'employee',
    //                 value: window.original_employee_code
    //             },
    //             callback: function (r) {
    //                 if (r.message) {
    //                     // If document name doesn't match original employee code, rename it
    //                     if (frm.doc.name !== window.original_employee_code) {
    //                         frappe.call({
    //                             method: 'frappe.rename_doc',
    //                             args: {
    //                                 doctype: 'Employee',
    //                                 old: frm.doc.name,
    //                                 new: window.original_employee_code,
    //                                 merge: false
    //                             },
    //                             callback: function (rename_r) {
    //                                 if (!rename_r.exc) {
    //                                     // Reload the form with the new name
    //                                     frappe.set_route('Form', 'Employee', window.original_employee_code);
    //                                     frappe.show_alert({
    //                                         message: __('Employee code preserved: {0}', [window.original_employee_code]),
    //                                         indicator: 'green'
    //                                     });
    //                                 } else {
    //                                     console.error('Rename failed:', rename_r.exc);
    //                                 }
    //                             }
    //                         });
    //                     } else {
    //                         // Just update the form values
    //                         frm.doc.employee = window.original_employee_code;
    //                         frm.refresh_field('employee');
    //                         frappe.show_alert({
    //                             message: __('Employee code preserved: {0}', [window.original_employee_code]),
    //                             indicator: 'green'
    //                         });
    //                     }
    //                 }
    //             }
    //         });
    //     }
    // }
});
function toProperCase(str) {
    if (!str) return str;

    let result = str.trim().toLowerCase();

    // First, handle regular word boundaries (spaces, punctuation)
    result = result.replace(/\b\w/g, function (char) {
        return char.toUpperCase();
    });

    // Special handling: ensure first non-number character is uppercase
    // This handles cases like "26ss" → "26Ss"
    result = result.replace(/^(\d*)([a-z])/, function (_, numbers, firstLetter) {
        return numbers + firstLetter.toUpperCase();
    });

    return result;
}
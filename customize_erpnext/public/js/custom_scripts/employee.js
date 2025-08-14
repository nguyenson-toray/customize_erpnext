// import apps/customize_erpnext/customize_erpnext/public/js/utilities.js

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
                        }
                    }
                });
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
        }

    },

    before_save: function (frm) {
        // Ensure employee code follows TIQN-XXXX format
        if (frm.doc.employee && !frm.doc.employee.startsWith('TIQN-')) {
            frappe.msgprint(__('Employee code should follow TIQN-XXXX format'));
            frappe.validated = false;
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

        // Ensure document name matches employee field
        if (frm.doc.employee) {
            frm.doc.name = frm.doc.employee;
        }
    }
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
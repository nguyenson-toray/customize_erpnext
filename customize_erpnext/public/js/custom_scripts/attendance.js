frappe.ui.form.on('Attendance', {
    onload: function(frm) {
        // Load and display custom_additional_info (maternity benefit info)
        if (frm.doc.employee && frm.doc.attendance_date && !frm.doc.__islocal) {
            frappe.call({
                method: 'customize_erpnext.overrides.attendance.attendance.get_attendance_custom_additional_info',
                args: {
                    employee: frm.doc.employee,
                    attendance_date: frm.doc.attendance_date
                },
                callback: function(r) {
                    if (r.message) {
                        // Set HTML field value
                        frm.set_df_property('custom_additional_info', 'options', r.message);
                        frm.refresh_field('custom_additional_info');
                    }
                }
            });
        }
    },

    refresh: function(frm) {
        // Add info message about maternity benefit tracking
        if (frm.doc.employee && frm.doc.attendance_date) {
            frm.dashboard.add_comment(__('Maternity benefit information will be loaded automatically'), 'blue', true);
        }
    },

    employee: function(frm) {
        // Load maternity benefit info when employee changes
        if (frm.doc.employee && frm.doc.attendance_date) {
            frm.trigger('load_additional_info');
        }
    },

    attendance_date: function(frm) {
        // Load maternity benefit info when date changes
        if (frm.doc.employee && frm.doc.attendance_date) {
            frm.trigger('load_additional_info');
        }
    },

    load_additional_info: function(frm) {
        // Load maternity benefit information
        if (frm.doc.employee && frm.doc.attendance_date) {
            frappe.call({
                method: 'customize_erpnext.overrides.attendance.attendance.get_attendance_custom_additional_info',
                args: {
                    employee: frm.doc.employee,
                    attendance_date: frm.doc.attendance_date
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_df_property('custom_additional_info', 'options', r.message);
                        frm.refresh_field('custom_additional_info');
                    } else {
                        // Clear field if no maternity benefit
                        frm.set_df_property('custom_additional_info', 'options', '');
                        frm.refresh_field('custom_additional_info');
                    }
                }
            });
        }
    }
});

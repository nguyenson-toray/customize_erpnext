frappe.ui.form.on('Attendance', {
    onload: function (frm) {
        frm.trigger('show_hide_fields');
        // Load and display custom_additional_info (maternity benefit info)
        if (frm.doc.employee && frm.doc.attendance_date && !frm.doc.__islocal) {
            frappe.call({
                method: 'customize_erpnext.overrides.attendance.attendance.get_attendance_custom_additional_info',
                args: {
                    employee: frm.doc.employee,
                    attendance_date: frm.doc.attendance_date
                },
                callback: function (r) {
                    if (r.message) {
                        // Set HTML field value
                        frm.set_df_property('custom_additional_info', 'options', r.message);
                        frm.refresh_field('custom_additional_info');
                    }
                }
            });
        }

    },

    show_hide_fields: function (frm) {
        if (frm.doc.employee && frm.doc.attendance_date && (!frm.doc.leave_application || !frm.doc.working_hours)) {
            frm.set_df_property('custom_actual_working_hours', 'hidden', 1);
        }
        if (!frm.doc.custom_hour_reduction) {
            frm.set_df_property('custom_hour_reduction', 'hidden', 1);
        }
    },

    employee: function (frm) {
        // Load maternity benefit info when employee changes
        if (frm.doc.employee && frm.doc.attendance_date) {
            frm.trigger('load_additional_info');
        }
    },

    attendance_date: function (frm) {
        // Load maternity benefit info when date changes
        if (frm.doc.employee && frm.doc.attendance_date) {
            frm.trigger('load_additional_info');
        }
    },

    load_additional_info: function (frm) {
        // Load maternity benefit information
        if (frm.doc.employee && frm.doc.attendance_date) {
            frappe.call({
                method: 'customize_erpnext.overrides.attendance.attendance.get_attendance_custom_additional_info',
                args: {
                    employee: frm.doc.employee,
                    attendance_date: frm.doc.attendance_date
                },
                callback: function (r) {
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

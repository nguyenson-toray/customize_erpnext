// customize_erpnext/health_check/doctype/health_check/health_check.js

frappe.ui.form.on("Health Check-Up", {
    refresh(frm) {
        // Add custom button to open Web App 
        frm.add_custom_button(__("Open Health Check-Up Management"), () => {
            frappe.set_route("health-check-up-management");
        }, __("Actions"));

        if (frm.doc.start_time_actual && frm.doc.end_time_actual) {
            frm.set_intro('Đã hoàn thành khám sức khỏe', 'blue');
            frm.set_df_property("employee", "read_only", 1);
            frm.set_df_property("hospital_code", "read_only", 1);
            frm.set_df_property("date", "read_only", 1);
        }
    },

    gender(frm) {
        if (frm.doc.gender === 'Female' || frm.doc.gender === 'Nữ') {
            frm.trigger("check_pregnant");
            frm.set_value("gynecological_exam", 1);
            frm.set_df_property("gynecological_exam", "read_only", 0);
        }
        else {
            frm.set_value("gynecological_exam", 0);
            frm.set_df_property("gynecological_exam", "read_only", 1);
        }
    },
    date(frm) {
        // Fetch pregnant status when date & employee changes
        if (frm.doc.date && frm.doc.employee) {
            frm.trigger("check_pregnant");
        }
    },
    pregnant(frm) {
        if (frm.doc.pregnant) {
            frm.set_value("x_ray", 0);
            frm.set_df_property("x_ray", "read_only", 1);
        }
        else {
            frm.set_value("x_ray", 1);
            frm.set_df_property("x_ray", "read_only", 0);
        }
    },
    check_pregnant(frm) {
        // Đang mang thai = ngày khám nằm trong [pregnant_from_date, pregnant_to_date]
        // (pregnant_to_date trống = chưa sinh). Cùng logic với server check_pregnant_status().
        if (frm.is_new() && (frm.doc.gender === "Female" || frm.doc.gender === "Nữ") && frm.doc.employee) {
            frappe.db.get_value("Employee Maternity",
                { employee: frm.doc.employee },
                ["pregnant_from_date", "pregnant_to_date"]
            ).then((r) => {
                const m = r && r.message;
                const checkDate = frm.doc.date || frappe.datetime.get_today();
                const isPregnant = m && m.pregnant_from_date
                    && m.pregnant_from_date <= checkDate
                    && (!m.pregnant_to_date || checkDate <= m.pregnant_to_date);
                frm.set_value("pregnant", isPregnant ? 1 : 0);
            });
        }
    },

});

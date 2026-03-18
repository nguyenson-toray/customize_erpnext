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
        if (frm.doc.gender == 'Female') {
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
        if (frm.is_new() && (frm.doc.gender === "Female")) {
            frappe.db.count("Employee Maternity", [
                ["employee", "=", frm.doc.employee],
                ["type", "=", "Pregnant"],
                ["from_date", "<=", frm.doc.date],
                ["to_date", ">=", frm.doc.date]
            ]).then((count) => {
                frm.set_value("pregnant", count > 0 ? 1 : 0);
            });
        }
    },

});

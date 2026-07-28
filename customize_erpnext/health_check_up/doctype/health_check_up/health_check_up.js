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

    not_check_up(frm) {
        // Tích "Không khám" → status = "Không khám" (hiển thị ngay; server tính lại khi Save).
        // Lý do ghi ở Note.
        if (frm.doc.not_check_up) {
            frm.set_value("status", "Không khám");
            if (!frm.doc.note) {
                frappe.show_alert({ message: __("Nhập lý do không khám vào Note"), indicator: "orange" });
            }
        } else if (frm.doc.status === "Không khám") {
            frm.set_value("status",
                frm.doc.end_time_actual ? "Hoàn thành" : (frm.doc.start_time_actual ? "Đang khám" : "Chưa khám"));
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
        // Lấy theo field 'status' của Employee Maternity (status = "Pregnant") — status này đã
        // được scheduler tự tính lại hàng ngày. Khớp server check_pregnant_status().
        // Chỉ tự điền khi tạo mới; HR vẫn có thể nhập tay ghi đè sau đó.
        if (frm.is_new() && (frm.doc.gender === "Female" || frm.doc.gender === "Nữ") && frm.doc.employee) {
            frappe.db.get_list("Employee Maternity", {
                filters: { employee: frm.doc.employee, status: "Pregnant" },
                fields: ["name"],
                limit: 1
            }).then((rows) => {
                frm.set_value("pregnant", (rows && rows.length) ? 1 : 0);
            });
        }
    },

});

// customize_erpnext/health_check/doctype/health_check/health_check.js

frappe.ui.form.on("Health Check-Up", {
    refresh(frm) {
        // Add custom button to open Web App
        if (!frm.is_new()) {
            frm.add_custom_button(__("Mở Web App"), () => {
                frappe.set_route("health-check-app");
            }, __("Actions"));
        }
    },

    employee(frm) {
        // Fetch pregnant status when employee changes
        if (frm.doc.employee) {
            frm.trigger("check_pregnant");
        }
    },

    check_pregnant(frm) {
        if (frm.is_new() && (frm.doc.gender === "Female" || frm.doc.gender === "Nữ")) {
            frappe.db.count("Employee Maternity", {
                employee: frm.doc.employee,
                type: "Pregnant",
            }).then((count) => {
                frm.set_value("pregnant", count > 0 ? 1 : 0);
            });
        }
    },

});

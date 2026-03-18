// health_check_up_list.js - List View customizations for Health Check-Up

frappe.listview_settings["Health Check-Up"] = {
    onload: function (listview) {
        listview.page.add_menu_item("🧹Clear Actual Time - Only for IT", function () {
            hcAdminDialog({
                title: "Clear Actual Time",
                hasToDate: false,
                onConfirm: function (date) {
                    frappe.call({
                        method: "customize_erpnext.health_check_up.api.health_check_api.clear_actual_times",
                        args: { date: date },
                        freeze: true,
                        freeze_message: "Clearing actual times...",
                        callback: function (r) {
                            if (r.message) {
                                frappe.msgprint(
                                    "Cleared " + r.message.cleared + " of " + r.message.total + " records for " + date,
                                    "Done"
                                );
                                listview.refresh();
                            }
                        }
                    });
                }
            });
        });

        listview.page.add_menu_item("📝Change Date - Only for IT", function () {
            hcAdminDialog({
                title: "Change Date",
                hasToDate: true,
                onConfirm: function (date, toDate) {
                    frappe.call({
                        method: "customize_erpnext.health_check_up.api.health_check_api.change_date",
                        args: { from_date: date, to_date: toDate },
                        freeze: true,
                        freeze_message: "Changing date...",
                        callback: function (r) {
                            if (r.message) {
                                frappe.msgprint(
                                    "Updated " + r.message.updated + " records from " + date + " to " + toDate,
                                    "Done"
                                );
                                listview.refresh();
                            }
                        }
                    });
                }
            });
        });
    }
};

function hcAdminDialog(opts) {
    var todayYMD = frappe.datetime.get_today(); // YYYY-MM-DD
    var expectedPwd = "1111";

    var toDateRow = opts.hasToDate
        ? '<div class="form-group" style="margin-top:10px;">'
        + '<label style="font-size:12px;font-weight:600;">New Date</label>'
        + '<input type="date" id="hc-to-date" class="form-control input-sm" value="' + todayYMD + '" style="margin-top:4px;" />'
        + '</div>'
        : '';

    var fields = [
        {
            fieldtype: "HTML",
            fieldname: "date_section",
            options:
                '<div class="form-group">'
                + '<label style="font-size:12px;font-weight:600;">Date</label>'
                + '<input type="date" id="hc-from-date" class="form-control input-sm" value="' + todayYMD + '" style="margin-top:4px;" />'
                + '</div>'
                + toDateRow
        },
        {
            label: "Password",
            fieldname: "password",
            fieldtype: "Password"
        }
    ];

    var dlg = new frappe.ui.Dialog({
        title: opts.title,
        fields: fields,
        primary_action_label: "Confirm",
        primary_action: function (values) {
            var fromDate = dlg.$body.find("#hc-from-date").val();
            var toDate = opts.hasToDate ? dlg.$body.find("#hc-to-date").val() : null;

            if (!fromDate) {
                frappe.msgprint({ message: "Please select a date.", indicator: "red" });
                return;
            }
            if (opts.hasToDate && !toDate) {
                frappe.msgprint({ message: "Please select a new date.", indicator: "red" });
                return;
            }
            if (!values.password) {
                frappe.msgprint({ message: "Please enter password.", indicator: "red" });
                return;
            }
            if (values.password !== expectedPwd) {
                frappe.msgprint({ message: "Wrong password!", indicator: "red" });
                return;
            }

            dlg.hide();
            opts.onConfirm(fromDate, toDate);
        }
    });

    dlg.show();

    dlg.$wrapper.on("keydown.hc_admin", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            dlg.$wrapper.find(".btn-primary").click();
        }
    });
}

// health_check_up_list.js - List View customizations for Health Check-Up

frappe.listview_settings["Health Check-Up"] = {
    onload: function (listview) {
        listview.page.add_menu_item(__("Clear Actual Time - Only for IT"), function () {
            hcAdminDialog({
                title: __("Clear Actual Time"),
                hasToDate: false,
                onConfirm: function (date) {
                    frappe.call({
                        method: "customize_erpnext.health_check_up.api.health_check_api.clear_actual_times",
                        args: { date: date },
                        freeze: true,
                        freeze_message: __("Clearing actual times..."),
                        callback: function (r) {
                            if (r.message) {
                                frappe.msgprint({
                                    title: __("Done"),
                                    message: __("Cleared {0} of {1} records for {2}", [r.message.cleared, r.message.total, date]),
                                    indicator: "green"
                                });
                                listview.refresh();
                            }
                        }
                    });
                }
            });
        });

        listview.page.add_menu_item(__("Change Date - Only for IT"), function () {
            hcAdminDialog({
                title: __("Change Date"),
                hasToDate: true,
                onConfirm: function (date, toDate) {
                    frappe.call({
                        method: "customize_erpnext.health_check_up.api.health_check_api.change_date",
                        args: { from_date: date, to_date: toDate },
                        freeze: true,
                        freeze_message: __("Changing date..."),
                        callback: function (r) {
                            if (r.message) {
                                frappe.msgprint({
                                    title: __("Done"),
                                    message: __("Updated {0} records from {1} to {2}", [r.message.updated, date, toDate]),
                                    indicator: "green"
                                });
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
    const todayYMD = frappe.datetime.get_today();
    const expectedPwd = "1111";

    const toDateRow = opts.hasToDate ? `
        <div class="form-group" style="margin-top:10px">
            <label class="control-label">${__("New Date")}</label>
            <input type="date" id="hc-to-date" class="form-control input-sm" value="${todayYMD}">
        </div>` : '';

    const fields = [
        {
            fieldtype: "HTML",
            fieldname: "date_section",
            options: `
                <div class="form-group">
                    <label class="control-label">${__("Date")}</label>
                    <input type="date" id="hc-from-date" class="form-control input-sm" value="${todayYMD}">
                </div>
                ${toDateRow}
            `
        },
        {
            label: __("Password"),
            fieldname: "password",
            fieldtype: "Password"
        }
    ];

    const dlg = new frappe.ui.Dialog({
        title: opts.title,
        fields: fields,
        primary_action_label: __("Confirm"),
        primary_action: function (values) {
            const fromDate = dlg.$body.find("#hc-from-date").val();
            const toDate = opts.hasToDate ? dlg.$body.find("#hc-to-date").val() : null;

            if (!fromDate) {
                frappe.msgprint({ message: __("Please select a date."), indicator: "red" });
                return;
            }
            if (opts.hasToDate && !toDate) {
                frappe.msgprint({ message: __("Please select a new date."), indicator: "red" });
                return;
            }
            if (!values.password) {
                frappe.msgprint({ message: __("Please enter password."), indicator: "red" });
                return;
            }
            if (values.password !== expectedPwd) {
                frappe.msgprint({ message: __("Wrong password."), indicator: "red" });
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

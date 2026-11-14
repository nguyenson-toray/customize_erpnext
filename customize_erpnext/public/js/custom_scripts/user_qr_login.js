// QR Login buttons on the User form (System Manager only — see MANAGER_ROLES in api/qr_login.py).
// Enable / Download card / Revoke / Disable — see customize_erpnext/api/qr_login.py
frappe.ui.form.on("User", {
    refresh(frm) {
        if (frm.is_new() || !frm.doc.name) return;
        if (!frappe.user.has_role("System Manager")) return;
        if (frm.doc.user_type !== "System User" || frm.doc.name === "Administrator") return;

        const group = __("QR Login");
        const api = "customize_erpnext.api.qr_login.";
        const version = cint(frm.doc.custom_qr_login_version);

        const run = (method, success) =>
            frappe.call({ method: api + method, args: { user: frm.doc.name }, type: "POST", freeze: true })
                .then(() => {
                    frappe.show_alert({ message: success, indicator: "green" });
                    frm.reload_doc();
                });

        const card_url = "/qr-login-card?user=" + encodeURIComponent(frm.doc.name);
        const print_card = () => window.open(card_url, "_blank");
        // After an async call the browser blocks window.open -> offer a link instead
        const offer_print = () =>
            frappe.msgprint({
                title: __("QR Login"),
                indicator: "green",
                message: `<a class="btn btn-primary" href="${card_url}" target="_blank" rel="noopener">${__("Download card")}</a>`,
            });

        if (version < 1) {
            frm.add_custom_button(__("Enable"), () => {
                run("enable", __("QR login enabled")).then(offer_print);
            }, group);
            return;
        }

        frm.add_custom_button(__("Download card"), print_card, group);
        frm.add_custom_button(__("Revoke"), () => {
            frappe.confirm(
                __("All cards of {0} will stop working. Continue?", [frm.doc.full_name || frm.doc.name]),
                () => run("revoke", __("Old cards revoked. Download the new card.")).then(offer_print)
            );
        }, group);
        frm.add_custom_button(__("Disable"), () => {
            frappe.confirm(
                __("Turn off QR login for {0}?", [frm.doc.full_name || frm.doc.name]),
                () => run("disable", __("QR login disabled"))
            );
        }, group);
    },
});

// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.listview_settings["Employee Onboarding Form"] = {
    add_fields: ["status", "employee_name", "date_of_joining", "employee"],

    get_indicator(doc) {
        const map = {
            "Pending Review": ["Pending Review", "orange"],
            "Approved": ["Approved", "green"],
            "Rejected": ["Rejected", "red"],
            "Synced": ["Synced", "blue"],
        };
        return map[doc.status] || [doc.status, "gray"];
    },

    onload(listview) {
        // ── Approve Selected ──────────────────────────────────────────────────
        listview.page.add_action_item(__("Approve Selected"), () => {
            const checked = listview.get_checked_items();
            if (!checked.length) {
                frappe.msgprint(__("Please select at least one record."));
                return;
            }
            const pending = checked.filter(d => d.status === "Pending Review");
            if (!pending.length) {
                frappe.msgprint(__("None of the selected forms are in Pending Review status."));
                return;
            }
            frappe.confirm(
                __("Approve <b>{0}</b> selected form(s)?", [pending.length]),
                () => {
                    _bulk_approve(pending.map(d => d.name), listview);
                }
            );
        });

        // ── Download Excel ────────────────────────────────────────────────────
        listview.page.add_action_item(__("Download Excel"), () => {
            const checked = listview.get_checked_items();
            const names = checked.length ? JSON.stringify(checked.map(d => d.name)) : null;
            frappe.call({
                method: "customize_erpnext.api.onboarding.onboarding_api.download_onboarding_excel",
                args: { names },
                freeze: true,
                freeze_message: __("Generating Excel..."),
                callback(r) {
                    if (r.message) {
                        const link = document.createElement("a");
                        link.href = `data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${r.message.data}`;
                        link.download = r.message.filename;
                        link.click();
                    }
                },
            });
        });

        // ── Download CCCD Photos (ZIP) ────────────────────────────────────────
        listview.page.add_action_item(__("Download CCCD Photos"), () => {
            const checked = listview.get_checked_items();
            const names = checked.length ? JSON.stringify(checked.map(d => d.name)) : null;
            frappe.call({
                method: "customize_erpnext.api.onboarding.onboarding_api.download_cccd_photos",
                args: { names },
                freeze: true,
                freeze_message: __("Preparing ZIP..."),
                callback(r) {
                    if (r.message && r.message.data) {
                        const link = document.createElement("a");
                        link.href = `data:application/zip;base64,${r.message.data}`;
                        link.download = r.message.filename;
                        link.click();
                    }
                },
            });
        });

        // ── Generate QR Codes ─────────────────────────────────────────────────
        listview.page.add_action_item(__("Generate QR Codes"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Generate Employee QR Codes"),
                fields: [
                    {
                        fieldname: "emp_ids",
                        fieldtype: "Small Text",
                        label: __("Employee IDs (one per line)"),
                        description: __("Leave empty to generate for checked records."),
                    },
                ],
                primary_action_label: __("Generate"),
                primary_action(values) {
                    d.hide();
                    let ids = [];
                    if (values.emp_ids && values.emp_ids.trim()) {
                        ids = values.emp_ids.split("\n").map(s => s.trim()).filter(Boolean);
                    } else {
                        ids = listview.get_checked_items().map(r => r.employee);
                    }
                    if (!ids.length) {
                        frappe.msgprint(__("No employees selected."));
                        return;
                    }
                    _show_qr_grid(ids);
                },
            });
            d.show();
        });
    },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _bulk_approve(names, listview) {
    frappe.call({
        method: "customize_erpnext.api.onboarding.onboarding_api.bulk_approve_onboarding",
        args: { names: JSON.stringify(names) },
        freeze: true,
        freeze_message: __("Approving..."),
        callback(r) {
            if (!r.exc && r.message) {
                const msg = __("Approved {0} form(s). Skipped {1}.", [
                    r.message.approved_count || 0,
                    r.message.skipped_count || 0,
                ]);
                frappe.show_alert({ message: msg, indicator: "green" });
                listview.refresh();
            }
        },
    });
}

function _load_qr_lib(cb) {
    if (window.QRCode) return cb();
    const s = document.createElement("script");
    s.src = "/assets/customize_erpnext/js/qrcode.min.js";
    s.onload = cb;
    s.onerror = () => {
        const s2 = document.createElement("script");
        s2.src = "https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js";
        s2.onload = cb;
        document.head.appendChild(s2);
    };
    document.head.appendChild(s);
}

function _render_qr(container_id, url) {
    _load_qr_lib(() => {
        const el = document.getElementById(container_id);
        if (!el) return;
        el.innerHTML = "";
        new QRCode(el, {
            text: url,
            width: 200,
            height: 200,
            colorDark: "#000000",
            colorLight: "#ffffff",
            correctLevel: QRCode.CorrectLevel.M,
        });
    });
}

function _show_qr_grid(emp_ids) {
    const base = "https://erp.tiqn.com.vn:8888/employee-onboarding";
    let html = `<div style="display:flex;flex-wrap:wrap;gap:20px;justify-content:center;padding:12px">`;
    emp_ids.forEach((id, i) => {
        html += `<div style="text-align:center;border:1px solid #eee;border-radius:8px;padding:12px;width:220px">
			<div id="qr_grid_${i}" style="display:inline-block;margin-bottom:8px"></div>
			<p style="font-weight:600;margin:0 0 4px;font-size:13px">${id}</p>
			<p style="font-size:11px;color:#888;word-break:break-all;margin:0">${base}?emp=${encodeURIComponent(id)}</p>
		</div>`;
    });
    html += `</div>`;

    const d = new frappe.ui.Dialog({
        title: __("QR Codes — {0} Employee(s)", [emp_ids.length]),
        fields: [{ fieldname: "qr_html", fieldtype: "HTML", options: html }],
        secondary_action_label: __("Print"),
        secondary_action() {
            const win = window.open("", "_blank");
            win.document.write(
                `<html><head><title>QR Codes</title></head><body>${html}</body></html>`
            );
            win.document.close();
            setTimeout(() => win.print(), 800);
        },
    });
    d.show();

    setTimeout(() => {
        emp_ids.forEach((id, i) => {
            _render_qr(`qr_grid_${i}`, `${base}?emp=${encodeURIComponent(id)}`);
        });
    }, 200);
}

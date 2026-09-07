// health_check_up_list.js - List View customizations for Health Check-Up

frappe.listview_settings["Health Check-Up"] = {
    // 🔴 PHẢI dùng `formatters`, KHÔNG được dùng `get_indicator`.
    //
    // Khai `get_indicator` làm `frappe.has_indicator()` trả true, và khi đó
    // `list_view.js:446` CỐ Ý GỠ HẲN cột `status` khỏi danh sách cột để thay bằng cột
    // indicator riêng — kết quả là cột Status biến mất khỏi chỗ cũ.
    //
    // `formatters.status` thì tô màu ngay BÊN TRONG cột sẵn có, `has_indicator` vẫn
    // false nên không có gì bị gỡ.
    formatters: {
        status(value) {
            // Bảng màu để TRONG hàm có chủ đích: `*_list.js` nạp thẳng vào global scope của
            // desk, khai `const` ở top-level mà trùng tên với một file list khác là
            // "Identifier has already been declared" và vỡ cả trang list.
            //
            // Màu phải khớp chú giải của trang Health Check Up Management
            // (`health_check_up_management.js`, bảng "Ý nghĩa trạng thái") — cùng một trạng
            // thái mà list một màu, dashboard một màu khác thì rất khó chịu.
            const color = {
                "Chưa khám": "gray",      // chưa có giờ phát thực tế
                "Đang khám": "yellow",    // có giờ phát, chưa có giờ thu
                "Hoàn thành": "green",    // có cả giờ phát và giờ thu
                "Không khám": "orange",   // tích not_check_up, lý do ghi ở Note
            }[value];

            if (!color) return value ? frappe.utils.escape_html(value) : "";
            return `<span class="indicator-pill ${color}">${frappe.utils.escape_html(__(value))}</span>`;
        },
    },

    onload: function (listview) {
        // Upload & auto-assign result files (by file name starting with employee code)
        listview.page.add_inner_button(__("Upload Results"), function () {
            hcUploadResultDialog(listview);
        });

        listview.page.add_menu_item(__("Clear Actual Data - Only for IT"), function () {
            // Chỉ cho chọn trong các ngày ĐÃ CÓ hồ sơ — gõ tự do rất dễ xoá nhầm sang
            // một ngày không tồn tại (API chạy trót lọt, báo "Cleared 0", không ai biết là gõ sai).
            hcWithExamDates(function (dates) {
                hcAdminDialog({
                    title: __("Clear Actual Data"),
                    hasToDate: false,
                    dateOptions: dates,
                    onConfirm: function (date) {
                        frappe.call({
                            method: "customize_erpnext.health_check_up.api.health_check_api.clear_actual_data",
                            args: { date: date },
                            freeze: true,
                            freeze_message: __("Clearing actual data..."),
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
        });

        listview.page.add_menu_item(__("Recalculate Status - Only for IT"), function () {
            hcWithExamDates(function (dates) {
                hcAdminDialog({
                    title: __("Recalculate Status by Date"),
                    hasToDate: false,
                    dateOptions: dates,
                    onConfirm: function (date) {
                        frappe.call({
                            method: "customize_erpnext.health_check_up.api.health_check_api.recalculate_status_by_date",
                            args: { date: date },
                            freeze: true,
                            freeze_message: __("Recalculating status..."),
                            callback: function (r) {
                                if (r.message) {
                                    frappe.msgprint({
                                        title: __("Done"),
                                        message: __("Updated {0} records for {1}", [r.message.updated, date]),
                                        indicator: "green"
                                    });
                                    listview.refresh();
                                }
                            }
                        });
                    }
                });
            });
        });

        listview.page.add_menu_item(__("Change Date - Only for IT"), function () {
            // Chỉ ngày NGUỒN bị khoá theo danh sách. Ngày ĐÍCH ("New Date") vẫn nhập tự do —
            // mục đích của chức năng này là dời hồ sơ sang một ngày CHƯA có, khoá luôn thì hỏng.
            hcWithExamDates(function (dates) {
                hcAdminDialog({
                    title: __("Change Date"),
                    hasToDate: true,
                    dateOptions: dates,
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
        });
    }
};

// Lấy các ngày ĐÃ CÓ hồ sơ khám rồi mới chạy tiếp — dùng cho dialog cần dropdown ngày.
function hcWithExamDates(callback) {
    frappe.call({
        method: "customize_erpnext.health_check_up.api.health_check_api.get_health_check_dates",
        freeze: true,
        callback: function (r) {
            const dates = r.message || [];
            if (!dates.length) {
                frappe.msgprint({ message: __("No exam dates found."), indicator: "orange" });
                return;
            }
            callback(dates);
        }
    });
}

function hcAdminDialog(opts) {
    const todayYMD = frappe.datetime.get_today();
    // Mật khẩu này chỉ là bước chặn thao tác nhầm (UX). Bảo mật thật nằm ở server:
    // các API admin yêu cầu role System Manager (_require_admin trong health_check_api.py).
    const expectedPwd = "1111";

    const toDateRow = opts.hasToDate ? `
        <div class="form-group" style="margin-top:10px">
            <label class="control-label">${__("New Date")}</label>
            <input type="date" id="hc-to-date" class="form-control input-sm" value="${todayYMD}">
        </div>` : '';

    // opts.dateOptions (mảng "YYYY-MM-DD") → dropdown khoá cứng theo ngày đã có hồ sơ.
    // Không truyền thì vẫn là <input type="date"> nhập tự do như cũ.
    const fromDateInput = opts.dateOptions
        ? `<select id="hc-from-date" class="form-control input-sm">
                ${opts.dateOptions.map(d =>
                    `<option value="${frappe.utils.escape_html(d)}"${d === todayYMD ? " selected" : ""}>
                        ${frappe.utils.escape_html(frappe.datetime.str_to_user(d))}
                    </option>`).join("")}
           </select>`
        : `<input type="date" id="hc-from-date" class="form-control input-sm" value="${todayYMD}">`;

    const fields = [
        {
            fieldtype: "HTML",
            fieldname: "date_section",
            options: `
                <div class="form-group">
                    <label class="control-label">${__("Date")}</label>
                    ${fromDateInput}
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

// ===========================================================================
// Upload & auto-assign health check result files
// ===========================================================================
function hcUploadResultDialog(listview) {
    frappe.call({
        method: "customize_erpnext.health_check_up.api.health_check_api.get_health_check_dates",
        callback: function (r) {
            const dates = r.message || [];
            if (!dates.length) {
                frappe.msgprint({ message: __("No exam dates found."), indicator: "orange" });
                return;
            }
            hcShowUploadDialog(listview, dates);
        }
    });
}

function hcShowUploadDialog(listview, dates) {
    const dlg = new frappe.ui.Dialog({
        title: __("Upload Health Check Results"),
        fields: [
            {
                fieldtype: "Select",
                fieldname: "date",
                label: __("Health Check Date"),
                reqd: 1,
                options: dates.join("\n"),
                default: dates[0]
            },
            {
                fieldtype: "HTML",
                fieldname: "files_html",
                options: `
                    <div class="form-group">
                        <label class="control-label">${__("Select result files")}</label>
                        <input type="file" id="hc-result-files" class="form-control input-sm"
                               multiple accept=".pdf,.jpg,.jpeg,.png">
                        <p class="text-muted small" style="margin-top:6px">
                            ${__("File name must START with the employee code. E.g. TIQN-0148_result.pdf or 0148 result.pdf")}
                        </p>
                    </div>`
            }
        ],
        primary_action_label: __("Upload & Assign"),
        primary_action: async function (values) {
            const input = dlg.$body.find("#hc-result-files")[0];
            const files = input && input.files ? Array.from(input.files) : [];
            if (!files.length) {
                frappe.msgprint({ message: __("Please select at least one file."), indicator: "red" });
                return;
            }
            dlg.disable_primary_action();
            const uploaded = [];
            frappe.show_progress(__("Uploading..."), 0, files.length);
            for (let i = 0; i < files.length; i++) {
                try {
                    const res = await hcUploadOneFile(files[i]);
                    if (res && res.file_url) {
                        uploaded.push({ filename: files[i].name, file_url: res.file_url });
                    }
                } catch (e) {
                    // skip failed upload — reported as missing in the summary
                }
                frappe.show_progress(__("Uploading..."), i + 1, files.length);
            }
            frappe.hide_progress();

            if (!uploaded.length) {
                dlg.enable_primary_action();
                frappe.msgprint({ message: __("No file could be uploaded."), indicator: "red" });
                return;
            }

            frappe.call({
                method: "customize_erpnext.health_check_up.api.health_check_api.assign_result_files",
                args: { date: values.date, files: JSON.stringify(uploaded) },
                freeze: true,
                freeze_message: __("Assigning results to records..."),
                callback: function (r) {
                    dlg.hide();
                    const m = r.message || {};
                    let msg = __("Assigned {0} file(s) to records.", [m.assigned_count || 0]);
                    if (m.unmatched && m.unmatched.length) {
                        msg += "<br><br><b>" + __("Not assigned ({0}):", [m.unmatched_count]) + "</b><ul style='margin-top:4px'>";
                        m.unmatched.forEach(function (u) {
                            msg += "<li>" + frappe.utils.escape_html(u.filename || "?") +
                                   " — " + frappe.utils.escape_html(u.reason || "") + "</li>";
                        });
                        msg += "</ul>";
                    }
                    frappe.msgprint({
                        title: __("Result"),
                        message: msg,
                        indicator: (m.unmatched_count ? "orange" : "green")
                    });
                    listview.refresh();
                }
            });
        }
    });
    dlg.show();
}

// Upload one file (private) via Frappe's standard API, returns {file_url, ...}
async function hcUploadOneFile(file) {
    const fd = new FormData();
    fd.append("file", file, file.name);
    fd.append("is_private", 1);
    fd.append("folder", "Home");
    const resp = await fetch("/api/method/upload_file", {
        method: "POST",
        headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
        body: fd
    });
    if (!resp.ok) throw new Error("upload failed " + resp.status);
    const data = await resp.json();
    return data.message;
}

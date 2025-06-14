frappe.ui.form.on('Stock Entry', {
    refresh: function (frm) {
        // Only run this for Material Transfer for Manufacture type
        if (frm.doc.purpose === "Material Transfer for Manufacture" && frm.doc.work_order) {
            check_existing_material_transfers(frm);
        }
    },

    work_order: function (frm) {
        // Check when work order is selected/changed
        if (frm.doc.purpose === "Material Transfer for Manufacture" && frm.doc.work_order) {
            check_existing_material_transfers(frm);
        }
    },

    purpose: function (frm) {
        // Check when purpose is changed to Material Transfer for Manufacture
        if (frm.doc.purpose === "Material Transfer for Manufacture" && frm.doc.work_order) {
            check_existing_material_transfers(frm);
        }
    },

    before_save: function (frm) {
        // Sync invoice fields to child table before saving
        sync_fields_to_child_table(frm);
    }
});

function check_existing_material_transfers(frm) {
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Stock Entry",
            filters: {
                work_order: frm.doc.work_order,
                purpose: "Material Transfer for Manufacture",
                docstatus: ["!=", 2], // Not cancelled
                name: ["!=", frm.doc.name] // Exclude current document
            },
            fields: ["name", "docstatus", "modified", "owner"]
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                // Clear any existing messages first
                frm.dashboard.clear_comment();

                // There are existing material transfers for this work order
                let existing_entries = r.message;
                let warning_html = `
                    <div class="alert alert-warning" style="margin-bottom: 15px;">
                        <h4><i class="fa fa-exclamation-triangle"></i> Cảnh báo: Đã có ${existing_entries.length} phiếu chuyển nguyên liệu cho Work Order này!</h4>
                        <div style="margin-top: 10px;">
                            <table class="table table-bordered table-condensed" style="margin-bottom: 5px;">
                                <thead>
                                    <tr>
                                        <th>Phiếu chuyển kho</th>
                                        <th>Trạng thái</th>
                                        <th>Ngày cập nhật</th>
                                        <th>Người tạo</th>
                                    </tr>
                                </thead>
                                <tbody>`;

                existing_entries.forEach(entry => {
                    let status = "";
                    if (entry.docstatus === 0) {
                        status = '<span class="indicator orange">Bản nháp</span>';
                    } else if (entry.docstatus === 1) {
                        status = '<span class="indicator green">Đã gửi</span>';
                    }

                    warning_html += `
                        <tr>
                            <td><a href="/app/stock-entry/${entry.name}" target="_blank">${entry.name}</a></td>
                            <td>${status}</td>
                            <td>${frappe.datetime.str_to_user(entry.modified)}</td>
                            <td>${entry.owner}</td>
                        </tr>
                    `;
                });

                warning_html += `
                                </tbody>
                            </table>
                            <div style="margin-top: 10px;">
                                <a href="/app/work-order/${frm.doc.work_order}" target="_blank" class="btn btn-sm btn-info">
                                    <i class="fa fa-external-link"></i> Xem Work Order
                                </a>
                                <a href="/app/stock-entry?filters=[['Stock Entry','work_order','=','${frm.doc.work_order}'],['Stock Entry','purpose','=','Material Transfer for Manufacture']]" target="_blank" class="btn btn-sm btn-info">
                                    <i class="fa fa-list"></i> Xem tất cả phiếu chuyển nguyên liệu
                                </a>
                            </div>
                        </div>
                    </div>
                `;

                frm.dashboard.add_comment(warning_html, "blue", true);

                // Check if any entry is submitted
                let has_submitted = existing_entries.some(entry => entry.docstatus === 1);
                if (has_submitted) {
                    frappe.show_alert({
                        message: __('Đã có phiếu chuyển nguyên liệu đã Submit cho Work Order này!'),
                        indicator: 'red'
                    }, 10);
                }
            } else {
                // No existing transfers, show positive confirmation
                frm.dashboard.clear_comment();
                frm.dashboard.add_comment(`
                    <div class="alert alert-info">
                        <i class="fa fa-info-circle"></i> 
                        Chưa có phiếu chuyển nguyên liệu nào cho Work Order này.
                        <div style="margin-top: 10px;">
                            <a href="/app/work-order/${frm.doc.work_order}" target="_blank" class="btn btn-sm btn-info">
                                <i class="fa fa-external-link"></i> Xem Work Order
                            </a>
                        </div>
                    </div>
                `, "blue", true);
            }

            // Show current status
            let status_html = '';
            if (frm.doc.docstatus === 0) {
                status_html = '<span class="indicator orange">Trạng thái hiện tại: Bản nháp</span>';
            } else if (frm.doc.docstatus === 1) {
                status_html = '<span class="indicator green">Trạng thái hiện tại: Đã submit</span>';
            } else if (frm.doc.docstatus === 2) {
                status_html = '<span class="indicator red">Trạng thái hiện tại: Đã hủy</span>';
            }

            frm.dashboard.add_comment(status_html, "blue", true);
        }
    });
}

function sync_fields_to_child_table(frm) {
    if (!frm.doc.items) return;

    let total_updated = 0;
    let fields_to_sync = [
        {
            field: 'custom_declaration_invoice_number',
            value: frm.doc.custom_declaration_invoice_number,
            label: 'Số hóa đơn tờ khai'
        },
        {
            field: 'custom_material_issue_purpose',
            value: frm.doc.custom_material_issue_purpose,
            label: 'Material Issue Purpose'
        },
        {
            field: 'custom_line',
            value: frm.doc.custom_material_issue_purpose,
            label: 'Line'
        },
        {
            field: 'custom_inv_lot',
            value: frm.doc.custom_inv_lot,
            label: 'INV Lot'
        },
        {
            field: 'custom_fg_qty',
            value: frm.doc.custom_fg_qty,
            label: 'Qty FG'
        },
        {
            field: 'custom_fg_style',
            value: frm.doc.custom_fg_style,
            label: 'FG Style'
        },
        {
            field: 'custom_fg_color',
            value: frm.doc.custom_fg_color,
            label: 'FG Color'
        },
        {
            field: 'custom_fg_size',
            value: frm.doc.custom_fg_size,
            label: 'FG Size'
        }
    ];

    fields_to_sync.forEach(function (field_info) {
        if (field_info.value) {
            let updated_count = 0;

            frm.doc.items.forEach(function (row) {
                if (!row[field_info.field]) {
                    frappe.model.set_value(row.doctype, row.name, field_info.field, field_info.value);
                    updated_count++;
                }
            });

            if (updated_count > 0) {
                total_updated += updated_count;
                console.log(`Đã cập nhật ${updated_count} dòng cho ${field_info.label}: ${field_info.value}`);
            }
        }
    });

    if (total_updated > 0) {
        frm.refresh_field('items');
        frappe.show_alert({
            message: __('Đã tự động cập nhật {0} trường trong bảng chi tiết', [total_updated]),
            indicator: 'green'
        }, 5);
    }
}
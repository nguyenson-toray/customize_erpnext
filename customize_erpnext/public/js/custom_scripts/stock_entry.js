frappe.ui.form.on('Stock Entry', {
    onload: function (frm) {
        $(document).on('keydown.duplicate_rows', function (e) {
            // Chỉ hoạt động khi đang focus vào form này
            if (frm.doc.name && frm.doc.doctype === 'Stock Entry') {
                // Ctrl+D để duplicate
                if (e.ctrlKey && e.keyCode === 68) {
                    e.preventDefault();

                    let selected_rows = frm.fields_dict.items.grid.get_selected();
                    if (selected_rows.length > 0) {
                        selected_rows.forEach(function (row_name) {
                            let source_row = locals['Stock Entry Detail'][row_name];
                            let new_row = frm.add_child('items');

                            Object.keys(source_row).forEach(function (field) {
                                if (!['name', 'idx', 'docstatus', 'creation', 'modified', 'owner', 'modified_by'].includes(field)) {
                                    new_row[field] = source_row[field];
                                }
                            });
                        });

                        frm.refresh_field('items');
                        frappe.show_alert(__('Rows duplicated with Ctrl+D'));
                    }
                }
            }
        });
    },

    // Cleanup event khi form bị destroy
    before_load: function (frm) {
        $(document).off('keydown.duplicate_rows');
    },
    refresh: function (frm) {
        // Only run this for Material Transfer for Manufacture type
        if (frm.doc.purpose === "Material Transfer for Manufacture" && frm.doc.work_order) {
            check_existing_material_transfers(frm);
        }

        // Khởi tạo duplicate button (ẩn ban đầu)
        let duplicate_btn = frm.fields_dict.items.grid.add_custom_button(__('Duplicate Selected'),
            function () {
                let selected_rows = frm.fields_dict.items.grid.get_selected();
                if (selected_rows.length === 0) {
                    frappe.msgprint(__('Please select rows to duplicate'));
                    return;
                }

                // LOGIC DUPLICATE THỰC TẾ
                selected_rows.forEach(function (row_name) {
                    // Lấy data từ row được select
                    let source_row = locals['Stock Entry Detail'][row_name];

                    // Tạo row mới
                    let new_row = frm.add_child('items');

                    // Copy tất cả fields trừ system fields
                    Object.keys(source_row).forEach(function (field) {
                        if (!['name', 'idx', 'docstatus', 'creation', 'modified', 'owner', 'modified_by'].includes(field)) {
                            new_row[field] = source_row[field];
                        }
                    });
                });

                // Refresh grid để hiển thị rows mới
                frm.refresh_field('items');

                // Show success message
                frappe.show_alert({
                    message: __(`${selected_rows.length} row(s) duplicated successfully`),
                    indicator: 'green'
                });
            }
        ).addClass('btn-primary').css({
            'background-color': '#6495ED',
            'border-color': '#6495ED',
            'color': '#fff'
        });;

        // Ẩn button ban đầu
        duplicate_btn.hide();

        // Lưu reference để có thể access từ các function khác
        frm.duplicate_btn = duplicate_btn;

        // Setup listener để monitor selection changes
        setup_selection_monitor(frm);

        // THÊM QUICK ADD BUTTON
        let quick_add_btn = frm.fields_dict.items.grid.add_custom_button(__('Quick Add'),
            function () {
                show_quick_add_dialog(frm);
            }
        ).addClass('btn-success').css({
            'background-color': '#5cb85c',
            'border-color': '#4cae4c',
            'color': '#fff'
        });
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

// NEW FUNCTION: Show Quick Add Dialog
function show_quick_add_dialog(frm) {
    let dialog = new frappe.ui.Dialog({
        title: __('Quick Add Items'),
        fields: [
            {
                fieldname: 'items_data',
                fieldtype: 'Small Text',
                label: __('Items Data'),
                description: __(`
                    <div style="background: #f5f5f5; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                        <strong>Định dạng:</strong> item_pattern;custom_inv_lot;qty<br><br>
                        
                        <strong>Cấu trúc item_pattern:</strong><br>
                        item_name<strong>%</strong> color<strong>%</strong> size<strong>%</strong> brand<strong>%</strong> season<strong>%</strong> info<br>
                        <small style="color: #666;">
                        • Dùng dấu % để ngăn cách các thuộc tính<br>
                        • Phải có khoảng trắng sau % và trước giá trị thuộc tính<br>
                        • Bắt buộc: item_name, color, size<br>
                        • Tùy chọn: brand, season, info
                        </small><br><br>
                        
                        <strong>Ví dụ:</strong><br>
                        <code style="background: #fff; padding: 5px; display: block; margin: 5px 0;">
                        LM-2666% 410% Sm% STIO FERNOS% 25fw% 200317;2650281395;52<br>
                        LM-2667% 420% M;2650281396;30<br>
                        LM-2668% 430% L% STIO FERNOS;2650281397;25
                        </code><br>
                        
                        <strong>Giải thích ví dụ 1:</strong><br>
                        • <code>LM-2666</code> → Mã item<br>
                        • <code>% 410</code> → Màu sắc (Color)<br>
                        • <code>% Sm</code> → Kích cỡ (Size)<br>
                        • <code>% STIO FERNOS</code> → Thương hiệu (Brand)<br>
                        • <code>% 25fw</code> → Mùa (Season)<br>
                        • <code>% 200317</code> → Thông tin thêm (Info)<br>
                        • <code>2650281395</code> → Số INV Lot<br>
                        • <code>52</code> → Số lượng<br><br>
                        
                        <strong>Lưu ý:</strong><br>
                        • Mỗi dòng là một item riêng biệt<br>
                        • Hệ thống sẽ tìm item dựa trên custom_item_name_detail<br>
                        • Nếu không tìm thấy item, dòng đó sẽ bị bỏ qua và báo lỗi
                    </div>
                `),
                reqd: 1,
                default: ''
            }
        ],
        size: 'large',
        primary_action_label: __('OK'),
        primary_action: function (values) {
            process_quick_add_items(frm, values.items_data);
            dialog.hide();
        }
    });

    // Set dialog height for better visibility
    dialog.$wrapper.find('.modal-dialog').css('width', '800px');
    dialog.$wrapper.find('[data-fieldname="items_data"]').css('min-height', '200px');

    dialog.show();
}

// NEW FUNCTION: Process Quick Add Items
async function process_quick_add_items(frm, items_data) {
    if (!items_data) return;

    let lines = items_data.split('\n');
    let success_count = 0;
    let error_count = 0;
    let errors = [];
    let items_to_add = [];

    // First pass: validate and prepare data
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        if (!line) continue; // Skip empty lines

        let parts = line.split(';');
        if (parts.length !== 3) {
            errors.push(__('Line {0}: Invalid format. Expected 3 parts separated by semicolon', [i + 1]));
            error_count++;
            continue;
        }

        let item_pattern = parts[0].trim();
        let custom_inv_lot = parts[1].trim();
        let qty = parseFloat(parts[2].trim());

        if (isNaN(qty) || qty <= 0) {
            errors.push(__('Line {0}: Invalid quantity', [i + 1]));
            error_count++;
            continue;
        }

        // Parse item pattern
        let pattern_parts = item_pattern.split('%').map(p => p.trim()).filter(p => p);

        if (pattern_parts.length < 3) {
            errors.push(__('Line {0}: Item pattern must have at least item_name, color, and size', [i + 1]));
            error_count++;
            continue;
        }

        let item_name = pattern_parts[0];
        let color = pattern_parts[1];
        let size = pattern_parts[2];
        let brand = pattern_parts[3] || '';
        let season = pattern_parts[4] || '';
        let info = pattern_parts[5] || '';

        // Build search pattern for custom_item_name_detail
        let search_pattern = item_name;
        if (color) search_pattern += '% ' + color;
        if (size) search_pattern += '% ' + size;
        if (brand) search_pattern += '% ' + brand;
        if (season) search_pattern += '% ' + season;
        if (info) search_pattern += '% ' + info;

        items_to_add.push({
            line_number: i + 1,
            search_pattern: search_pattern,
            custom_inv_lot: custom_inv_lot,
            qty: qty,
            attributes: {
                color: color,
                size: size,
                brand: brand,
                season: season,
                info: info
            }
        });
    }

    // Second pass: find items and add rows sequentially
    for (let item_data of items_to_add) {
        try {
            // Find item
            let response = await frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Item',
                    filters: {
                        'custom_item_name_detail': ['like', item_data.search_pattern]
                    },
                    fields: ['name', 'item_code', 'item_name', 'stock_uom'],
                    limit: 1
                }
            });

            if (response.message && response.message.length > 0) {
                let item = response.message[0];

                // Add new row
                let new_row = frm.add_child('items');

                // Set all values at once to avoid conflicts
                let values_to_set = {
                    'item_code': item.item_code,
                    'custom_inv_lot': item_data.custom_inv_lot,
                    'qty': item_data.qty
                };

                // Add attribute fields
                Object.keys(item_data.attributes).forEach(function (attr) {
                    if (item_data.attributes[attr]) {
                        let field_name = 'custom_' + attr;
                        if (frm.fields_dict.items.grid.fields_map[field_name]) {
                            values_to_set[field_name] = item_data.attributes[attr];
                        }
                    }
                });

                // Set all values
                Object.keys(values_to_set).forEach(function (field) {
                    frappe.model.set_value(new_row.doctype, new_row.name, field, values_to_set[field]);
                });

                success_count++;

                // Small delay between adding items to ensure proper processing
                await new Promise(resolve => setTimeout(resolve, 100));

            } else {
                errors.push(__('Line {0}: Item not found with pattern: {1}', [item_data.line_number, item_data.search_pattern]));
                error_count++;
            }
        } catch (error) {
            errors.push(__('Line {0}: Error processing item: {1}', [item_data.line_number, error.message]));
            error_count++;
        }
    }

    // Refresh grid once after all items are added
    if (success_count > 0) {
        frm.refresh_field('items');
    }

    // Show results
    let message = __('Quick Add completed: {0} items added successfully', [success_count]);

    if (error_count > 0) {
        message += __('<br><br>Errors ({0}):<br>', [error_count]);
        message += errors.join('<br>');

        frappe.msgprint({
            title: __('Quick Add Results'),
            message: message,
            indicator: 'orange'
        });
    } else if (success_count > 0) {
        frappe.show_alert({
            message: message,
            indicator: 'green'
        }, 5);
    }
}

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
            field: 'custom_invoice_number',
            value: frm.doc.custom_invoice_number,
            label: 'Số hóa đơn'
        },
        {
            field: 'custom_material_issue_purpose',
            value: frm.doc.custom_material_issue_purpose,
            label: 'Material Issue Purpose'
        },
        {
            field: 'custom_line',
            value: frm.doc.custom_line,
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

// Function để monitor selection changes
function setup_selection_monitor(frm) {
    // Monitor click events trên grid
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-row-check', function () {
        setTimeout(() => {
            toggle_duplicate_button(frm);
        }, 50); // Small delay để đảm bảo selection đã được update
    });

    // Monitor click trên row (có thể select/deselect)
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-row', function () {
        setTimeout(() => {
            toggle_duplicate_button(frm);
        }, 50);
    });

    // Monitor select all checkbox
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-header-row .grid-row-check', function () {
        setTimeout(() => {
            toggle_duplicate_button(frm);
        }, 50);
    });

    // Monitor keyboard events (Ctrl+A, arrow keys, etc.)
    frm.fields_dict.items.grid.wrapper.on('keyup', function () {
        setTimeout(() => {
            toggle_duplicate_button(frm);
        }, 50);
    });
}

// Function để show/hide duplicate button
function toggle_duplicate_button(frm) {
    if (!frm.duplicate_btn) return;

    let selected_rows = frm.fields_dict.items.grid.get_selected();

    if (selected_rows.length > 0) {
        frm.duplicate_btn.show();
        // Update button text với số lượng selected
        frm.duplicate_btn.text(__(`Duplicate Selected (${selected_rows.length})`));
    } else {
        frm.duplicate_btn.hide();
    }
}
// Duplicate button and Quick Add functionality for Stock Entry
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
    stock_entry_type: function (frm) {
        // THÊM QUICK ADD BUTTONS - Hiển thị theo stock_entry_type
        // Status not submitted
        if (frm.doc.docstatus !== 1) {
            // Remove existing quick add buttons first
            frm.fields_dict.items.grid.grid_buttons.find('.btn').filter(function () {
                return $(this).text().includes('Quick Add');
            }).remove();

            if (frm.doc.stock_entry_type === "Material Issue") {
                let material_issue_quick_add_btn = frm.fields_dict.items.grid.add_custom_button(__('Material Issue - Quick Add'),
                    function () {
                        show_quick_add_dialog(frm, 'material_issue');
                    }
                ).addClass('btn-success').css({
                    'background-color': '#5cb85c',
                    'border-color': '#4cae4c',
                    'color': '#fff'
                });
            }

            if (frm.doc.stock_entry_type === "Material Receipt") {
                let material_receipt_quick_add_btn = frm.fields_dict.items.grid.add_custom_button(__('Material Receipt - Quick Add'),
                    function () {
                        show_quick_add_dialog(frm, 'material_receipt');
                    }
                ).addClass('btn-warning').css({
                    'background-color': '#f0ad4e',
                    'border-color': '#eea236',
                    'color': '#fff'
                });
            }
        }
    },
    refresh: function (frm) {
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
        });

        // Ẩn button ban đầu
        duplicate_btn.hide();

        // Lưu reference để có thể access từ các function khác
        frm.duplicate_btn = duplicate_btn;

        // Setup listener để monitor selection changes
        setup_selection_monitor(frm);
    }
});

// HELPER FUNCTION: Parse Vietnamese number format (comma as decimal separator)
function parseVietnameseFloat(value) {
    if (!value) return 0;

    // Convert to string and trim
    let str = String(value).trim();

    // Replace Vietnamese comma decimal separator with dot
    str = str.replace(',', '.');

    // Parse the number
    let result = parseFloat(str);

    // Return 0 if not a valid number
    return isNaN(result) ? 0 : result;
}

// UPDATED FUNCTION: Show Quick Add Dialog with type parameter
function show_quick_add_dialog(frm, dialog_type) {
    let dialog_config = get_dialog_config(dialog_type);

    let dialog = new frappe.ui.Dialog({
        title: dialog_config.title,
        fields: [
            {
                fieldname: 'items_data',
                fieldtype: 'Small Text',
                label: __('Items Data'),
                description: dialog_config.description,
                reqd: 1,
                default: ''
            }
        ],
        size: 'extra-large',
        primary_action_label: __('OK'),
        primary_action: function (values) {
            process_quick_add_items(frm, values.items_data, dialog_type);
            dialog.hide();
        }
    });

    // Set dialog width and height for full screen visibility
    dialog.$wrapper.find('.modal-dialog').css({
        'width': '95%',
        'max-width': '1200px',
        'height': '90vh'
    });
    dialog.$wrapper.find('.modal-content').css('height', '100%');
    dialog.$wrapper.find('.modal-body').css({
        'height': 'calc(100% - 120px)',
        'overflow-y': 'auto'
    });
    dialog.$wrapper.find('[data-fieldname="items_data"]').css('min-height', '250px');

    dialog.show();
}

// UPDATED FUNCTION: Get dialog configuration based on type with optional fields
function get_dialog_config(dialog_type) {
    if (dialog_type === 'material_issue') {
        return {
            title: __('Quick Add Items - Material Issue'),
            description: __(`
                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; font-size: 13px; line-height: 1.4;">
                    
                    <div style="display: flex; gap: 20px;">
                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📝 Format Options</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                                <strong>1. Simple:</strong> <code>item_pattern</code><br>
                                <strong>2. With Invoice Number:</strong> <code>item_pattern;invoice_number</code><br>
                                <strong>3. Full format:</strong> <code>item_pattern;invoice_number;qty</code><br>
                                <strong>4. Skip Invoice Number:</strong> <code>item_pattern;;qty</code>
                            </div>

                            <h4 style="margin: 0 0 10px 0; color: #333;">🏷️ Item Pattern Structure</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                                <code>item_name<strong>%</strong> color<strong>%</strong> size<strong>%</strong> brand<strong>%</strong> season<strong>%</strong> info</code><br><br>
                                <small style="color: #666;">
                                ✓ Use % to separate attributes<br>
                                ✓ Space after % before value (Xl vs Xxl)<br>
                                ✓ Only item_name is required<br>
                                ✓ Skip empty attributes
                                </small>
                            </div>

                            <h4 style="margin: 0 0 10px 0; color: #333;">⚙️ Default Values</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px;">
                                <strong>invoice_number:</strong> empty<br>
                                <strong>qty:</strong> 1<br>
                                <strong>Number format:</strong> 52,5 or 52.5
                            </div>
                        </div>

                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📋 Examples</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px;">
                                <div style="margin-bottom: 8px;"><code>E79799 Black 20Mm Vital 25Ss</code><br><small style="color: #28a745;">→ qty=1, Invoice Number=empty</small></div>
                                <div style="margin-bottom: 8px;"><code>E79799 Black 20Mm Vital 25Ss;IV01</code><br><small style="color: #28a745;">→ qty=1, Invoice Number=IN01</small></div>
                                <div style="margin-bottom: 8px;"><code>E79799 Black 20Mm Vital 25Ss;IV02;25,75</code><br><small style="color: #28a745;">→ qty=25.75, Invoice Number=IV02</small></div>
                                <div><code>E79799 Black 20Mm Vital 25Ss;;30</code><br><small style="color: #28a745;">→ qty=30, Invoice Number=empty</small></div>
                            </div>
                            
                            <h4 style="margin: 15px 0 10px 0; color: #333;">ℹ️ Notes</h4>
                            <div style="background: #fff3cd; padding: 10px; border-radius: 4px; border-left: 4px solid #ffc107;">
                                <small>
                                • Each line = one item<br>
                                • The system will search for item_pattern in the "Item Name Detail" field of all Items.<br>
                                • Invalid items will be skipped with error report
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            `)
        };
    } else if (dialog_type === 'material_receipt') {
        return {
            title: __('Quick Add Items - Material Receipt'),
            description: __(`
                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; font-size: 13px; line-height: 1.4;">
                    
                    <div style="display: flex; gap: 20px;">
                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📝 Format Options</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                                <strong>1. Simple:</strong> <code>item_pattern</code><br>
                                <strong>2. With invoice:</strong> <code>item_pattern;invoice_number</code><br>
                                <strong>3. Full format:</strong> <code>item_pattern;invoice_number;qty</code><br>
                                <strong>4. Skip invoice:</strong> <code>item_pattern;;qty</code>
                            </div>

                            <h4 style="margin: 0 0 10px 0; color: #333;">🏷️ Item Pattern Structure</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                                <code>item_name<strong>%</strong> color<strong>%</strong> size<strong>%</strong> brand<strong>%</strong> season<strong>%</strong> info</code><br><br>
                                <small style="color: #666;">
                                ✓ Use % to separate attributes<br>
                                ✓ Space after % before value (Xl vs Xxl)<br>
                                ✓ Only item_name is required<br>
                                ✓ Skip empty attributes
                                </small>
                            </div>

                            <h4 style="margin: 0 0 10px 0; color: #333;">⚙️ Default Values</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px;">
                                <strong>invoice_number:</strong> empty<br>
                                <strong>qty:</strong> 1<br>
                                <strong>Number format:</strong> 52,5 or 52.5
                            </div>
                        </div>

                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📋 Examples</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px;">
                                <div style="margin-bottom: 8px;"><code>E79799 Black 20Mm Vital 25Ss</code><br><small style="color: #17a2b8;">→ qty=1, invoice=empty</small></div>
                                <div style="margin-bottom: 8px;"><code>E79799 Black 20Mm Vital 25Ss;IV003</code><br><small style="color: #17a2b8;">→ qty=1, invoice=IV003</small></div>
                                <div style="margin-bottom: 8px;"><code>E79799 Black 20Mm Vital 25Ss;IV005;25,75</code><br><small style="color: #17a2b8;">→ qty=25.75, invoice=IV005</small></div>
                                <div><code>E79799 Black 20Mm Vital 25Ss;;30</code><br><small style="color: #17a2b8;">→ qty=30, invoice=empty</small></div>
                            </div>
                            
                            <h4 style="margin: 15px 0 10px 0; color: #333;">ℹ️ Notes</h4>
                            <div style="background: #fff3cd; padding: 10px; border-radius: 4px; border-left: 4px solid #ffc107;">
                                <small>
                                • Each line = one item<br>
                                • The system will search for item_pattern in the "Item Name Detail" field of all Items.<br>
                                • Invalid items will be skipped with error report
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            `)
        };
    }
}

// UPDATED FUNCTION: Process Quick Add Items with flexible format support
async function process_quick_add_items(frm, items_data, dialog_type) {
    if (!items_data) return;

    let lines = items_data.split('\n');
    let success_count = 0;
    let error_count = 0;
    let errors = [];
    let items_to_add = [];

    // First pass: validate and prepare data based on dialog type
    for (let i = 0; i < lines.length; i++) {
        console.log(`Processing line ${i + 1}: ${lines[i]}`);
        let line = lines[i].trim();
        if (!line) continue; // Skip empty lines

        let parts = line.split(';');
        let item_pattern = parts[0].trim();
        let qty = 1; // Default quantity
        let field_data = {};

        // Check if we have at least the item pattern
        if (!item_pattern) {
            errors.push(__('Line {0}: Item pattern is required', [i + 1]));
            error_count++;
            continue;
        }

        if (dialog_type === 'material_issue') {
            // Handle different format options for material issue
            if (parts.length >= 2 && parts[1].trim() !== '') {
                // Has custom_inv_lot
                field_data.custom_invoice_number = parts[1].trim();
            } else {
                // No custom_inv_lot or empty
                field_data.custom_invoice_number = '';
            }

            if (parts.length >= 3 && parts[2].trim() !== '') {
                // Has quantity
                qty = parseVietnameseFloat(parts[2].trim());
                if (isNaN(qty) || qty <= 0) {
                    errors.push(__('Line {0}: Invalid quantity: {1}', [i + 1, parts[2]]));
                    error_count++;
                    continue;
                }
            }
        } else if (dialog_type === 'material_receipt') {
            // Handle different format options for material receipt
            if (parts.length >= 2 && parts[1].trim() !== '') {
                // Has custom_invoice_number
                field_data.custom_invoice_number = parts[1].trim();
            } else {
                // No custom_invoice_number or empty
                field_data.custom_invoice_number = '';
            }

            if (parts.length >= 3 && parts[2].trim() !== '') {
                // Has quantity
                qty = parseVietnameseFloat(parts[2].trim());
                if (isNaN(qty) || qty <= 0) {
                    errors.push(__('Line {0}: Invalid quantity: {1}', [i + 1, parts[2]]));
                    error_count++;
                    continue;
                }
            }
        }

        // Parse item pattern
        let pattern_parts = item_pattern.split('%').map(p => p.trim()).filter(p => p);

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

        search_pattern += '%';

        items_to_add.push({
            line_number: i + 1,
            search_pattern: search_pattern,
            field_data: field_data,
            qty: qty
        });
    }

    // Second pass: find items and add rows sequentially
    let count = 0;
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
                count++;
                console.log(`Processing item: ${count} ${item.item_code} for pattern: ${item_data.search_pattern}, qty: ${item_data.qty}`);

                // Add new row
                let new_row = frm.add_child('items');

                // Set basic item values
                let values_to_set = {
                    'item_code': item.item_code,
                    'qty': item_data.qty
                };

                // Add type-specific fields
                Object.assign(values_to_set, item_data.field_data);

                // Set all values
                Object.keys(values_to_set).forEach(function (field) {
                    frappe.model.set_value(new_row.doctype, new_row.name, field, values_to_set[field]);
                });

                success_count++;

                // Small delay between adding items to ensure proper processing
                await new Promise(resolve => setTimeout(resolve, 180));

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
    let type_label = dialog_type === 'material_issue' ? 'Material Issue' : 'Material Receipt';
    let message = __('Quick Add {0} completed: {1} items added successfully', [type_label, success_count]);

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
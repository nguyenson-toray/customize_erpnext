// Client Script for Stock Reconciliation - Quick Add functionality
// Purpose: Add Quick Add button for Opening Stock purpose with custom format
// Format: item_pattern;invoice_number;qty;receive_date
// Updated: Added validation and better handling for custom_receive_date

frappe.ui.form.on('Stock Reconciliation', {
    onload: function (frm) {
        // Setup keyboard shortcuts for duplicate functionality
        $(document).on('keydown.duplicate_rows_sr', function (e) {
            // Only work when focused on this form
            if (frm.doc.name && frm.doc.doctype === 'Stock Reconciliation') {
                // Ctrl+D to duplicate
                if (e.ctrlKey && e.keyCode === 68) {
                    e.preventDefault();

                    let selected_rows = frm.fields_dict.items.grid.get_selected();
                    if (selected_rows.length > 0) {
                        selected_rows.forEach(function (row_name) {
                            let source_row = locals['Stock Reconciliation Item'][row_name];
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

    // Cleanup event when form is destroyed
    before_load: function (frm) {
        $(document).off('keydown.duplicate_rows_sr');
    },

    purpose: function (frm) {
        // Add Quick Add button only for Opening Stock purpose
        // Status not submitted
        if (frm.doc.docstatus !== 1) {
            // Remove existing quick add buttons first
            frm.fields_dict.items.grid.grid_buttons.find('.btn').filter(function () {
                return $(this).text().includes('Quick Add');
            }).remove();

            if (frm.doc.purpose === "Opening Stock") {
                let opening_stock_quick_add_btn = frm.fields_dict.items.grid.add_custom_button(__('Opening Stock - Quick Add'),
                    function () {
                        show_quick_add_dialog_sr(frm, 'opening_stock');
                    }
                ).addClass('btn-info').css({
                    'background-color': '#17a2b8',
                    'border-color': '#138496',
                    'color': '#fff'
                });
            }
        }
    },

    refresh: function (frm) {
        // Initialize duplicate button (hidden initially)
        let duplicate_btn = frm.fields_dict.items.grid.add_custom_button(__('Duplicate Selected'),
            function () {
                let selected_rows = frm.fields_dict.items.grid.get_selected();
                if (selected_rows.length === 0) {
                    frappe.msgprint(__('Please select rows to duplicate'));
                    return;
                }

                // Actual duplicate logic
                selected_rows.forEach(function (row_name) {
                    // Get data from selected row
                    let source_row = locals['Stock Reconciliation Item'][row_name];

                    // Create new row
                    let new_row = frm.add_child('items');

                    // Copy all fields except system fields
                    Object.keys(source_row).forEach(function (field) {
                        if (!['name', 'idx', 'docstatus', 'creation', 'modified', 'owner', 'modified_by'].includes(field)) {
                            new_row[field] = source_row[field];
                        }
                    });
                });

                // Refresh grid to show new rows
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

        // Hide button initially
        duplicate_btn.hide();

        // Save reference for access from other functions
        frm.duplicate_btn = duplicate_btn;

        // Setup listener to monitor selection changes
        setup_selection_monitor_sr(frm);

        // Trigger purpose event to show Quick Add if applicable
        if (frm.doc.purpose === "Opening Stock" && frm.doc.docstatus !== 1) {
            frm.trigger('purpose');
        }
    },

    // Validate before submit to ensure custom fields are properly set
    before_submit: function (frm) {
        // Validate custom_receive_date format in all items
        let validation_errors = [];

        frm.doc.items.forEach(function (item, index) {
            if (item.custom_receive_date) {
                // Validate date format
                let date_obj = new Date(item.custom_receive_date);
                if (isNaN(date_obj.getTime())) {
                    validation_errors.push(__('Row {0}: Invalid receive date format', [index + 1]));
                }
            }
        });

        if (validation_errors.length > 0) {
            frappe.msgprint({
                title: __('Validation Errors'),
                message: validation_errors.join('<br>'),
                indicator: 'red'
            });
            frappe.validated = false;
            return false;
        }

        frappe.validated = true;
    }
});

// Event handlers for individual child table row changes
frappe.ui.form.on('Stock Reconciliation Item', {
    custom_invoice_number: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Trim the field when user moves out of the field
        if (row.custom_invoice_number && typeof row.custom_invoice_number === 'string') {
            let trimmed_value = row.custom_invoice_number.trim();

            if (row.custom_invoice_number !== trimmed_value) {
                frappe.model.set_value(cdt, cdn, 'custom_invoice_number', trimmed_value);
            }
        }
    },

    custom_receive_date: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Validate date format when user changes the date
        if (row.custom_receive_date) {
            let date_obj = new Date(row.custom_receive_date);
            if (isNaN(date_obj.getTime())) {
                frappe.msgprint({
                    title: __('Invalid Date'),
                    message: __('Please enter a valid date in the receive date field'),
                    indicator: 'red'
                });
                frappe.model.set_value(cdt, cdn, 'custom_receive_date', '');
                return;
            }

            // Format the date to ensure consistency (YYYY-MM-DD)
            let formatted_date = date_obj.getFullYear() + '-' +
                String(date_obj.getMonth() + 1).padStart(2, '0') + '-' +
                String(date_obj.getDate()).padStart(2, '0');

            if (row.custom_receive_date !== formatted_date) {
                frappe.model.set_value(cdt, cdn, 'custom_receive_date', formatted_date);
            }
        }
    },

    item_code: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (row.item_code) {
            // Fetch item details including default warehouse
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Item',
                    name: row.item_code
                },
                callback: function (r) {
                    if (r.message) {
                        // Check for default warehouse in item defaults
                        if (r.message.item_defaults && r.message.item_defaults.length > 0) {
                            // Find default warehouse for current company
                            let default_warehouse = null;
                            for (let item_default of r.message.item_defaults) {
                                if (item_default.company === frm.doc.company && item_default.default_warehouse) {
                                    default_warehouse = item_default.default_warehouse;
                                    break;
                                }
                            }

                            if (default_warehouse) {
                                frappe.model.set_value(cdt, cdn, 'warehouse', default_warehouse);
                            }
                        }
                    }
                }
            });
        }
    }
});

// HELPER FUNCTION: Parse Vietnamese number format (comma as decimal separator)
function parseVietnameseFloat_sr(value) {
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

// HELPER FUNCTION: Parse date in various formats with enhanced validation
function parseDate_sr(dateStr) {
    if (!dateStr) return null;

    dateStr = dateStr.trim();

    // Try different date formats
    let date = null;

    // Format: DD/MM/YYYY
    if (dateStr.match(/^\d{1,2}\/\d{1,2}\/\d{4}$/)) {
        let parts = dateStr.split('/');
        let day = parseInt(parts[0], 10);
        let month = parseInt(parts[1], 10);
        let year = parseInt(parts[2], 10);

        // Validate ranges
        if (day >= 1 && day <= 31 && month >= 1 && month <= 12 && year >= 1900 && year <= 2100) {
            date = new Date(year, month - 1, day);
        }
    }
    // Format: DD-MM-YYYY
    else if (dateStr.match(/^\d{1,2}-\d{1,2}-\d{4}$/)) {
        let parts = dateStr.split('-');
        let day = parseInt(parts[0], 10);
        let month = parseInt(parts[1], 10);
        let year = parseInt(parts[2], 10);

        // Validate ranges
        if (day >= 1 && day <= 31 && month >= 1 && month <= 12 && year >= 1900 && year <= 2100) {
            date = new Date(year, month - 1, day);
        }
    }
    // Format: YYYY-MM-DD
    else if (dateStr.match(/^\d{4}-\d{1,2}-\d{1,2}$/)) {
        date = new Date(dateStr);
    }

    // Check if date is valid and not in the future
    if (date && !isNaN(date.getTime())) {
        // Check if date is not too far in the future (max 1 year ahead)
        let maxDate = new Date();
        maxDate.setFullYear(maxDate.getFullYear() + 1);

        if (date <= maxDate) {
            // Return in YYYY-MM-DD format
            return date.getFullYear() + '-' +
                String(date.getMonth() + 1).padStart(2, '0') + '-' +
                String(date.getDate()).padStart(2, '0');
        }
    }

    return null;
}

// FUNCTION: Show Quick Add Dialog for Stock Reconciliation
function show_quick_add_dialog_sr(frm, dialog_type) {
    let dialog_config = get_dialog_config_sr(dialog_type);

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
            process_quick_add_items_sr(frm, values.items_data, dialog_type);
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

// FUNCTION: Get dialog configuration for Opening Stock
function get_dialog_config_sr(dialog_type) {
    if (dialog_type === 'opening_stock') {
        return {
            title: __('Quick Add Items - Opening Stock'),
            description: __(`
                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; font-size: 13px; line-height: 1.4;">
                    
                    <div style="display: flex; gap: 20px;">
                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📝 Format Options</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                                <strong>1. Simple:</strong> <code>item_pattern</code><br>
                                <strong>2. With invoice:</strong> <code>item_pattern;invoice_number</code><br>
                                <strong>3. With qty:</strong> <code>item_pattern;invoice_number;qty</code><br>
                                <strong>4. Full format:</strong> <code>item_pattern;invoice_number;qty;receive_date</code><br>
                                <strong>5. Skip fields:</strong> <code>item_pattern;;qty;receive_date</code>
                            </div>

                            <h4 style="margin: 0 0 10px 0; color: #333;">🏷️ Item Pattern Structure</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                                <code>item_name<strong>%</strong> color<strong>%</strong> size<strong>%</strong> brand<strong>%</strong> season<strong>%</strong> info</code><br><br>
                                <small style="color: #666;">
                                ✓ Use % to separate attributes<br>
                                ✓ Must have space after % and before attribute value (To avoid confusion between ""Xl"" & ""Xxl"")<br>
                                ✓ Only item_name is required<br>
                                ✓ Skip empty attributes
                                </small>
                            </div>

                            <h4 style="margin: 0 0 10px 0; color: #333;">⚙️ Default Values</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px;">
                                <strong>invoice_number:</strong> empty<br>
                                <strong>qty:</strong> 1<br>
                                <strong>receive_date:</strong> empty<br>
                                <strong>Number format:</strong> 52,5 or 52.5<br>
                                <strong>Date format:</strong> DD/MM/YYYY, DD-MM-YYYY, or YYYY-MM-DD<br>
                                <strong>Date validation:</strong> Max 1 year in future
                            </div>
                        </div>

                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📋 Examples</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px;">
                                <div style="margin-bottom: 8px;"><code>E79799 Black 20Mm Vital 25Ss</code><br><small style="color: #17a2b8;">→ qty=1, invoice=empty, date=empty</small></div>
                                <div style="margin-bottom: 8px;"><code>E79799 Black 20Mm Vital 25Ss;IV003</code><br><small style="color: #17a2b8;">→ qty=1, invoice=IV003, date=empty</small></div>
                                <div style="margin-bottom: 8px;"><code>E79799 Black 20Mm Vital 25Ss;IV005;25,75</code><br><small style="color: #17a2b8;">→ qty=25.75, invoice=IV005, date=empty</small></div>
                                <div style="margin-bottom: 8px;"><code>E79799 Black 20Mm Vital 25Ss;IV007;30;15/06/2024</code><br><small style="color: #17a2b8;">→ qty=30, invoice=IV007, date=15/06/2024</small></div>
                                <div><code>E79799 Black 20Mm Vital 25Ss;;45;2024-06-20</code><br><small style="color: #17a2b8;">→ qty=45, invoice=empty, date=2024-06-20</small></div>
                            </div>
                            
                            <h4 style="margin: 15px 0 10px 0; color: #333;">ℹ️ Notes</h4>
                            <div style="background: #fff3cd; padding: 10px; border-radius: 4px; border-left: 4px solid #ffc107;">
                                <small>
                                • Each line = one item<br>
                                • The system will search for item_pattern in the "Item Name Detail" field of all Items.<br>
                                • Invalid items will be skipped with error report<br>
                                • Date formats: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD<br>
                                • Receive date will be saved to Stock Ledger Entry
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            `)
        };
    }
}

// FUNCTION: Process Quick Add Items for Stock Reconciliation
async function process_quick_add_items_sr(frm, items_data, dialog_type) {
    if (!items_data) return;

    let lines = items_data.split('\n');
    let success_count = 0;
    let error_count = 0;
    let errors = [];
    let items_to_add = [];

    // First pass: validate and prepare data
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

        // Process invoice_number (parts[1])
        if (parts.length >= 2 && parts[1].trim() !== '') {
            field_data.custom_invoice_number = parts[1].trim();
        } else {
            field_data.custom_invoice_number = '';
        }

        // Process quantity (parts[2])
        if (parts.length >= 3 && parts[2].trim() !== '') {
            qty = parseVietnameseFloat_sr(parts[2].trim());
            if (isNaN(qty) || qty <= 0) {
                errors.push(__('Line {0}: Invalid quantity: {1}', [i + 1, parts[2]]));
                error_count++;
                continue;
            }
        }

        // Process receive_date (parts[3]) with enhanced validation
        if (parts.length >= 4 && parts[3].trim() !== '') {
            let parsed_date = parseDate_sr(parts[3].trim());
            if (parsed_date) {
                field_data.custom_receive_date = parsed_date;
            } else {
                errors.push(__('Line {0}: Invalid date format: {1}. Use DD/MM/YYYY, DD-MM-YYYY, or YYYY-MM-DD (max 1 year in future)', [i + 1, parts[3]]));
                error_count++;
                continue;
            }
        } else {
            field_data.custom_receive_date = '';
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
                console.log(`Processing item: ${count} ${item.item_code} for pattern: ${item_data.search_pattern}, qty: ${item_data.qty}, receive_date: ${item_data.field_data.custom_receive_date || 'empty'}`);

                // Get full item details including warehouse defaults
                let item_response = await frappe.call({
                    method: 'frappe.client.get',
                    args: {
                        doctype: 'Item',
                        name: item.item_code
                    }
                });

                let default_warehouse = null;
                if (item_response.message && item_response.message.item_defaults) {
                    // Find default warehouse for current company
                    for (let item_default of item_response.message.item_defaults) {
                        if (item_default.company === frm.doc.company && item_default.default_warehouse) {
                            default_warehouse = item_default.default_warehouse;
                            break;
                        }
                    }
                }

                // Add new row
                let new_row = frm.add_child('items');

                // Set basic item values
                let values_to_set = {
                    'item_code': item.item_code,
                    'qty': item_data.qty
                };

                // Add default warehouse if available
                if (default_warehouse) {
                    values_to_set.warehouse = default_warehouse;
                }

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
    let message = __('Quick Add Opening Stock completed: {0} items added successfully', [success_count]);

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

// Function to monitor selection changes
function setup_selection_monitor_sr(frm) {
    // Monitor click events on grid
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-row-check', function () {
        setTimeout(() => {
            toggle_duplicate_button_sr(frm);
        }, 50); // Small delay to ensure selection has been updated
    });

    // Monitor click on row (can select/deselect)
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-row', function () {
        setTimeout(() => {
            toggle_duplicate_button_sr(frm);
        }, 50);
    });

    // Monitor select all checkbox
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-header-row .grid-row-check', function () {
        setTimeout(() => {
            toggle_duplicate_button_sr(frm);
        }, 50);
    });

    // Monitor keyboard events (Ctrl+A, arrow keys, etc.)
    frm.fields_dict.items.grid.wrapper.on('keyup', function () {
        setTimeout(() => {
            toggle_duplicate_button_sr(frm);
        }, 50);
    });
}

// Function to show/hide duplicate button
function toggle_duplicate_button_sr(frm) {
    if (!frm.duplicate_btn) return;

    let selected_rows = frm.fields_dict.items.grid.get_selected();

    if (selected_rows.length > 0) {
        frm.duplicate_btn.show();
        // Update button text with selected count
        frm.duplicate_btn.text(__(`Duplicate Selected (${selected_rows.length})`));
    } else {
        frm.duplicate_btn.hide();
    }
}
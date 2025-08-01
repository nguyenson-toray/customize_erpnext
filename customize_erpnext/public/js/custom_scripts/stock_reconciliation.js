// Constants
const max_line_quick_add = 3000;

// Client Script for Stock Reconciliation - Quick Add functionality
// Purpose: Add Quick Add button for Opening Stock purpose with custom format
// Format: item_name_detail;invoice_number;qty;receive_date
// Updated: Progress dialog, button states, max 100 lines limit

frappe.ui.form.on('Stock Reconciliation', {
    onload: function (frm) {
        frm.set_intro(__('Trường hợp trùng Item nhưng khác Invoice : Chỉ nhập 1 invoice, còn lại chuyển sang Stopk Entry - Material Receipt & chọn "Is Opening Stock"', 'blue'));
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
    validate: function (frm) {
        // remove empty items from items table
        frm.doc.items = frm.doc.items.filter(item => item.item_code && item.item_code.trim() !== '');
        frappe.show_alert({
            message: __('Empty items have been removed from the items table.'),
            indicator: 'green'
        });

    },
    purpose: function (frm) {
        // Update Quick Add button state when purpose changes
        if (frm.opening_stock_quick_add_btn) {
            update_quick_add_button_state_sr(frm, frm.opening_stock_quick_add_btn);
        }

        // Update duplicate button state as well
        toggle_duplicate_button_sr(frm);
        initialize_quick_add_button_sr(frm);

        // Set default date and time for Opening Stock purpose
        if (frm.doc.purpose === 'Opening Stock') {
            frm.set_value('posting_time', '00:00:00');
            frm.set_df_property('posting_time', 'read_only', 1);
        } else {
            frm.toggle_display('posting_time', 1);
            frm.set_df_property('posting_time', 'read_only', 0);
            frm.set_df_property('posting_date', 'read_only', 0);
        }
    },
    set_posting_time: function (frm) {
        // Set default date and time for Opening Stock purpose
        if (frm.doc.purpose === 'Opening Stock' && frm.doc.set_posting_time) {
            frm.set_value('posting_time', '00:00:00');
            frm.set_df_property('posting_time', 'read_only', 1);
        } else {
            frm.toggle_display('posting_time', 1);
            frm.set_df_property('posting_time', 'read_only', 0);
            frm.set_df_property('posting_date', 'read_only', 0);
        }
    },

    refresh: function (frm) {
        // Setup listener to monitor selection changes
        setup_selection_monitor_sr(frm);

        // Always add Quick Add button (but handle disabled state)
        if (!frm.quick_add_btn_added) {
            let opening_stock_quick_add_btn = frm.add_custom_button(__('Opening Stock - Quick Add'),
                function () {
                    // Check if button should be disabled
                    let is_disabled = frm.doc.purpose !== "Opening Stock" || frm.doc.docstatus === 1;

                    if (is_disabled) {
                        // Show appropriate message based on condition
                        if (frm.doc.docstatus === 1) {
                            frappe.msgprint({
                                title: __('Document Submitted'),
                                message: __('Cannot add items to a submitted Stock Reconciliation'),
                                indicator: 'red'
                            });
                        } else if (frm.doc.purpose !== "Opening Stock") {
                            frappe.msgprint({
                                title: __('Invalid Purpose'),
                                message: __('Quick Add is only available for Opening Stock purpose.<br>Current purpose: <strong>{0}</strong><br><br>Please change the purpose to "Opening Stock" to use this feature.', [frm.doc.purpose || 'Not Set']),
                                indicator: 'orange'
                            });
                        }
                        return;
                    }

                    // Proceed with Quick Add dialog
                    show_quick_add_dialog_sr(frm, 'opening_stock');
                }
            );

            // Update button styling based on state
            update_quick_add_button_state_sr(frm, opening_stock_quick_add_btn);

            // Save reference to button
            frm.opening_stock_quick_add_btn = opening_stock_quick_add_btn;

            // Mark that Quick Add button has been added
            frm.quick_add_btn_added = true;
        } else {
            // Update existing button state
            if (frm.opening_stock_quick_add_btn) {
                update_quick_add_button_state_sr(frm, frm.opening_stock_quick_add_btn);
            }
        }

        initialize_quick_add_button_sr(frm);
    },

    // Validate before submit to ensure custom fields are properly set
    before_submit: function (frm) {
        let validation_errors = [];
        frm.doc.items.forEach(function (item, index) {
            if (item.custom_receive_date) {
                // Validate date format
                let date_obj = new Date(item.custom_receive_date);
                if (isNaN(date_obj.getTime())) {
                    validation_errors.push(__('Row {0}: Invalid receive date format', [index + 1]));
                }
            } else {
                validation_errors.push(__('Row {0}: Receive date cannot be empty', [index + 1]));
            }
            if (!item.custom_invoice_number) {
                validation_errors.push(__('Row {0}: Invoice number cannot be empty', [index + 1]));
            }
            if (!item.qty || item.qty <= 0) {
                validation_errors.push(__('Row {0}: Quantity cannot be empty or zero', [index + 1]));
            }
        });

        if (validation_errors.length > 0) {
            frappe.throw(validation_errors.join('<br>'));
            frappe.validated = false;
        }
    },

    // Update button states when document status changes
    after_save: function (frm) {
        setTimeout(() => {
            initialize_quick_add_button_sr(frm);
            // Update button states after save (docstatus might have changed)
            if (frm.opening_stock_quick_add_btn) {
                update_quick_add_button_state_sr(frm, frm.opening_stock_quick_add_btn);
            }
            toggle_duplicate_button_sr(frm);
        }, 300);
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
            // Validate line count
            if (!values.items_data) {
                frappe.msgprint({
                    title: __('No Data'),
                    message: __('Please enter items data'),
                    indicator: 'red'
                });
                return;
            }

            let lines = values.items_data.split('\n').filter(line => line.trim());
            if (lines.length > max_line_quick_add) {
                frappe.msgprint({
                    title: __('Too Many Lines'),
                    message: __('Maximum {0} lines allowed per Quick Add operation.<br>Current lines: <strong>{1}</strong><br><br>Please split your data into smaller batches.', [max_line_quick_add, lines.length]),
                    indicator: 'red'
                });
                return;
            }

            if (lines.length === 0) {
                frappe.msgprint({
                    title: __('No Valid Lines'),
                    message: __('Please enter at least one valid line of data'),
                    indicator: 'red'
                });
                return;
            }

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
            title: __('Quick Add Items - Opening Stock (Max {0} lines)', [max_line_quick_add]),
            description: __(`
                <div style="background: #f8f9fa; padding: 15px; border-radius: 12px; font-size: 13px; line-height: 1.4;">
                    
                    <div style="display: flex; gap: 20px;">
                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📝 Format Options</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                                <strong>1. Full format:</strong> <code>item_name_detail; invoice_number; qty; receive_date; [customs_declaration_number]</code><br>
                                <strong>2. With invoice:</strong> <code>item_name_detail; invoice_number; [customs_declaration_number]</code><br>
                                <strong>3. With qty:</strong> <code>item_name_detail; invoice_number; qty; [customs_declaration_number]</code><br>
                                <strong>4. Skip fields:</strong> <code>item_name_detail; ; qty; receive_date; [customs_declaration_number]</code><br>
                                <strong>5. Simple:</strong> <code>item_name_detail; [customs_declaration_number]</code><br>
                            </div>


                            <h4 style="margin: 0 0 10px 0; color: #333;">⚙️ Default Values</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px;">
                                <strong>invoice_number:</strong> empty<br>
                                <strong>qty:</strong> 1<br>
                                <strong>receive_date:</strong> empty<br>
                                <strong>customs_declaration_number:</strong> empty (optional)<br>
                                <strong>Number format:</strong> 52,5 or 52.5<br>
                                <strong>Date format:</strong> DD/MM/YYYY, DD-MM-YYYY, or YYYY-MM-DD<br>
                                <strong>Date validation:</strong> Max 1 year in future
                            </div>
                        </div>

                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📋 Examples</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px;">
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss; IV007; 30; 15/06/2024; TK001</code><br><small style="color: #17a2b8;">→ qty=30, invoice=IV007, date=15/06/2024, customs=TK001</small></div>
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss; IV003; ; ; TK002</code><br><small style="color: #17a2b8;">→ qty=1, invoice=IV003, date=empty, customs=TK002</small></div>
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss; IV007; 30; 15/06/2024</code><br><small style="color: #17a2b8;">→ qty=30, invoice=IV007, date=15/06/2024, customs=empty</small></div>
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss; IV005; 25,75</code><br><small style="color: #17a2b8;">→ qty=25.75, invoice=IV005, date=empty, customs=empty</small></div>
                                <div><code>E79799 Black 20Mm Vital 25Ss</code><br><small style="color: #17a2b8;">→ qty=1, invoice=empty, date=empty, customs=empty</small></div>
                            </div>
                            
                            <h4 style="margin: 15px 0 10px 0; color: #333;">ℹ️ Notes</h4>
                            <div style="background: #fff3cd; padding: 10px; border-radius: 4px; border-left: 4px solid #ffc107;">
                                <small>
                                • Each line = one item<br>
                                • The system will search for item_name_detail in the "Item Name Detail" field of all Items.<br>
                                • Invalid items will be skipped with error report<br> 
                                • Receive date will be saved to Stock Ledger Entry<br>
                                • customs_declaration_number is optional - can be included or omitted
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            `)
        };
    }
}

// FUNCTION: Process Quick Add Items for Stock Reconciliation - Optimized Version with Progress Dialog
async function process_quick_add_items_sr(frm, items_data, dialog_type) {
    if (!items_data) return;

    // Create progress dialog with simplified structure
    let progress_dialog = new frappe.ui.Dialog({
        title: __('Processing Quick Add Items'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'progress_content'
            }
        ],
        size: 'small',
        static: true  // Prevent closing by clicking outside
    });

    // Show dialog first
    progress_dialog.show();

    // Set HTML content after dialog is shown
    setTimeout(() => {
        let progress_wrapper = progress_dialog.fields_dict.progress_content.$wrapper;
        progress_wrapper.html(`
            <div style="text-align: center; padding: 30px 20px;">
                <div style="width: 100%; background-color: #e9ecef; border-radius: 10px; margin: 20px 0; height: 25px; overflow: hidden;">
                    <div id="progress_bar_sr" style="width: 0%; height: 100%; background: linear-gradient(90deg, #17a2b8, #20c997); transition: width 0.5s ease; border-radius: 10px;"></div>
                </div>
                <div id="progress_text_sr" style="font-size: 16px; font-weight: 500; color: #495057; margin: 15px 0;">
                    Initializing...
                </div>
                <div id="progress_details_sr" style="font-size: 13px; color: #6c757d; margin-top: 10px;">
                    Please wait while we process your items
                </div>
                <div id="progress_percentage_sr" style="font-size: 24px; font-weight: bold; color: #17a2b8; margin-top: 15px;">
                    0%
                </div>
            </div>
        `);
    }, 100);

    // Helper function to update progress
    function updateProgress(percentage, text, details = '') {
        try {
            let progress_bar = progress_dialog.$wrapper.find('#progress_bar_sr');
            let progress_text = progress_dialog.$wrapper.find('#progress_text_sr');
            let progress_details = progress_dialog.$wrapper.find('#progress_details_sr');
            let progress_percentage = progress_dialog.$wrapper.find('#progress_percentage_sr');

            if (progress_bar.length) {
                progress_bar.css('width', percentage + '%');
            }
            if (progress_text.length) {
                progress_text.text(text);
            }
            if (progress_details.length && details) {
                progress_details.text(details);
            }
            if (progress_percentage.length) {
                progress_percentage.text(Math.round(percentage) + '%');
            }
        } catch (error) {
            console.log('Progress update error:', error);
        }
    }

    let lines = items_data.split('\n');
    let success_count = 0;
    let error_count = 0;
    let errors = [];
    let items_to_add = [];

    updateProgress(10, 'Validating input data...', `Processing ${lines.length} lines`);
    await new Promise(resolve => setTimeout(resolve, 200));

    // First pass: validate and prepare data
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        if (!line) continue; // Skip empty lines

        let parts = line.split(';');
        let item_name_detail = parts[0].trim();
        let qty = 1; // Default quantity
        let field_data = {};

        // Check if we have at least the item pattern
        if (!item_name_detail) {
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

        // Process custom_customs_declaration_number (parts[4])
        if (parts.length >= 5 && parts[4].trim() !== '') {
            field_data.custom_customs_declaration_number = parts[4].trim();
        } else {
            field_data.custom_customs_declaration_number = '';
        }
        item_name_detail += '%'; // Ensure pattern ends with %
        items_to_add.push({
            line_number: i + 1,
            search_pattern: item_name_detail,
            field_data: field_data,
            qty: qty
        });

        // Update progress during validation - optimized for larger batches
        if (i % 50 === 0 || i === lines.length - 1) {
            let progress = 10 + (i / lines.length) * 20;
            updateProgress(progress, 'Validating input data...', `Processed ${i + 1}/${lines.length} lines`);
            // Reduced delay for faster processing
            await new Promise(resolve => setTimeout(resolve, 20));
        }
    }

    // Second pass: Find all items in batch
    updateProgress(30, 'Searching for items in database...', `Searching ${items_to_add.length} patterns`);
    await new Promise(resolve => setTimeout(resolve, 200));
    let found_items = [];
    let search_patterns = items_to_add.map(item => item.search_pattern);
    try {
        // Process items in smaller batches to avoid overwhelming the server
        const BATCH_SIZE = 500; // Process 500 items at a time
        let batch_responses = [];

        for (let i = 0; i < search_patterns.length; i += BATCH_SIZE) {
            let batch_patterns = search_patterns.slice(i, i + BATCH_SIZE);
            let batch_promises = batch_patterns.map(pattern =>
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Item',
                        filters: {
                            'custom_item_name_detail': ['like', pattern],
                            'variant_of': ['!=', '']  // Chỉ lấy item variants (có parent template)
                        },
                        fields: ['name', 'item_code', 'item_name', 'stock_uom'],
                        order_by: 'LENGTH(custom_item_name_detail) ASC',  // Chuỗi ngắn hơn lên đầu
                        limit: 1
                    }
                })
            );

            let batch_results = await Promise.all(batch_promises);
            batch_responses.push(...batch_results);

            // Update progress for each batch
            let progress = 30 + ((i + batch_patterns.length) / search_patterns.length) * 20;
            updateProgress(progress, 'Searching for items in database...', `Processed ${Math.min(i + BATCH_SIZE, search_patterns.length)}/${search_patterns.length} patterns`);
            await new Promise(resolve => setTimeout(resolve, 50));
        }

        updateProgress(50, 'Processing search results...', `Found items for ${batch_responses.length} patterns`);
        await new Promise(resolve => setTimeout(resolve, 200));

        // Process batch responses and map to original items
        for (let i = 0; i < batch_responses.length; i++) {
            let response = batch_responses[i];
            let original_item = items_to_add[i];

            if (response.message && response.message.length > 0) {
                let item = response.message[0];
                found_items.push({
                    ...original_item,
                    item_code: item.item_code,
                    item_name: item.item_name,
                    stock_uom: item.stock_uom,
                    found: true
                });
            } else {
                errors.push(__('Line {0}: Item not found with pattern: {1}', [original_item.line_number, original_item.search_pattern]));
                error_count++;
            }
        }
        // Third pass: Get item details for found items (warehouse defaults)
        if (found_items.length > 0) {
            updateProgress(60, 'Getting item details...', `Processing ${found_items.length} found items`);
            await new Promise(resolve => setTimeout(resolve, 200));

            // Process item details in batches to avoid overwhelming the server
            const DETAIL_BATCH_SIZE = 300; // Process 300 item details at a time
            let item_detail_responses = [];

            for (let i = 0; i < found_items.length; i += DETAIL_BATCH_SIZE) {
                let batch_items = found_items.slice(i, i + DETAIL_BATCH_SIZE);
                let batch_promises = batch_items.map(item =>
                    frappe.call({
                        method: 'frappe.client.get',
                        args: {
                            doctype: 'Item',
                            name: item.item_code
                        }
                    })
                );

                let batch_results = await Promise.all(batch_promises);
                item_detail_responses.push(...batch_results);

                // Update progress for each batch
                let progress = 60 + ((i + batch_items.length) / found_items.length) * 10;
                updateProgress(progress, 'Getting item details...', `Processed ${Math.min(i + DETAIL_BATCH_SIZE, found_items.length)}/${found_items.length} items`);
                await new Promise(resolve => setTimeout(resolve, 30));
            }

            // Add warehouse defaults to found items
            for (let i = 0; i < item_detail_responses.length; i++) {
                let response = item_detail_responses[i];
                if (response.message && response.message.item_defaults) {
                    // Find default warehouse for current company
                    for (let item_default of response.message.item_defaults) {
                        if (item_default.company === frm.doc.company && item_default.default_warehouse) {
                            found_items[i].default_warehouse = item_default.default_warehouse;
                            break;
                        }
                    }
                }
            }
        }

        // Fourth pass: Add all rows to table (including qty) - Optimized for large batches
        updateProgress(70, 'Adding items to table...', `Adding ${found_items.length} items`);
        await new Promise(resolve => setTimeout(resolve, 100));

        let added_rows = [];

        // Process items in smaller chunks to avoid DOM overload
        const ADD_BATCH_SIZE = 200; // Add 200 items at a time before refreshing

        for (let batch_start = 0; batch_start < found_items.length; batch_start += ADD_BATCH_SIZE) {
            let batch_end = Math.min(batch_start + ADD_BATCH_SIZE, found_items.length);
            let batch_items = found_items.slice(batch_start, batch_end);

            // Add batch of items without refreshing grid each time
            for (let i = 0; i < batch_items.length; i++) {
                let item = batch_items[i];
                let global_index = batch_start + i;

                try {
                    // Add new row
                    let new_row = frm.add_child('items');

                    // Set basic item values (including qty this time)
                    let values_to_set = {
                        'item_code': item.item_code,
                        'qty': item.qty,  // Set qty immediately
                        'allow_zero_valuation_rate': 1,
                    };

                    // Add default warehouse if available
                    if (item.default_warehouse) {
                        values_to_set.warehouse = item.default_warehouse;
                    }

                    // Add type-specific fields
                    Object.assign(values_to_set, item.field_data);

                    // Set all values including qty
                    Object.keys(values_to_set).forEach(function (field) {
                        // Set directly on the row object
                        new_row[field] = values_to_set[field];
                    });

                    // Store row info for backup qty setting
                    added_rows.push({
                        doctype: new_row.doctype,
                        name: new_row.name,
                        qty: item.qty
                    });

                    success_count++;

                } catch (error) {
                    errors.push(__('Line {0}: Error adding item to table: {1}', [item.line_number, error.message]));
                    error_count++;
                }
            }

            // Update progress after each batch
            let progress = 70 + ((batch_end) / found_items.length) * 15;
            updateProgress(progress, 'Adding items to table...', `Added ${batch_end}/${found_items.length} items`);

            // Small delay between batches to keep UI responsive
            if (batch_end < found_items.length) {
                await new Promise(resolve => setTimeout(resolve, 50));
            }
        }

        // Refresh grid after adding all rows - Optimized for large datasets
        if (added_rows.length > 0) {
            updateProgress(85, 'Refreshing table display...', 'Updating user interface');
            await new Promise(resolve => setTimeout(resolve, 100));

            frm.refresh_field('items');
            // Reduced wait time for refresh to complete
            await new Promise(resolve => setTimeout(resolve, 300));

            updateProgress(90, 'Verifying quantities...', 'Ensuring all quantities are correct');
            await new Promise(resolve => setTimeout(resolve, 100));

            // Verify and fix qty values in batches for better performance
            const VERIFY_BATCH_SIZE = 500;
            for (let i = 0; i < added_rows.length; i += VERIFY_BATCH_SIZE) {
                let batch_rows = added_rows.slice(i, i + VERIFY_BATCH_SIZE);

                for (let row_info of batch_rows) {
                    try {
                        let row = locals[row_info.doctype][row_info.name];
                        if (row && (!row.qty || row.qty === 0)) {
                            row.qty = row_info.qty;
                            frappe.model.set_value(row_info.doctype, row_info.name, 'qty', row_info.qty);
                            frappe.model.set_value(row_info.doctype, row_info.name, 'allow_zero_valuation_rate', 1);
                        }
                    } catch (error) {
                        console.error(`Error verifying qty for row ${row_info.name}:`, error);
                    }
                }

                // Small delay between verification batches
                if (i + VERIFY_BATCH_SIZE < added_rows.length) {
                    await new Promise(resolve => setTimeout(resolve, 10));
                }
            }
        }

        updateProgress(100, 'Completed!', `Successfully added ${success_count} items`);
        await new Promise(resolve => setTimeout(resolve, 800));

    } catch (error) {
        console.error('Error in batch processing:', error);
        errors.push(__('Error in batch processing: {0}', [error.message]));
        error_count++;
        updateProgress(100, 'Error occurred', 'Processing failed');
        await new Promise(resolve => setTimeout(resolve, 1000));
    }

    // Close progress dialog
    progress_dialog.hide();

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

// Function to show/hide duplicate button with proper styling
// Client Script for Stock Reconciliation - Quick Add functionality
// Purpose: Add Quick Add button for Opening Stock purpose with custom format
// Format: item_name_detail;invoice_number;qty;receive_date
// Updated: Progress dialog, button states, max 100 lines limit

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
        // Update Quick Add button state when purpose changes
        if (frm.opening_stock_quick_add_btn) {
            update_quick_add_button_state_sr(frm, frm.opening_stock_quick_add_btn);
        }

        // Update duplicate button state as well
        toggle_duplicate_button_sr(frm);
        initialize_quick_add_button_sr(frm);
    },

    refresh: function (frm) {
        // Initialize duplicate button (hidden initially)
        let duplicate_btn = frm.fields_dict.items.grid.add_custom_button(__('Duplicate Selected'),
            function () {
                let selected_rows = frm.fields_dict.items.grid.get_selected();
                if (selected_rows.length === 0) {
                    frappe.msgprint({
                        title: __('No Selection'),
                        message: __('Please select one or more rows to duplicate'),
                        indicator: 'red'
                    });
                    return;
                }

                // Check if document is submitted
                if (frm.doc.docstatus === 1) {
                    frappe.msgprint({
                        title: __('Document Submitted'),
                        message: __('Cannot duplicate rows in a submitted document'),
                        indicator: 'red'
                    });
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

        // Always add Quick Add button (but handle disabled state)
        if (!frm.quick_add_btn_added) {
            let opening_stock_quick_add_btn = frm.fields_dict.items.grid.add_custom_button(__('Opening Stock - Quick Add'),
                function () {
                    // Check if button should be disabled
                    let is_disabled = frm.doc.purpose !== "Opening Stock" || frm.doc.docstatus === 1;

                    if (is_disabled) {
                        // Show appropriate message based on condition
                        if (frm.doc.docstatus === 1) {
                            frappe.msgprint({
                                title: __('Document Submitted'),
                                message: __('Cannot add items to a submitted Stock Reconciliation'),
                                indicator: 'red'
                            });
                        } else if (frm.doc.purpose !== "Opening Stock") {
                            frappe.msgprint({
                                title: __('Invalid Purpose'),
                                message: __('Quick Add is only available for Opening Stock purpose.<br>Current purpose: <strong>{0}</strong><br><br>Please change the purpose to "Opening Stock" to use this feature.', [frm.doc.purpose || 'Not Set']),
                                indicator: 'orange'
                            });
                        }
                        return;
                    }

                    // Proceed with Quick Add dialog
                    show_quick_add_dialog_sr(frm, 'opening_stock');
                }
            );

            // Update button styling based on state
            update_quick_add_button_state_sr(frm, opening_stock_quick_add_btn);

            // Save reference to button
            frm.opening_stock_quick_add_btn = opening_stock_quick_add_btn;

            // Mark that Quick Add button has been added
            frm.quick_add_btn_added = true;
        } else {
            // Update existing button state
            if (frm.opening_stock_quick_add_btn) {
                update_quick_add_button_state_sr(frm, frm.opening_stock_quick_add_btn);
            }
        }

        initialize_quick_add_button_sr(frm);
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
    },

    // Update button states when document status changes
    after_save: function (frm) {
        setTimeout(() => {
            initialize_quick_add_button_sr(frm);
            // Update button states after save (docstatus might have changed)
            if (frm.opening_stock_quick_add_btn) {
                update_quick_add_button_state_sr(frm, frm.opening_stock_quick_add_btn);
            }
            toggle_duplicate_button_sr(frm);
        }, 300);
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
            // Validate line count
            if (!values.items_data) {
                frappe.msgprint({
                    title: __('No Data'),
                    message: __('Please enter items data'),
                    indicator: 'red'
                });
                return;
            }

            let lines = values.items_data.split('\n').filter(line => line.trim());
            if (lines.length > max_line_quick_add) {
                frappe.msgprint({
                    title: __('Too Many Lines'),
                    message: __('Maximum {0} lines allowed per Quick Add operation.<br>Current lines: <strong>{1}</strong><br><br>Please split your data into smaller batches.', [max_line_quick_add, lines.length]),
                    indicator: 'red'
                });
                return;
            }

            if (lines.length === 0) {
                frappe.msgprint({
                    title: __('No Valid Lines'),
                    message: __('Please enter at least one valid line of data'),
                    indicator: 'red'
                });
                return;
            }

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

// Function to show/hide duplicate button with proper styling
function toggle_duplicate_button_sr(frm) {
    if (!frm.duplicate_btn) return;

    let selected_rows = frm.fields_dict.items.grid.get_selected();
    let is_disabled = frm.doc.docstatus === 1; // Disable if document is submitted

    if (selected_rows.length > 0 && !is_disabled) {
        frm.duplicate_btn.show();
        // Update button text with selected count and enable styling
        frm.duplicate_btn.text(__(`Duplicate Selected (${selected_rows.length})`));
        frm.duplicate_btn.removeClass('btn-secondary').addClass('btn-primary').css({
            'background-color': '#6495ED',
            'border-color': '#6495ED',
            'color': '#fff',
            'cursor': 'pointer',
            'opacity': '1'
        });
    } else if (selected_rows.length > 0 && is_disabled) {
        frm.duplicate_btn.show();
        // Show but disabled
        frm.duplicate_btn.text(__(`Duplicate Selected (${selected_rows.length}) - Disabled`));
        frm.duplicate_btn.removeClass('btn-primary').addClass('btn-secondary').css({
            'background-color': '#6c757d',
            'border-color': '#6c757d',
            'color': '#fff',
            'cursor': 'not-allowed',
            'opacity': '0.6'
        });
    } else {
        frm.duplicate_btn.hide();
    }
}

// Function to update Quick Add button state
function update_quick_add_button_state_sr(frm, button) {
    if (!button) return;

    let is_disabled = frm.doc.purpose !== "Opening Stock" || frm.doc.docstatus === 1;

    if (is_disabled) {
        // Disabled state - gray styling
        button.removeClass('btn-info').addClass('btn-secondary').css({
            'background-color': '#6c757d',
            'border-color': '#6c757d',
            'color': '#fff',
            'cursor': 'not-allowed',
            'opacity': '0.6'
        });

        // // Update button text to indicate disabled
        // if (frm.doc.docstatus === 1) {
        //     button.text(__('Opening Stock - Quick Add (Document Submitted)'));
        // } else {
        //     button.text(__('Opening Stock - Quick Add (Wrong Purpose)'));
        // }
    } else {
        // Enabled state - blue styling
        button.removeClass('btn-secondary').addClass('btn-info').css({
            'background-color': '#17a2b8',
            'border-color': '#138496',
            'color': '#fff',
            'cursor': 'pointer',
            'opacity': '1'
        });

        // Reset button text
        button.text(__('Opening Stock - Quick Add'));
    }
}

// NEW FUNCTION: Initialize Quick Add button at form level
function initialize_quick_add_button_sr(frm) {
    // Xóa button cũ nếu có
    if (frm.quick_add_btn) {
        frm.remove_custom_button(__('Opening Stock - Quick Add'));
        frm.quick_add_btn = null;
    }
    // Luôn add button, nhưng disable khi không hợp lệ
    frm.quick_add_btn = frm.add_custom_button(__('Opening Stock - Quick Add'), function () {
        if (frm.doc.docstatus === 1) {
            frappe.msgprint(__('Cannot add items to a submitted Stock Reconciliation'));
            return;
        }
        if (frm.doc.purpose !== "Opening Stock") {
            frappe.msgprint(__('Quick Add is only available for Opening Stock purpose.<br>Current purpose: <strong>{0}</strong><br><br>Please change the purpose to "Opening Stock" to use this feature.', [frm.doc.purpose || 'Not Set']));
            return;
        }
        show_quick_add_dialog_sr(frm, 'opening_stock');
    });
    // Style button
    let btn = $(frm.custom_buttons[__('Opening Stock - Quick Add')]);
    let is_disabled = frm.doc.purpose !== "Opening Stock" || frm.doc.docstatus === 1;
    if (is_disabled) {
        btn.removeClass('btn-info').addClass('btn-secondary').css({
            'background-color': '#6c757d',
            'border-color': '#6c757d',
            'color': '#fff',
            'cursor': 'not-allowed',
            'opacity': '0.6',
            'pointer-events': 'none'
        });
    } else {
        btn.removeClass('btn-secondary').addClass('btn-info').css({
            'background-color': '#17a2b8',
            'border-color': '#138496',
            'color': '#fff',
            'cursor': 'pointer',
            'opacity': '1',
            'pointer-events': 'auto'
        });
    }
}
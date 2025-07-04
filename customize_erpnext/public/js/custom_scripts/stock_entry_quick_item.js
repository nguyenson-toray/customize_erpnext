// Enhanced Stock Entry Quick Add and Duplicate functionality
// Merged optimized features from stock_reconciliation.js
// Features: Progress dialog, batch processing, improved qty handling, max 100 lines validation
// Updated: Buttons always visible with proper disable states

frappe.ui.form.on('Stock Entry', {
    onload: function (frm) {
        // Setup cleanup for browser navigation/close
        $(window).on('beforeunload.quick_add_se', function () {
            // Cleanup any remaining intervals or listeners
        });

        // Setup keyboard shortcuts for duplicate functionality
        $(document).on('keydown.duplicate_rows_se', function (e) {
            // Only work when focused on this form
            if (frm.doc.name && frm.doc.doctype === 'Stock Entry') {
                // Ctrl+D to duplicate
                if (e.ctrlKey && e.keyCode === 68) {
                    e.preventDefault();

                    let selected_rows = frm.fields_dict.items.grid.get_selected();
                    if (selected_rows.length > 0) {
                        selected_rows.forEach(function (row_name) {
                            let source_row = locals['Stock Entry Detail'][row_name];

                            // Add new row first
                            let new_row = frm.add_child('items');

                            // Copy all fields except system fields
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
        // Simple cleanup - keyboard and window events only
        $(document).off('keydown.duplicate_rows_se');
        $(window).off('beforeunload.quick_add_se');
    },

    stock_entry_type: function (frm) {
        // Re-initialize form buttons when stock entry type changes
        initialize_form_buttons_se(frm);
    },

    refresh: function (frm) {
        // Initialize form-level Quick Add buttons
        initialize_form_buttons_se(frm);

        // Always show duplicate button (grid level for this one)
        let duplicate_btn = frm.fields_dict.items.grid.add_custom_button(__('Duplicate Selected'),
            function () {
                try {
                    let selected_rows = frm.fields_dict.items.grid.get_selected();

                    if (frm.doc.docstatus === 1) {
                        throw new Error('Cannot duplicate rows in a submitted document');
                    }

                    if (selected_rows.length === 0) {
                        throw new Error('Please select one or more rows to duplicate');
                    }

                    // Duplicate logic using original pattern to avoid mandatory field issues
                    selected_rows.forEach(function (row_name) {
                        let source_row = locals['Stock Entry Detail'][row_name];

                        // Add new row first
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
                } catch (error) {
                    frappe.msgprint({
                        title: __('Duplicate Error'),
                        message: __(error.message),
                        indicator: 'red'
                    });
                }
            }
        );

        // Save reference for access from other functions
        frm.duplicate_btn = duplicate_btn;

        // Setup listener to monitor selection changes for duplicate button
        setup_selection_monitor_se(frm);

        // Update duplicate button style
        update_duplicate_button_style_se(frm);
    },

    // Validate before submit to ensure custom fields are properly set
    before_submit: function (frm) {
        // Basic validation only - no date validation needed
        frappe.validated = true;
    },

    // Update button states when document status changes
    after_save: function (frm) {
        // Re-initialize form buttons after save
        setTimeout(() => {
            initialize_form_buttons_se(frm);
            update_duplicate_button_style_se(frm);
        }, 300);
    }
});

// Event handlers for individual child table row changes
frappe.ui.form.on('Stock Entry Detail', {
    custom_invoice_number: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Trim the field when user moves out of the field
        if (row.custom_invoice_number && typeof row.custom_invoice_number === 'string') {
            let trimmed_value = row.custom_invoice_number.trim();

            if (row.custom_invoice_number !== trimmed_value) {
                frappe.model.set_value(cdt, cdn, 'custom_invoice_number', trimmed_value);
            }
        }
    }
});

// HELPER FUNCTION: Parse Vietnamese number format (comma as decimal separator)
function parseVietnameseFloat_se(value) {
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

// ENHANCED FUNCTION: Show Quick Add Dialog with validation
function show_quick_add_dialog_se(frm, dialog_type) {
    let dialog_config = get_dialog_config_se(dialog_type);

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
            // Validate line count (max 100 lines like stock reconciliation)
            if (!values.items_data) {
                frappe.msgprint({
                    title: __('No Data'),
                    message: __('Please enter items data'),
                    indicator: 'red'
                });
                return;
            }

            let lines = values.items_data.split('\n').filter(line => line.trim());
            if (lines.length > 100) {
                frappe.msgprint({
                    title: __('Too Many Lines'),
                    message: __('Maximum 100 lines allowed per Quick Add operation.<br>Current lines: <strong>{0}</strong><br><br>Please split your data into smaller batches.', [lines.length]),
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

            process_quick_add_items_se(frm, values.items_data, dialog_type);
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

// ENHANCED FUNCTION: Get dialog configuration with max 100 lines note
function get_dialog_config_se(dialog_type) {
    let dialog_description = `
    <div style="background: #f8f9fa; padding: 15px; border-radius: 12px; font-size: 13px; line-height: 1.4;">
                    
                    <div style="display: flex; gap: 20px;">
                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📝 Format Options</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                                <strong>1. Full format:</strong> <code>item_name_detail; invoice_number; qty</code><br>
                                <strong>2. With Invoice:</strong> <code>item_name_detail; invoice_number</code><br>
                                <strong>3. Skip Invoice:</strong> <code>item_name_detail; ; qty</code><br>
                                <strong>4. Simple:</strong> <code>item_name_detail</code><br>
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
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss; IV001; 25,75</code><br><small style="color: #28a745;">→ qty=25.75, Invoice=IV001</small></div>
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss; IV002</code><br><small style="color: #28a745;">→ qty=1, Invoice=IV002</small></div>
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss; ; 30</code><br><small style="color: #28a745;">→ qty=30, Invoice=empty</small></div>
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss</code><br><small style="color: #28a745;">→ qty=1, Invoice=empty</small></div>
                                                                
                            </div>
                            
                            <h4 style="margin: 15px 0 10px 0; color: #333;">ℹ️ Notes</h4>
                            <div style="background: #fff3cd; padding: 10px; border-radius: 4px; border-left: 4px solid #ffc107;">
                                <small>
                                • <strong>Maximum 100 lines per batch</strong><br>
                                • Each line = one item<br>
                                • System searches "Item Name Detail" field<br>
                                • Invalid items will be skipped with error report
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
    `;
    if (dialog_type === 'material_issue') {
        return {
            title: __('Quick Add Items - Material Issue (Max 100 lines)'),
            description: __(dialog_description)
        };
    } else if (dialog_type === 'material_receipt') {
        return {
            title: __('Quick Add Items - Material Receipt (Max 100 lines)'),
            description: __(dialog_description)
        };
    }
}

// OPTIMIZED FUNCTION: Process Quick Add Items with Progress Dialog and Batch Processing
async function process_quick_add_items_se(frm, items_data, dialog_type) {
    if (!items_data) return;

    // Create progress dialog with enhanced UI (from stock_reconciliation.js)
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
                    <div id="progress_bar_se" style="width: 0%; height: 100%; background: linear-gradient(90deg, #17a2b8, #20c997); transition: width 0.5s ease; border-radius: 10px;"></div>
                </div>
                <div id="progress_text_se" style="font-size: 16px; font-weight: 500; color: #495057; margin: 15px 0;">
                    Initializing...
                </div>
                <div id="progress_details_se" style="font-size: 13px; color: #6c757d; margin-top: 10px;">
                    Please wait while we process your items
                </div>
                <div id="progress_percentage_se" style="font-size: 24px; font-weight: bold; color: #17a2b8; margin-top: 15px;">
                    0%
                </div>
            </div>
        `);
    }, 100);

    // Helper function to update progress
    function updateProgress(percentage, text, details = '') {
        try {
            let progress_bar = progress_dialog.$wrapper.find('#progress_bar_se');
            let progress_text = progress_dialog.$wrapper.find('#progress_text_se');
            let progress_details = progress_dialog.$wrapper.find('#progress_details_se');
            let progress_percentage = progress_dialog.$wrapper.find('#progress_percentage_se');

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

    // First pass: validate and prepare data based on dialog type
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
            qty = parseVietnameseFloat_se(parts[2].trim());
            if (isNaN(qty) || qty <= 0) {
                errors.push(__('Line {0}: Invalid quantity: {1}', [i + 1, parts[2]]));
                error_count++;
                continue;
            }
        }
        item_name_detail += '%'; // Ensure pattern ends with %
        items_to_add.push({
            line_number: i + 1,
            search_pattern: item_name_detail,
            field_data: field_data,
            qty: qty
        });

        // Update progress during validation
        if (i % 5 === 0 || i === lines.length - 1) {
            let progress = 10 + (i / lines.length) * 20;
            updateProgress(progress, 'Validating input data...', `Processed ${i + 1}/${lines.length} lines`);
            await new Promise(resolve => setTimeout(resolve, 50));
        }
    }

    // Second pass: Find all items in batch (optimized from stock_reconciliation.js)
    updateProgress(30, 'Searching for items in database...', `Searching ${items_to_add.length} patterns`);
    await new Promise(resolve => setTimeout(resolve, 200));
    let found_items = [];
    let search_patterns = items_to_add.map(item => item.search_pattern);

    try {
        // Find all items using batch call
        let batch_responses = await Promise.all(
            search_patterns.map(pattern =>
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Item',
                        filters: {
                            'custom_item_name_detail': ['like', pattern],
                            'variant_of': ['!=', '']  // Chỉ lấy item variants (có parent template)
                        },
                        fields: ['name', 'item_code', 'item_name', 'stock_uom'],
                        order_by: 'LENGTH(custom_item_name_detail) ASC',
                        limit: 1
                    }
                })
            )
        );

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


        // Third pass: Add all rows to table using optimized method
        updateProgress(70, 'Adding items to table...', `Adding ${found_items.length} items`);
        await new Promise(resolve => setTimeout(resolve, 200));
        let added_rows = [];

        for (let i = 0; i < found_items.length; i++) {
            let item = found_items[i];
            try {
                console.log(`Processing item: ${i + 1} ${item.item_code} for pattern: ${item.search_pattern}, qty: ${item.qty}`);

                // Add new row using optimized pattern from stock_reconciliation.js
                let new_row = frm.add_child('items');

                // Set item_code first to trigger auto-population of UOM fields
                await frappe.model.set_value(new_row.doctype, new_row.name, 'item_code', item.item_code);

                // Wait for item_code to be fully processed and UOM fields populated
                await new Promise(resolve => setTimeout(resolve, 200));

                // Set quantity and other fields directly on row object (more reliable)
                new_row.qty = item.qty;

                // Set additional fields
                for (let field of Object.keys(item.field_data)) {
                    new_row[field] = item.field_data[field];
                }

                // Store row info for backup qty setting
                added_rows.push({
                    doctype: new_row.doctype,
                    name: new_row.name,
                    qty: item.qty
                });

                success_count++;
                // Update progress for every 3 items or last item
                if (i % 3 === 0 || i === found_items.length - 1) {
                    let progress = 70 + ((i + 1) / found_items.length) * 15;
                    updateProgress(progress, 'Adding items to table...', `Added ${i + 1}/${found_items.length} items`);
                    await new Promise(resolve => setTimeout(resolve, 100));
                }

            } catch (error) {
                errors.push(__('Line {0}: Error adding item to table: {1}', [item.line_number, error.message]));
                error_count++;
            }
        }

        // Refresh grid after adding all rows
        if (added_rows.length > 0) {
            updateProgress(85, 'Refreshing table display...', 'Updating user interface');
            await new Promise(resolve => setTimeout(resolve, 200));

            frm.refresh_field('items');
            // Wait for refresh to complete, then verify and fix qty if needed
            await new Promise(resolve => setTimeout(resolve, 500));

            updateProgress(90, 'Verifying quantities...', 'Ensuring all quantities are correct');
            await new Promise(resolve => setTimeout(resolve, 200));
            for (let row_info of added_rows) {
                try {
                    let row = locals[row_info.doctype][row_info.name];
                    if (row && (!row.qty || row.qty === 0 || row.qty != row_info.qty)) {
                        await frappe.model.set_value(row_info.doctype, row_info.name, 'qty', row_info.qty);
                    }
                } catch (error) {
                    console.error(`Error verifying qty for row ${row_info.name}:`, error);
                }
            }

            // Final refresh to ensure all changes are visible
            frm.refresh_field('items');
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

// ENHANCED FUNCTION: Monitor selection changes
function setup_selection_monitor_se(frm) {
    // Monitor click events on grid
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-row-check', function () {
        setTimeout(() => {
            update_duplicate_button_style_se(frm);
        }, 50); // Small delay to ensure selection has been updated
    });

    // Monitor click on row (can select/deselect)
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-row', function () {
        setTimeout(() => {
            update_duplicate_button_style_se(frm);
        }, 50);
    });

    // Monitor select all checkbox
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-header-row .grid-row-check', function () {
        setTimeout(() => {
            update_duplicate_button_style_se(frm);
        }, 50);
    });

    // Monitor keyboard events (Ctrl+A, arrow keys, etc.)
    frm.fields_dict.items.grid.wrapper.on('keyup', function () {
        setTimeout(() => {
            update_duplicate_button_style_se(frm);
        }, 50);
    });
}

// NEW FUNCTION: Initialize Form-level Quick Add buttons (much simpler & stable)
function initialize_form_buttons_se(frm) {
    try {
        // Remove existing custom buttons to prevent duplicates
        frm.custom_buttons = frm.custom_buttons || {};

        // Remove existing Quick Add buttons
        if (frm.custom_buttons['Material Issue - Quick Add']) {
            frm.remove_custom_button('Material Issue - Quick Add');
        }
        if (frm.custom_buttons['Material Receipt - Quick Add']) {
            frm.remove_custom_button('Material Receipt - Quick Add');
        }

        // Get current state
        let is_submitted = frm.doc.docstatus === 1;
        let is_material_issue = frm.doc.stock_entry_type === "Material Issue";
        let is_material_receipt = frm.doc.stock_entry_type === "Material Receipt";

        // Add Material Issue button
        if (is_material_issue && !is_submitted) {
            // Enabled state
            frm.add_custom_button(__('Material Issue - Quick Add'), function () {
                handle_quick_add_click_se(frm, 'material_issue');
            }).addClass('btn btn-success').css({
                'background-color': '#5cb85c',
                'border-color': '#4cae4c',
                'color': '#fff'
            });
        } else if (is_material_issue && is_submitted) {
            // Disabled state for submitted
            frm.add_custom_button(__('Material Issue - Quick Add'), function () {
                throw_error_se('Cannot add items to submitted document');
            }).addClass('btn btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6'
            });
        } else {
            // Show for wrong type but disabled
            frm.add_custom_button(__('Material Issue - Quick Add'), function () {
                throw_error_se('This function is only available for Material Issue entries');
            }).addClass('btn btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6'
            });
        }

        // Add Material Receipt button
        if (is_material_receipt && !is_submitted) {
            // Enabled state
            frm.add_custom_button(__('Material Receipt - Quick Add'), function () {
                handle_quick_add_click_se(frm, 'material_receipt');
            }).addClass('btn btn-warning').css({
                'background-color': '#f0ad4e',
                'border-color': '#eea236',
                'color': '#fff'
            });
        } else if (is_material_receipt && is_submitted) {
            // Disabled state for submitted
            frm.add_custom_button(__('Material Receipt - Quick Add'), function () {
                throw_error_se('Cannot add items to submitted document');
            }).addClass('btn btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6'
            });
        } else {
            // Show for wrong type but disabled
            frm.add_custom_button(__('Material Receipt - Quick Add'), function () {
                throw_error_se('This function is only available for Material Receipt entries');
            }).addClass('btn btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6'
            });
        }
    } catch (error) {
        console.error('Error initializing form buttons:', error);
        throw_error_se('Failed to initialize Quick Add buttons: ' + error.message);
    }
}

// NEW FUNCTION: Handle Quick Add button clicks with error handling
function handle_quick_add_click_se(frm, dialog_type) {
    try {
        // Validate document state
        if (frm.doc.docstatus === 1) {
            throw new Error('Cannot add items to a submitted document');
        }

        // Validate stock entry type
        if (dialog_type === 'material_issue' && frm.doc.stock_entry_type !== "Material Issue") {
            throw new Error('This function is only available for Material Issue entries');
        }

        if (dialog_type === 'material_receipt' && frm.doc.stock_entry_type !== "Material Receipt") {
            throw new Error('This function is only available for Material Receipt entries');
        }

        // Validate grid existence
        if (!frm.fields_dict || !frm.fields_dict.items || !frm.fields_dict.items.grid) {
            throw new Error('Items table is not ready. Please wait and try again.');
        }

        // All validations passed - show dialog
        show_quick_add_dialog_se(frm, dialog_type);

    } catch (error) {
        throw_error_se(error.message);
    }
}

// NEW FUNCTION: Standardized error throwing
function throw_error_se(message) {
    frappe.msgprint({
        title: __('Quick Add Error'),
        message: __(message),
        indicator: 'red'
    });
    console.error('Quick Add Error:', message);
}

// NEW FUNCTION: Update Quick Add button styles (simplified - no text change)
function update_quick_add_button_styles_se(frm) {
    try {
        if (!frm.material_issue_btn || !frm.material_receipt_btn) {
            return;
        }

        let is_submitted = frm.doc.docstatus === 1;
        let is_material_issue = frm.doc.stock_entry_type === "Material Issue";
        let is_material_receipt = frm.doc.stock_entry_type === "Material Receipt";

        // Material Issue button styling
        if (is_submitted || !is_material_issue) {
            // Disabled state - gray color only
            frm.material_issue_btn.removeClass('btn-success').addClass('btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6',
                'pointer-events': 'none'
            });
        } else {
            // Enabled state
            frm.material_issue_btn.removeClass('btn-secondary').addClass('btn-success').css({
                'background-color': '#5cb85c',
                'border-color': '#4cae4c',
                'color': '#fff',
                'cursor': 'pointer',
                'opacity': '1',
                'pointer-events': 'auto'
            });
        }

        // Material Receipt button styling
        if (is_submitted || !is_material_receipt) {
            // Disabled state - gray color only
            frm.material_receipt_btn.removeClass('btn-warning').addClass('btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6',
                'pointer-events': 'none'
            });
        } else {
            // Enabled state
            frm.material_receipt_btn.removeClass('btn-secondary').addClass('btn-warning').css({
                'background-color': '#f0ad4e',
                'border-color': '#eea236',
                'color': '#fff',
                'cursor': 'pointer',
                'opacity': '1',
                'pointer-events': 'auto'
            });
        }
    } catch (error) {
        console.error('Error updating Quick Add button styles:', error);
    }
}

// NEW FUNCTION: Update Duplicate button style (simplified - no text change)
function update_duplicate_button_style_se(frm) {
    try {
        if (!frm.duplicate_btn) {
            return;
        }

        let selected_rows = frm.fields_dict.items.grid.get_selected();
        let is_submitted = frm.doc.docstatus === 1;
        let has_selection = selected_rows.length > 0;

        // Always show button, but style it based on state
        if (is_submitted || !has_selection) {
            // Disabled state - gray color only
            frm.duplicate_btn.removeClass('btn-primary').addClass('btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6',
                'pointer-events': 'none'
            });
        } else {
            // Enabled state
            frm.duplicate_btn.removeClass('btn-secondary').addClass('btn-primary').css({
                'background-color': '#6495ED',
                'border-color': '#6495ED',
                'color': '#fff',
                'cursor': 'pointer',
                'opacity': '1',
                'pointer-events': 'auto'
            });
        }
    } catch (error) {
        console.error('Error updating Duplicate button style:', error);
    }
}

// NEW FUNCTION: Update all button styles
function update_all_button_styles_se(frm) {
    try {
        update_quick_add_button_styles_se(frm);
        update_duplicate_button_style_se(frm);
    } catch (error) {
        console.error('Error updating all button styles:', error);
    }
}
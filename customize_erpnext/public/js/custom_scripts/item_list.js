frappe.listview_settings['Item'] = {
    onload: function (listview) {
        // Add "Print QR Labels" button to Item List
        listview.page.add_inner_button(__('Print QR Labels'), function () {
            show_qr_label_dialog(listview);
        }, __('Actions'));

        // Add "Quick Check Item" button to Item List
        listview.page.add_inner_button(__('Quick Check Item'), function () {
            show_quick_check_item_dialog(listview);
        }, __('Actions'));

        // Add "Export Master Data - Item - Attribute" button to Item List
        listview.page.add_inner_button(__('Export Master Data - Item - Attribute'), function () {
            export_master_data_item_attribute();
        }, __('Actions'));
    }
};

function show_qr_label_dialog(listview) {
    let dialog = new frappe.ui.Dialog({
        title: __('Print QR Labels (A4 - Tommy No.138). Enter to apply filter, Ctrl + Enter to generate PDF'),
        fields: [

            // {
            //     fieldtype: 'Section Break',
            //     label: __('Filters : Enter to apply filter, Ctrl+Enter to generate PDF')
            // },
            {
                fieldname: 'filter_type',
                fieldtype: 'Select',
                label: __('Filter Type'),
                options: [
                    { value: 'filter', label: __('Custom Filter') },
                    { value: 'recent', label: __('Recent Items') },
                    { value: 'all', label: __('All Items') }
                ],
                default: 'filter',
                change: function () {
                    toggle_filter_fields(dialog);
                }
            },
            {
                fieldname: 'cb1',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'limit',
                fieldtype: 'Int',
                label: __('Limit (Max 1000)'),
                default: 100,
            },
            {
                fieldname: 'cb2',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'item_code',
                fieldtype: 'Data',
                label: __('Item Code'),
                depends_on: 'eval:doc.filter_type=="filter"'
            },
            {
                fieldname: 'cb3',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'custom_item_name_detail',
                fieldtype: 'Data',
                label: __('Item Name Detail'),
                depends_on: 'eval:doc.filter_type=="filter"'
            },
            {
                fieldname: 'cb4',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'item_group',
                fieldtype: 'Link',
                options: 'Item Group',
                label: __('Item Group'),
                depends_on: 'eval:doc.filter_type=="filter"',
                get_query: function () {
                    return {
                        filters: {
                            'is_group': 0
                        }
                    };
                }
            },
            {
                fieldname: 'cb5',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'created_after',
                fieldtype: 'Date',
                label: __('Created After'),
                depends_on: 'eval:doc.filter_type=="filter"'
            },
            {
                fieldtype: 'Section Break',
                label: __('Recent Items Filter'),
                depends_on: 'eval:doc.filter_type=="recent"'
            },
            {
                fieldname: 'recent_days',
                fieldtype: 'Int',
                label: __('Items created in last N days'),
                default: 7,
                depends_on: 'eval:doc.filter_type=="recent"'
            },
            {
                fieldtype: 'Section Break',
                label: __('Apply Filter')
            },
            {
                fieldname: 'item_preview',
                fieldtype: 'HTML',
                label: __('Filtered Items')
            },
            {
                fieldtype: 'Section Break',
                label: __('Selected Items for PDF')
            },
            {
                fieldname: 'selected_items_list',
                fieldtype: 'HTML',
                label: __('Items Added to Print List')
            }
        ],
        size: 'extra-large',
        // Remove primary_action to avoid default Generate PDF button
        secondary_action_label: __('Apply Filter'),
        secondary_action: function (values) {
            // Always get fresh values from dialog
            let current_values = dialog.get_values();
            preview_items(current_values, dialog);
        }
    });

    // Add custom buttons in the desired order
    dialog.page = {
        add_action_item: function (label, action, group) {
            let btn = $(`<button class="btn btn-default btn-sm" style="margin-left: 10px;">${label}</button>`);
            btn.click(action);
            dialog.$wrapper.find('.modal-footer .standard-actions').append(btn);
            return btn;
        }
    };

    // Initialize selected items array
    dialog.selected_items = [];

    dialog.show();

    // Add keyboard event handlers
    $(dialog.$wrapper).on('keydown', function (e) {
        if (e.key === 'Enter') {
            if (e.ctrlKey) {
                // Ctrl+Enter: Generate PDF
                e.preventDefault();
                generate_qr_labels_pdf(dialog.get_values(), null, dialog);
            } else {
                // Enter: Apply Filter
                e.preventDefault();
                let current_values = dialog.get_values();
                preview_items(current_values, dialog);
            }
        }
    });

    // Add buttons in the desired order: Add to List, Clear List, Generate PDF
    setTimeout(() => {
        // 1. "Add to List" button (after Apply Filter)
        let add_btn = dialog.page.add_action_item(__('Add to List'), function () {
            add_selected_items_to_list(dialog);
        });
        add_btn.addClass('btn-warning');

        // 2. "Clear List" button  
        let clear_btn = dialog.page.add_action_item(__('Clear List'), function () {
            clear_selected_items_list(dialog);
        });
        clear_btn.addClass('btn-danger');

        // 3. "Generate PDF" button (last)
        let generate_btn = dialog.page.add_action_item(__('Generate PDF'), function () {
            generate_qr_labels_pdf(dialog.get_values(), null, dialog);
        });
        generate_btn.addClass('btn-primary');
        generate_btn.css('font-weight', 'bold');
    }, 100);

    // Initialize preview and selected items display
    setTimeout(() => {
        preview_items(dialog.get_values(), dialog);
        update_selected_items_display(dialog);
    }, 500);
}

function toggle_filter_fields(dialog) {
    let filter_type = dialog.get_value('filter_type');

    // Refresh dialog to show/hide fields based on filter_type
    dialog.refresh();

    // Update preview when filter type changes
    setTimeout(() => {
        let current_values = dialog.get_values();
        preview_items(current_values, dialog);
    }, 200);
}

function preview_items(values, dialog) {
    if (!values) {
        values = dialog.get_values();
    }

    // Show loading indicator
    dialog.set_value('item_preview', '<div class="text-center"><i class="fa fa-spinner fa-spin"></i> Loading items...</div>');

    let filters = build_filters(values);

    frappe.call({
        method: 'customize_erpnext.api.qr_label_print.get_filtered_items',
        args: {
            filters: filters
        },
        callback: function (r) {
            if (r.message) {
                // Store all filtered items for selection
                dialog.filtered_items = r.message;

                let items = r.message; // Show all items
                let select_all_text = `Select All (${r.message.length} items)`;

                let html = `
                    <div class="row" style="margin-bottom: 15px; align-items: center;">
                        <div class="col-md-4">
                            <div class="alert alert-info" style="margin-bottom: 0; padding: 8px 12px;">
                                <strong>Total Items Found:</strong> ${r.message.length}
                            </div>
                        </div>
                        <div class="col-md-4">
                            <label style="margin-bottom: 0; font-weight: normal;">
                                <input type="checkbox" id="select_all_items" style="margin-right: 8px;">
                                <strong>${select_all_text}</strong>
                            </label>
                        </div>
                     
                    </div>
                    <div style="max-height: 300px; overflow-y: auto;">
                        <table class="table table-bordered">
                            <thead>
                                <tr>
                                    <th width="50px">Select</th>
                                    <th>Item Code</th>
                                    <th>Item Name Detail</th>
                                    <th>Item Group</th>
                                    <th>Created</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                items.forEach((item, index) => {
                    html += `
                        <tr>
                            <td>
                                <input type="checkbox" class="item-checkbox" 
                                       data-item-code="${item.item_code}" 
                                       data-index="${index}" 
                                       style="margin: 0;">
                            </td>
                            <td>${item.item_code || ''}</td>
                            <td>${item.custom_item_name_detail || item.item_name || ''}</td>
                            <td>${item.item_group || ''}</td>
                            <td>${frappe.datetime.str_to_user(item.creation) || ''}</td>
                        </tr>
                    `;
                });

                html += '</tbody></table></div>';

                if (r.message.length === 0) {
                    html = '<div class="alert alert-warning">No items found with the current filters.</div>';
                    dialog.filtered_items = [];
                }

                dialog.set_value('item_preview', html);

                // Add event handlers for checkboxes and inline apply filter button after setting HTML
                setTimeout(() => {
                    setup_checkbox_handlers(dialog);

                    // Add handler for inline Apply Filter button
                    $(dialog.$wrapper).find('.apply-filter-inline').off('click').on('click', function () {
                        let current_values = dialog.get_values();
                        preview_items(current_values, dialog);
                    });
                }, 100);
            }
        }
    });
}

function build_filters(values) {
    let filters = {};

    if (values.filter_type === 'filter') {
        if (values.item_code) filters.item_code = values.item_code;
        if (values.custom_item_name_detail) filters.custom_item_name_detail = values.custom_item_name_detail;
        if (values.item_group) filters.item_group = values.item_group;
        if (values.created_after) filters.created_after = values.created_after;
    } else if (values.filter_type === 'recent') {
        let days = values.recent_days || 7;
        let date = frappe.datetime.add_days(frappe.datetime.get_today(), -days);
        filters.created_after = date;
    }

    if (values.limit) {
        filters.limit = Math.min(values.limit, 1000); // Max 1000 items
    }

    return filters;
}

function setup_checkbox_handlers(dialog) {
    // Select all functionality
    $(dialog.$wrapper).find('#select_all_items').off('change').on('change', function () {
        let is_checked = $(this).is(':checked');
        $(dialog.$wrapper).find('.item-checkbox').prop('checked', is_checked);

        // Show message when selecting all items
        if (is_checked && dialog.filtered_items && dialog.filtered_items.length > 0) {
            frappe.show_alert({
                message: __('Selected all {0} filtered items', [dialog.filtered_items.length]),
                indicator: 'blue'
            }, 3);
        }
    });

    // Individual checkbox functionality
    $(dialog.$wrapper).find('.item-checkbox').off('change').on('change', function () {
        let total_checkboxes = $(dialog.$wrapper).find('.item-checkbox').length;
        let checked_checkboxes = $(dialog.$wrapper).find('.item-checkbox:checked').length;

        // Update select all checkbox
        let select_all = $(dialog.$wrapper).find('#select_all_items');
        if (checked_checkboxes === 0) {
            select_all.prop('indeterminate', false);
            select_all.prop('checked', false);
        } else if (checked_checkboxes === total_checkboxes) {
            select_all.prop('indeterminate', false);
            select_all.prop('checked', true);
        } else {
            select_all.prop('indeterminate', true);
        }
    });
}

function add_selected_items_to_list(dialog) {
    let selected_checkboxes = $(dialog.$wrapper).find('.item-checkbox:checked');
    let select_all_checked = $(dialog.$wrapper).find('#select_all_items').is(':checked');

    // If "Select All" is checked, add all filtered items
    if (select_all_checked && dialog.filtered_items) {
        let added_items = [];
        dialog.filtered_items.forEach(item => {
            // Check if item is already in the selected list
            let exists = dialog.selected_items.find(selected_item => selected_item.item_code === item.item_code);
            if (!exists) {
                dialog.selected_items.push(item);
                added_items.push(item.item_code);
            }
        });

        if (added_items.length > 0) {
            frappe.show_alert({
                message: __('Added {0} items to print list', [added_items.length]),
                indicator: 'green'
            });

            // Uncheck all items
            $(dialog.$wrapper).find('.item-checkbox').prop('checked', false);
            $(dialog.$wrapper).find('#select_all_items').prop('checked', false).prop('indeterminate', false);

            // Update selected items display
            update_selected_items_display(dialog);
        } else {
            frappe.msgprint(__('All filtered items are already in the print list.'));
        }
        return;
    }

    // Handle individual selections
    if (selected_checkboxes.length === 0) {
        frappe.msgprint(__('Please select at least one item to add to the list.'));
        return;
    }

    let added_items = [];
    selected_checkboxes.each(function () {
        let item_code = $(this).data('item-code');
        let index = $(this).data('index');

        if (dialog.filtered_items && dialog.filtered_items[index]) {
            let item = dialog.filtered_items[index];

            // Check if item is already in the selected list
            let exists = dialog.selected_items.find(selected_item => selected_item.item_code === item_code);
            if (!exists) {
                dialog.selected_items.push(item);
                added_items.push(item_code);
            }
        }
    });

    if (added_items.length > 0) {
        frappe.show_alert({
            message: __('Added {0} items to print list', [added_items.length]),
            indicator: 'green'
        });

        // Uncheck selected items
        selected_checkboxes.prop('checked', false);
        $(dialog.$wrapper).find('#select_all_items').prop('checked', false).prop('indeterminate', false);

        // Update selected items display
        update_selected_items_display(dialog);
    } else {
        frappe.msgprint(__('All selected items are already in the print list.'));
    }
}

function clear_selected_items_list(dialog) {
    if (dialog.selected_items.length === 0) {
        frappe.msgprint(__('Print list is already empty.'));
        return;
    }

    frappe.confirm(
        __('Are you sure you want to clear all items from the print list?'),
        () => {
            dialog.selected_items = [];
            update_selected_items_display(dialog);
            frappe.show_alert({
                message: __('Print list cleared'),
                indicator: 'orange'
            });
        }
    );
}

function update_selected_items_display(dialog) {
    let html = '';

    if (dialog.selected_items.length === 0) {
        html = '<div class="alert alert-info">No items added to print list yet. Use "Add to List" button after selecting items above.</div>';
    } else {
        html = `
            <div class="alert alert-success">
                <strong>Items in Print List:</strong> ${dialog.selected_items.length}
            </div>
            <div style="max-height: 200px; overflow-y: auto;">
                <table class="table table-sm table-bordered">
                    <thead>
                        <tr>
                            <th width="30px">#</th>
                            <th>Item Code</th>
                            <th>Item Name Detail</th>
                            <th width="80px">Action</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        dialog.selected_items.forEach((item, index) => {
            html += `
                <tr>
                    <td>${index + 1}</td>
                    <td>${item.item_code || ''}</td>
                    <td>${item.custom_item_name_detail || item.item_name || ''}</td>
                    <td>
                        <button class="btn btn-xs btn-danger remove-item-btn" 
                                data-index="${index}" title="Remove">
                            <i class="fa fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table></div>';
    }

    dialog.set_value('selected_items_list', html);

    // Add remove button handlers
    setTimeout(() => {
        $(dialog.$wrapper).find('.remove-item-btn').off('click').on('click', function () {
            let index = $(this).data('index');
            dialog.selected_items.splice(index, 1);
            update_selected_items_display(dialog);
            frappe.show_alert({
                message: __('Item removed from print list'),
                indicator: 'orange'
            });
        });
    }, 100);
}

function generate_qr_labels_pdf(values, listview, dialog) {
    // Check if there are items in the print list
    if (!dialog.selected_items || dialog.selected_items.length === 0) {
        frappe.msgprint(__('Please add items to the print list first using the "Add to List" button.'));
        return;
    }

    // Find the Generate PDF button and show loading state
    let generate_btn = $(dialog.$wrapper).find('.modal-footer button:contains("Generate PDF")');
    let original_text = generate_btn.text();
    generate_btn.text(__('Generating...')).prop('disabled', true);

    // Extract item codes from selected items
    let item_codes = dialog.selected_items.map(item => item.item_code);

    frappe.call({
        method: 'customize_erpnext.api.qr_label_print.generate_qr_labels_pdf',
        args: {
            filters: {
                item_codes: item_codes
            }
        },
        callback: function (r) {
            // Restore button state
            generate_btn.text(original_text).prop('disabled', false);

            if (r.message) {
                // Download PDF
                download_pdf(r.message.pdf_data, r.message.filename);

                // Show success message
                frappe.show_alert({
                    message: __('QR Labels PDF generated successfully! ({0} items)', [r.message.items_count]),
                    indicator: 'green'
                }, 5);

                dialog.hide();
            } else {
                frappe.msgprint(__('Error generating PDF. Please try again.'));
            }
        },
        error: function (r) {
            // Restore button state
            generate_btn.text(original_text).prop('disabled', false);

            frappe.msgprint(__('Error generating PDF: {0}', [r.message || 'Unknown error']));
        }
    });
}

function download_pdf(pdf_data, filename) {
    // Convert base64 to blob
    let byteCharacters = atob(pdf_data);
    let byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    let byteArray = new Uint8Array(byteNumbers);
    let blob = new Blob([byteArray], { type: 'application/pdf' });

    // Create download link
    let url = window.URL.createObjectURL(blob);
    let a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();

    // Cleanup
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

// Helper function to handle selected items filter
frappe.listview_settings['Item'].get_indicator = function (doc) {
    if (doc.disabled) {
        return [__("Disabled"), "grey", "disabled,=,1"];
    } else if (doc.is_stock_item) {
        return [__("Stock Item"), "green", "is_stock_item,=,1"];
    } else {
        return [__("Non-Stock Item"), "orange", "is_stock_item,=,0"];
    }
};

// Quick Check Item functionality
function show_quick_check_item_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Quick Check Item'),
        fields: [

            {
                fieldname: 'search_type',
                fieldtype: 'Select',
                label: __('Search Type'),
                options: [
                    { value: 'qr_scan', label: __('QR Code Scan') },
                    { value: 'search_item', label: __('Search Item') }
                ],
                default: 'qr_scan',
                change: function () {
                    toggle_search_fields(dialog);
                }
            },
            {
                fieldname: 'search_input',
                fieldtype: 'Link',
                options: 'Item',
                label: __('Search Item'),
                depends_on: 'eval:doc.search_type=="search_item"',
                placeholder: __('Type to search for items...'),
                change: function () {
                    const selected_item = dialog.get_value('search_input');
                    if (selected_item) {
                        search_item_by_code(dialog, selected_item);
                    }
                }
            },
            {
                fieldname: 'qr_scan_area',
                fieldtype: 'HTML',
                label: __('QR Code Scanner'),
                depends_on: 'eval:doc.search_type=="qr_scan"',
                options: `
                    <div id="qr-scanner-container">
                        <div id="qr-reader" style="width: 100%; max-width: 600px; margin: 0 auto;"></div>
                        <div class="text-center mt-3">
                            <button class="btn btn-primary" id="start-qr-scan-btn">Start QR Scanning</button>
                            <button class="btn btn-secondary" id="stop-qr-scan-btn" style="display: none;">Stop QR Scanning</button>
                        </div>
                        <div id="qr-scan-result" class="mt-3"></div>
                    </div>
                `
            },
            {
                fieldtype: 'Section Break',
                label: __('Item Information')
            },
            {
                fieldname: 'item_info',
                fieldtype: 'HTML',
                label: __('Item Details'),
                options: '<div class="text-muted">Search for an item to see information</div>'
            },
            {
                fieldtype: 'Section Break',
                label: __('Stock Information')
            },
            {
                fieldname: 'stock_info',
                fieldtype: 'HTML',
                label: __('Stock Details'),
                options: '<div class="text-muted">Item information will show stock details</div>'
            },
            {
                fieldtype: 'Section Break',
                label: __('Transaction History')
            },
            {
                fieldname: 'transaction_history',
                fieldtype: 'HTML',
                label: __('Recent Transactions'),
                options: '<div class="text-muted">Item information will show transaction history</div>'
            }
        ],
        size: 'extra-large'
    });

    dialog.show();

    // Initialize dialog handlers
    setTimeout(() => {
        setup_quick_check_dialog_handlers(dialog);
        toggle_search_fields(dialog);
    }, 200);
}

function setup_quick_check_dialog_handlers(dialog) {
    console.log('Setting up quick check dialog handlers');

    // QR Scanner handlers
    $(document).off('click', '#start-qr-scan-btn').on('click', '#start-qr-scan-btn', function () {
        console.log('Start QR scan button clicked');
        start_qr_scanner(dialog);
    });

    $(document).off('click', '#stop-qr-scan-btn').on('click', '#stop-qr-scan-btn', function () {
        console.log('Stop QR scan button clicked');
        stop_qr_scanner(dialog);
    });

    // Manual search handlers - Link field will handle autocomplete automatically
}

function toggle_search_fields(dialog) {
    const search_type = dialog.get_value('search_type');

    // Show/hide QR scanner and auto-start if QR scan is selected
    const qr_container = $(dialog.$wrapper).find('#qr-scanner-container');
    const qr_field = dialog.get_field('qr_scan_area');
    if (search_type === 'qr_scan') {
        qr_container.show();
        if (qr_field) qr_field.toggle(true);

        // Auto-start QR scanner when QR scan is selected
        setTimeout(() => {
            start_qr_scanner(dialog);
        }, 500);
    } else {
        qr_container.hide();
        if (qr_field) qr_field.toggle(false);
        stop_qr_scanner(dialog);
    }

    // Clear previous results when switching search types
    dialog.set_value('item_info', '<div class="text-muted">Search for an item to see information</div>');
    dialog.set_value('stock_info', '<div class="text-muted">Item information will show stock details</div>');
    dialog.set_value('transaction_history', '<div class="text-muted">Item information will show transaction history</div>');

    // Refresh dialog layout
    dialog.refresh();
}

let qr_scanner = null;

function start_qr_scanner(dialog) {
    // Load HTML5-QRCode library if not available
    if (typeof Html5QrcodeScanner === 'undefined') {
        load_qr_scanner_library().then(() => {
            start_qr_scanner(dialog);
        }).catch(() => {
            frappe.msgprint({
                title: __('QR Scanner Not Available'),
                message: __('Failed to load QR Code scanning library. Please scan QR codes manually or use other search methods.'),
                indicator: 'orange'
            });
        });
        return;
    }

    const qr_reader_element = document.getElementById('qr-reader');
    if (!qr_reader_element) {
        frappe.msgprint(__('QR reader element not found. Please try again.'));
        return;
    }

    // Clear any previous scanner content
    $(qr_reader_element).empty();

    try {
        console.log('Creating QR scanner...');
        qr_scanner = new Html5QrcodeScanner(
            'qr-reader',
            {
                fps: 10,
                qrbox: { width: 250, height: 250 },
                aspectRatio: 1.0,
                rememberLastUsedCamera: true,
                preferredCamera: 'environment'  // Use back camera on mobile
            },
            false
        );
        console.log('QR scanner created successfully');

        console.log('Rendering QR scanner...');
        qr_scanner.render(
            function (decodedText, decodedResult) {
                console.log('QR code scanned:', decodedText);
                // Handle successful scan
                $('#qr-scan-result').html(`
                    <div class="alert alert-success">
                        <strong>QR Code Detected:</strong> ${decodedText}
                    </div>
                `);

                // Stop scanner
                stop_qr_scanner(dialog);

                // Search for the item
                search_item_by_qr_code(dialog, decodedText);
            },
            function (error) {
                // Handle scan failure - don't show error for every frame
                if (error.indexOf('QR code parse error') === -1) {
                    console.log('QR scan error:', error);
                }
            }
        );

        // Update button states
        $('#start-qr-scan-btn').hide();
        $('#stop-qr-scan-btn').show();

        console.log('QR scanner started successfully');

    } catch (error) {
        console.error('QR Scanner error:', error);
        frappe.msgprint(__('Error starting QR scanner: {0}', [error.message || 'Unknown error']));
    }
}

function stop_qr_scanner(dialog) {
    if (qr_scanner) {
        try {
            qr_scanner.clear();
            qr_scanner = null;
            console.log('QR scanner stopped successfully');
        } catch (error) {
            console.log('Error stopping QR scanner:', error);
        }
    }

    // Update button states
    $('#start-qr-scan-btn').show();
    $('#stop-qr-scan-btn').hide();
}

function search_item_by_qr_code(dialog, qr_code) {
    // QR code typically contains item_code
    dialog.set_value('item_code', qr_code);
    search_item_by_code(dialog, qr_code);
}

function search_item_info(dialog) {
    // This function is now used for QR code searches
    const item_code = dialog.get_value('item_code');
    if (!item_code) return;

    search_item_by_code(dialog, item_code);
}





function search_item_by_code(dialog, item_code) {
    // Show loading
    dialog.set_value('item_info', '<div class="text-center"><i class="fa fa-spinner fa-spin"></i> Loading item information...</div>');

    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Item',
            name: item_code
        },
        callback: function (r) {
            if (r.message) {
                display_item_information(dialog, r.message);
                load_stock_information(dialog, item_code);
                load_transaction_history(dialog, item_code);
            } else {
                dialog.set_value('item_info', '<div class="alert alert-warning">Item not found</div>');
            }
        },
        error: function (r) {
            dialog.set_value('item_info', '<div class="alert alert-danger">Error loading item information</div>');
        }
    });
}

function display_item_information(dialog, item) {
    // Check if device is mobile
    const isMobile = window.innerWidth <= 768;
    
    let html;
    if (isMobile) {
        // Mobile layout - show only Item Name Detail, Item Group, Stock UOM
        html = `
            <div class="card">
                <div class="card-body">
                    <div class="row">
                        <div class="col-12">
                            <p><strong>Item Name Detail:</strong> ${item.custom_item_name_detail || 'N/A'}</p>
                            <p><strong>Item Group:</strong> ${item.item_group || 'N/A'}</p>
                            <p><strong>Stock UOM:</strong> ${item.stock_uom || 'N/A'}</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    } else {
        // Desktop layout - show all fields
        html = `
            <div class="card">
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6">
                            <p><strong>Item Name:</strong> ${item.item_name || 'N/A'}</p>
                            <p><strong>Item Name Detail:</strong> ${item.custom_item_name_detail || 'N/A'}</p>
                        </div>
                        <div class="col-md-3">
                            <p><strong>Item Group:</strong> ${item.item_group || 'N/A'}</p>
                            <p><strong>Stock UOM:</strong> ${item.stock_uom || 'N/A'}</p>
                        </div>
                        <div class="col-md-3">
                            <p><strong>Is Stock Item:</strong> ${item.is_stock_item ? 'Yes' : 'No'}</p>
                            <p><strong>Status:</strong> ${item.disabled ? 'Disabled' : 'Active'}</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    dialog.set_value('item_info', html);
}

function load_stock_information(dialog, item_code) {
    dialog.set_value('stock_info', '<div class="text-center"><i class="fa fa-spinner fa-spin"></i> Loading stock information...</div>');

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Bin',
            filters: {
                'item_code': item_code
            },
            fields: ['warehouse', 'actual_qty', 'reserved_qty', 'planned_qty', 'projected_qty'],
            order_by: 'actual_qty desc'
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                let html = '<div class="table-responsive"><table class="table table-sm table-striped">';
                html += '<thead><tr><th>Warehouse</th><th>Available Qty</th><th>Reserved Qty</th><th>Planned Qty</th><th>Projected Qty</th></tr></thead><tbody>';

                r.message.forEach(bin => {
                    html += `<tr>
                        <td>${bin.warehouse}</td>
                        <td>${bin.actual_qty || 0}</td>
                        <td>${bin.reserved_qty || 0}</td>
                        <td>${bin.planned_qty || 0}</td>
                        <td>${bin.projected_qty || 0}</td>
                    </tr>`;
                });

                html += '</tbody></table></div>';

                dialog.set_value('stock_info', html);
            } else {
                dialog.set_value('stock_info', '<div class="alert alert-warning">No stock information found</div>');
            }
        },
        error: function (r) {
            dialog.set_value('stock_info', '<div class="alert alert-danger">Error loading stock information</div>');
        }
    });
}

function load_transaction_history(dialog, item_code) {
    dialog.set_value('transaction_history', '<div class="text-center"><i class="fa fa-spinner fa-spin"></i> Loading transaction history...</div>');

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Stock Ledger Entry',
            filters: {
                'item_code': item_code
            },
            fields: ['posting_date', 'posting_time', 'voucher_type', 'voucher_no', 'warehouse', 'actual_qty', 'qty_after_transaction'],
            order_by: 'posting_date desc, posting_time desc',
            limit: 20
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                let html = '<div class="table-responsive"><table class="table table-sm table-striped">';
                html += '<thead><tr><th>Date</th><th>Time</th><th>Voucher Type</th><th>Voucher No</th><th>Warehouse</th><th>Qty Change</th><th>Qty After</th></tr></thead><tbody>';

                r.message.forEach(entry => {
                    const qty_change = entry.actual_qty || 0;
                    const qty_class = qty_change > 0 ? 'text-success' : qty_change < 0 ? 'text-danger' : '';

                    html += `<tr>
                        <td>${entry.posting_date || ''}</td>
                        <td>${entry.posting_time || ''}</td>
                        <td>${entry.voucher_type || ''}</td>
                        <td><a href="/app/${entry.voucher_type.toLowerCase().replace(' ', '-')}/${entry.voucher_no}" target="_blank">${entry.voucher_no || ''}</a></td>
                        <td>${entry.warehouse || ''}</td>
                        <td class="${qty_class}">${qty_change}</td>
                        <td>${entry.qty_after_transaction || 0}</td>
                    </tr>`;
                });

                html += '</tbody></table></div>';

                dialog.set_value('transaction_history', html);
            } else {
                dialog.set_value('transaction_history', '<div class="alert alert-warning">No transaction history found</div>');
            }
        },
        error: function (r) {
            dialog.set_value('transaction_history', '<div class="alert alert-danger">Error loading transaction history</div>');
        }
    });
}

// Function to load QR scanner library
function load_qr_scanner_library() {
    return new Promise((resolve, reject) => {
        if (typeof Html5QrcodeScanner !== 'undefined') {
            resolve();
            return;
        }

        // Show loading message
        frappe.show_alert({
            message: __('Loading scanner library...'),
            indicator: 'blue'
        });

        // Try to load from CDN
        const script = document.createElement('script');
        script.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
        script.onload = function () {
            if (typeof Html5QrcodeScanner !== 'undefined') {
                frappe.show_alert({
                    message: __('Scanner library loaded successfully'),
                    indicator: 'green'
                });
                resolve();
            } else {
                reject('Library loaded but Html5QrcodeScanner not available');
            }
        };
        script.onerror = function () {
            reject('Failed to load QR scanner library');
        };
        document.head.appendChild(script);
    });
}

// Export Master Data - Item - Attribute function
function export_master_data_item_attribute() {
    frappe.show_alert({
        message: __('Generating Excel file...'),
        indicator: 'blue'
    });

    frappe.call({
        method: 'customize_erpnext.api.utilities.export_master_data_item_attribute',
        callback: function(r) {
            if (r.message) {
                // Convert base64 to blob
                const byteCharacters = atob(r.message.file_data);
                const byteNumbers = new Array(byteCharacters.length);
                for (let i = 0; i < byteCharacters.length; i++) {
                    byteNumbers[i] = byteCharacters.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);
                const blob = new Blob([byteArray], { 
                    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
                });

                // Create download link
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = r.message.filename;
                document.body.appendChild(a);
                a.click();

                // Cleanup
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                // Show success message
                frappe.show_alert({
                    message: __('Excel file downloaded successfully! ({0} items)', [r.message.items_count]),
                    indicator: 'green'
                }, 5);
            }
        },
        error: function(r) {
            frappe.msgprint(__('Error generating Excel file: {0}', [r.message || 'Unknown error']));
        }
    });
}
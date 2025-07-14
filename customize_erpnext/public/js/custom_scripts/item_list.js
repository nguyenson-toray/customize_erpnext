frappe.listview_settings['Item'] = {
    onload: function (listview) {
        // Add "Print QR Labels" button to Item List
        listview.page.add_inner_button(__('Print QR Labels'), function () {
            show_qr_label_dialog(listview);
        }, __('Actions'));
    }
};

function show_qr_label_dialog(listview) {
    let dialog = new frappe.ui.Dialog({
        title: __('Print QR Labels - A4 - Tommy No.138'),
        fields: [
            {
                fieldtype: 'Section Break',
                label: __('Filter Options')
            },
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
                description: __('Maximum number of items to query.')
            },
            {
                fieldtype: 'Section Break',
                label: __('Custom Filters'),
                depends_on: 'eval:doc.filter_type=="filter"'
            },
            {
                fieldname: 'item_code',
                fieldtype: 'Data',
                label: __('Item Code (Contains)'),
                depends_on: 'eval:doc.filter_type=="filter"'
            },
            {
                fieldname: 'cb2',
                fieldtype: 'Column Break',
                depends_on: 'eval:doc.filter_type=="filter"'
            },
            {
                fieldname: 'custom_item_name_detail',
                fieldtype: 'Data',
                label: __('Item Name Detail (Contains)'),
                depends_on: 'eval:doc.filter_type=="filter"'
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
                fieldname: 'cb3',
                fieldtype: 'Column Break',
                depends_on: 'eval:doc.filter_type=="filter"'
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
                label: __('Preview Items')
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
        primary_action_label: __('Generate PDF'),
        primary_action: function (values) {
            generate_qr_labels_pdf(values, listview, dialog);
        },
        secondary_action_label: __('Preview Items'),
        secondary_action: function (values) {
            // Always get fresh values from dialog
            let current_values = dialog.get_values();
            preview_items(current_values, dialog);
        }
    });

    // Add custom buttons
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

    // Add "Add to List" button
    setTimeout(() => {
        let add_btn = dialog.page.add_action_item(__('Add to List'), function () {
            add_selected_items_to_list(dialog);
        });
        add_btn.addClass('btn-warning');

        // Add "Clear List" button  
        let clear_btn = dialog.page.add_action_item(__('Clear List'), function () {
            clear_selected_items_list(dialog);
        });
        clear_btn.addClass('btn-danger');
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
                    <div class="alert alert-info">
                        <strong>Total Items Found:</strong> ${r.message.length}
                    </div>
                    <div style="margin-bottom: 10px;">
                        <label style="margin-right: 15px;">
                            <input type="checkbox" id="select_all_items" style="margin-right: 5px;">
                            <strong>${select_all_text}</strong>
                        </label>
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

                // Add event handlers for checkboxes after setting HTML
                setTimeout(() => {
                    setup_checkbox_handlers(dialog);
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

    // Show loading
    dialog.set_primary_action(__('Generating...'), null);

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
            dialog.set_primary_action(__('Generate PDF'), function () {
                generate_qr_labels_pdf(values, listview, dialog);
            });

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
            dialog.set_primary_action(__('Generate PDF'), function () {
                generate_qr_labels_pdf(values, listview, dialog);
            });

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
frappe.ui.form.on('Stock Entry', {
    refresh: function (frm) {
        // Only run this for Material Transfer for Manufacture type
        if (frm.doc.purpose === "Material Transfer for Manufacture" && frm.doc.work_order) {
            check_existing_material_transfers(frm);
        }

        // Setup invoice selector for Material Issue
        if (frm.doc.stock_entry_type === "Material Issue") {
            setup_invoice_selector(frm);
        }

        // Setup warehouse column visibility based on stock entry type
        setup_warehouse_column_visibility(frm);
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
        // Validate empty invoice numbers first
        validate_invoice_numbers(frm);

        // Trim parent fields first
        trim_parent_fields(frm);

        // Aggregate invoice numbers from child table to parent
        aggregate_invoice_numbers(frm);

        // Sync invoice fields to child table after trimming parent fields
        sync_fields_to_child_table(frm);
    },

    stock_entry_type: function (frm) {
        // Setup warehouse column visibility when stock entry type changes
        setup_warehouse_column_visibility(frm);
    }
});

// Function to validate invoice numbers in items table
function validate_invoice_numbers(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        return;
    }

    let empty_invoice_rows = [];

    frm.doc.items.forEach(function (item, index) {
        if (!item.custom_invoice_number || !item.custom_invoice_number.trim()) {
            empty_invoice_rows.push({
                row_number: index + 1,
                item_code: item.item_code || 'Unknown Item'
            });
        }
    });

    if (empty_invoice_rows.length > 0) {
        let error_message = __('The following rows have empty Invoice Number:');
        error_message += '<ul>';
        empty_invoice_rows.forEach(function (row) {
            error_message += `<li>Row ${row.row_number}: ${row.item_code}</li>`;
        });
        error_message += '</ul>';
        error_message += __('Please fill in all Invoice Numbers before saving.');
        error_message += __('</br>Fill "yy-mm-dd:Unknow" if not exit Invoice Number.');
        frappe.throw({
            title: __('Validation Error'),
            message: error_message
        });
    }
}

// Function to trim parent document fields
function trim_parent_fields(frm) {
    // List of fields to trim with their formatting options
    let fields_to_trim = [
        {
            field: 'custom_material_issue_purpose',
            camel_case: false
        },
        {
            field: 'custom_line',
            camel_case: true
        },
        {
            field: 'custom_fg_qty',
            camel_case: false
        },
        {
            field: 'custom_fg_style',
            camel_case: true
        },
        {
            field: 'custom_fg_color',
            camel_case: true
        },
        {
            field: 'custom_fg_size',
            camel_case: true
        },
        {
            field: 'custom_note',
            camel_case: false
        },
        {
            field: 'custom_no',
            camel_case: false
        }
    ];

    // Function để chuyển đổi text sang Camel Case
    function toCamelCase(str) {
        return str.toLowerCase().replace(/\b\w/g, function (match) {
            return match.toUpperCase();
        });
    }

    // Function để xử lý giá trị field
    function processFieldValue(value, apply_camel_case = false) {
        if (!value) return value;

        // Trim toàn bộ giá trị
        let processed_value = value.toString().trim();
        // Thay thế nhiều khoảng trắng bằng một khoảng trắng
        processed_value = processed_value.replace(/\s+/g, ' ');

        // Áp dụng Camel Case nếu được yêu cầu
        if (apply_camel_case && processed_value) {
            // Chỉ áp dụng Camel Case cho text, không áp dụng cho numbers, codes
            if (!/^[0-9\-\.]+$/.test(processed_value)) {
                processed_value = toCamelCase(processed_value);
            }
        }

        return processed_value;
    }

    let updated_fields = [];

    fields_to_trim.forEach(function (field_info) {
        let current_value = frm.doc[field_info.field];

        if (current_value) {
            let processed_value = processFieldValue(current_value, field_info.camel_case);

            // Chỉ update nếu có thay đổi
            if (current_value !== processed_value) {
                frm.set_value(field_info.field, processed_value);
                updated_fields.push(field_info.field);
                frappe.show_alert({
                    message: __('Trimmed and formatted field: {0}', [processed_value]),
                    indicator: 'green'
                });

            }
        }
    });

    if (updated_fields.length > 0) {
        console.log(`Trimmed and formatted parent fields: ${updated_fields.join(', ')}`);
    }
}

// Function to aggregate invoice numbers from items table
function aggregate_invoice_numbers(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        return;
    }

    // Collect all unique invoice numbers from items
    let invoice_numbers = [];

    frm.doc.items.forEach(function (item) {
        if (item.custom_invoice_number && item.custom_invoice_number.trim()) {
            let invoice_num = item.custom_invoice_number.trim();
            // Only add if not already in the array (avoid duplicates)
            if (invoice_numbers.indexOf(invoice_num) === -1) {
                invoice_numbers.push(invoice_num);
            }
        }
    });

    // Join with "; " separator and set to parent field
    let aggregated_invoices = invoice_numbers.join("; ");

    // Only update if there's a change to avoid unnecessary triggers
    if (frm.doc.custom_invoice_number !== aggregated_invoices) {
        frm.set_value('custom_invoice_number', aggregated_invoices);

        // Show info message if invoices were aggregated
        if (aggregated_invoices && invoice_numbers.length > 0) {
            console.log(`Aggregated ${invoice_numbers.length} invoice numbers: ${aggregated_invoices}`);
        }
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
                        <h4><i class="fa fa-exclamation-triangle"></i> Warning: There are ${existing_entries.length} material transfer entries for this Work Order!</h4>
                        <div style="margin-top: 10px;">
                            <table class="table table-bordered table-condensed" style="margin-bottom: 5px;">
                                <thead>
                                    <tr>
                                        <th>Transfer Entry</th>
                                        <th>Status</th>
                                        <th>Last Updated</th>
                                        <th>Created By</th>
                                    </tr>
                                </thead>
                                <tbody>`;

                existing_entries.forEach(entry => {
                    let status = "";
                    if (entry.docstatus === 0) {
                        status = '<span class="indicator orange">Draft</span>';
                    } else if (entry.docstatus === 1) {
                        status = '<span class="indicator green">Submitted</span>';
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
                                    <i class="fa fa-external-link"></i> View Work Order
                                </a>
                                <a href="/app/stock-entry?filters=[['Stock Entry','work_order','=','${frm.doc.work_order}'],['Stock Entry','purpose','=','Material Transfer for Manufacture']]" target="_blank" class="btn btn-sm btn-info">
                                    <i class="fa fa-list"></i> View all material transfer entries
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
                        message: __('There is a material transfer slip submitted for this Work Order.!'),
                        indicator: 'red'
                    }, 10);
                }
            } else {
                // No existing transfers, show positive confirmation
                frm.dashboard.clear_comment();
                frm.dashboard.add_comment(`
                    <div class="alert alert-info">
                        <i class="fa fa-info-circle"></i> 
                        There are no material transfer orders for this Work Order.
                        <div style="margin-top: 10px;">
                            <a href="/app/work-order/${frm.doc.work_order}" target="_blank" class="btn btn-sm btn-info">
                                <i class="fa fa-external-link"></i> View Work Order
                            </a>
                        </div>
                    </div>
                `, "blue", true);
            }

            // Show current status
            let status_html = '';
            if (frm.doc.docstatus === 0) {
                status_html = '<span class="indicator orange">Current status: Draft</span>';
            } else if (frm.doc.docstatus === 1) {
                status_html = '<span class="indicator green">Current status: Submitted</span>';
            } else if (frm.doc.docstatus === 2) {
                status_html = '<span class="indicator red">Current status: Cancelled</span>';
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
            field: 'custom_fg_qty',
            value: frm.doc.custom_fg_qty,
            label: 'FG Qty'
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
                // Chỉ update nếu field chưa có giá trị hoặc khác với giá trị parent
                if (!row[field_info.field] || row[field_info.field] !== field_info.value) {
                    frappe.model.set_value(row.doctype, row.name, field_info.field, field_info.value);
                    updated_count++;
                }
            });

            if (updated_count > 0) {
                total_updated += updated_count;
                console.log(`Updated ${updated_count} rows for ${field_info.label}: ${field_info.value}`);
            }
        }
    });

    if (total_updated > 0) {
        frm.refresh_field('items');
        frappe.show_alert({
            message: __('Automatically updated {0} fields in detail table', [total_updated]),
            indicator: 'green'
        }, 5);
    }
}

// Function to setup invoice selector click handlers
function setup_invoice_selector(frm) {
    // Prevent multiple dialogs
    if (frm.invoice_dialog_open) {
        return;
    }

    // Wait for grid to be ready
    setTimeout(() => {
        // Remove existing handlers first
        frm.fields_dict.items.grid.wrapper.off('click', 'input[data-fieldname="custom_invoice_number"]');
        frm.fields_dict.items.grid.wrapper.off('focus', 'input[data-fieldname="custom_invoice_number"]');

        // Attach click handler to grid
        frm.fields_dict.items.grid.wrapper.on('click', 'input[data-fieldname="custom_invoice_number"]', function (e) {
            e.preventDefault();
            e.stopPropagation();

            // Prevent multiple dialogs
            if (frm.invoice_dialog_open) {
                return;
            }

            // Get the row index from the clicked element
            let $row = $(this).closest('.grid-row');
            let row_index = $row.attr('data-idx') - 1;
            let row = frm.doc.items[row_index];

            if (!row) return;

            // Only show dialog if item is selected
            if (!row.item_code) {
                frappe.msgprint(__('Please select an item first'));
                return;
            }
            if (!row.s_warehouse) {
                frappe.msgprint(__('Please select a warehouse'));
                return;
            }

            // Show invoice selection dialog
            show_invoice_selection_dialog(frm, row);
        });

        // Also handle focus event
        frm.fields_dict.items.grid.wrapper.on('focus', 'input[data-fieldname="custom_invoice_number"]', function (e) {
            e.preventDefault();
            e.stopPropagation();

            // Prevent multiple dialogs
            if (frm.invoice_dialog_open) {
                return;
            }

            // Get the row index from the clicked element
            let $row = $(this).closest('.grid-row');
            let row_index = $row.attr('data-idx') - 1;
            let row = frm.doc.items[row_index];

            if (!row) return;

            // Only show dialog if item is selected
            if (!row.item_code) {
                frappe.msgprint(__('Please select an item first'));
                return;
            }

            // Show invoice selection dialog
            show_invoice_selection_dialog(frm, row);
        });
    }, 500);
}

// Stock Entry Detail form handlers
frappe.ui.form.on('Stock Entry Detail', {
    items_add: function (frm, cdt, cdn) {
        // Re-setup invoice selector when new row is added
        if (frm.doc.stock_entry_type === "Material Issue") {
            setTimeout(() => {
                setup_invoice_selector(frm);
            }, 100);
        }
    },

    item_code: function (frm, cdt, cdn) {
        // Re-setup invoice selector when item is changed
        if (frm.doc.stock_entry_type === "Material Issue") {
            setTimeout(() => {
                setup_invoice_selector(frm);
            }, 100);
        }
    },

    custom_invoice_number: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.custom_invoice_number) {
            // Store original value
            let original_value = row.custom_invoice_number;

            // Trim and clean the text
            let cleaned_value = row.custom_invoice_number.trim();
            // Replace multiple spaces with single space
            cleaned_value = cleaned_value.replace(/\s+/g, ' ');

            // Check if there was any change
            if (original_value !== cleaned_value) {
                // Set the cleaned value back to the row
                frappe.model.set_value(cdt, cdn, 'custom_invoice_number', cleaned_value);

                // Show alert only when there was a change
                frappe.show_alert({
                    message: __('Invoice number has been cleaned: "{0}" → "{1}"', [original_value, cleaned_value]),
                    indicator: 'blue'
                }, 5);
            }
        }

        // Trigger aggregation with a slight delay
        setTimeout(() => {
            aggregate_invoice_numbers(frm);
        }, 100);
    }
});

// Function to show invoice selection dialog
function show_invoice_selection_dialog(frm, row) {
    // Mark dialog as open
    frm.invoice_dialog_open = true;

    // Fetch available stock by invoice
    console.log('Fetching available stock by invoice for item:', row.item_code, 'in warehouse:', row.s_warehouse || frm.doc.from_warehouse);
    frappe.call({
        method: 'customize_erpnext.api.get_stock_by_invoice.get_stock_by_invoice',
        args: {
            item_code: row.item_code,
            warehouse: row.s_warehouse || frm.doc.from_warehouse,
            company: frm.doc.company
        },
        callback: function (r) {
            console.log('Available stock by invoice:', r.message);
            if (!r.message || r.message.length === 0) {
                frm.invoice_dialog_open = false;
                frappe.msgprint(__('No stock available for this item with invoice information'));
                return;
            }

            // Calculate total available quantity and determine default quantity
            let total_available_qty = r.message.reduce((sum, item) => sum + (item.available_qty || 0), 0);
            let default_qty = row.qty > 0 ? row.qty : total_available_qty;

            // Create dialog with grid and quantity field
            let dialog = new frappe.ui.Dialog({
                title: __('Select Invoice(s) for Item:<br>{0}<br>{1}', [row.item_code, row.custom_item_name_detail]),
                fields: [
                    {
                        fieldname: 'quantity_info',
                        fieldtype: 'HTML',
                        options: `<div class="alert alert-info" style="margin-bottom: 15px;">
                            <strong>Current Row Quantity:</strong> ${row.qty || 0}<br>
                            <strong>Total Available Stock:</strong> ${total_available_qty}
                        </div>`
                    },
                    {
                        fieldname: 'selected_quantity',
                        fieldtype: 'Float',
                        label: __('Quantity to Use'),
                        default: default_qty,
                        reqd: 1,
                        description: __('Maximum available quantity: {0}', [total_available_qty])
                    },
                    {
                        fieldname: 'invoice_selection',
                        fieldtype: 'Table',
                        label: __('Available Stock by Invoice (Select multiple)'),
                        cannot_add_rows: true,
                        cannot_delete_rows: true,
                        in_place_edit: false,
                        data: r.message,
                        fields: [
                            {
                                fieldname: 'invoice_number',
                                fieldtype: 'Data',
                                label: __('Invoice Number'),
                                read_only: 1,
                                in_list_view: 1,
                                columns: 2
                            },
                            {
                                fieldname: 'custom_item_name_detail',
                                fieldtype: 'Data',
                                label: __('Item Detail'),
                                read_only: 1,
                                in_list_view: 1,
                                columns: 3
                            },
                            {
                                fieldname: 'available_qty',
                                fieldtype: 'Float',
                                label: __('Available Qty'),
                                read_only: 1,
                                in_list_view: 1,
                                columns: 1
                            },
                            {
                                fieldname: 'stock_uom',
                                fieldtype: 'Data',
                                label: __('UOM'),
                                read_only: 1,
                                in_list_view: 1,
                                columns: 1
                            },
                            {
                                fieldname: 'warehouse',
                                fieldtype: 'Link',
                                options: 'Warehouse',
                                label: __('Warehouse'),
                                read_only: 1,
                                in_list_view: 1,
                                columns: 1
                            },
                            {
                                fieldname: 'receive_date',
                                fieldtype: 'Date',
                                label: __('Date'),
                                read_only: 1,
                                in_list_view: 1,
                                columns: 1
                            }
                        ]
                    }
                ],
                size: 'extra-large',
                primary_action_label: __('Add Selected Items'),
                primary_action: function (values) {
                    // Find selected rows
                    let selected_rows = values.invoice_selection.filter(inv => inv.__checked);

                    if (selected_rows.length === 0) {
                        frappe.msgprint(__('Please select at least one invoice'));
                        return;
                    }

                    // Validate selected quantity
                    let selected_qty = values.selected_quantity;
                    if (!selected_qty || selected_qty <= 0) {
                        frappe.msgprint(__('Please enter a valid quantity'));
                        return;
                    }

                    if (selected_qty > total_available_qty) {
                        frappe.msgprint(__('Selected quantity ({0}) cannot exceed available stock ({1})', [selected_qty, total_available_qty]));
                        return;
                    }

                    // Process multiple selections with selected quantity
                    process_multiple_invoice_selection(frm, row, selected_rows, selected_qty);

                    dialog.hide();
                    frm.invoice_dialog_open = false;
                },
                secondary_action_label: __('Cancel'),
                secondary_action: function () {
                    dialog.hide();
                    frm.invoice_dialog_open = false;
                }
            });

            dialog.show();
        },
        error: function () {
            frm.invoice_dialog_open = false;
        }
    });
}

// Function to process multiple invoice selections
function process_multiple_invoice_selection(frm, original_row, selected_invoices, selected_qty) {
    let added_count = 0;
    let updated_count = 0;
    let remaining_qty = selected_qty;

    // Sort invoices by date (oldest first) to prioritize older invoices
    selected_invoices.sort(function (a, b) {
        let dateA = new Date(a.receive_date || '1900-01-01');
        let dateB = new Date(b.receive_date || '1900-01-01');
        return dateA - dateB;
    });

    selected_invoices.forEach(function (selected, index) {
        // Use FIFO (First In, First Out) - prioritize older invoices
        // Use the minimum of remaining quantity or available quantity for this invoice
        let qty_to_use = Math.min(remaining_qty, selected.available_qty);

        if (qty_to_use <= 0) return; // Skip if no quantity to use

        remaining_qty -= qty_to_use;

        if (index === 0) {
            // First selection: update the current row (keep item_code and warehouse, update invoice and qty)
            frappe.model.set_value(original_row.doctype, original_row.name, 'custom_invoice_number', selected.invoice_number);
            frappe.model.set_value(original_row.doctype, original_row.name, 'qty', qty_to_use);

            // Set warehouse if not already set
            if (!original_row.s_warehouse && selected.warehouse) {
                frappe.model.set_value(original_row.doctype, original_row.name, 's_warehouse', selected.warehouse);
            }

            updated_count++;
        } else {
            // Additional selections: create new rows
            let new_row = frm.add_child('items');

            // Copy basic item data from original row
            frappe.model.set_value(new_row.doctype, new_row.name, 'item_code', original_row.item_code);
            frappe.model.set_value(new_row.doctype, new_row.name, 's_warehouse', original_row.s_warehouse || selected.warehouse);

            // Set invoice-specific data
            frappe.model.set_value(new_row.doctype, new_row.name, 'custom_invoice_number', selected.invoice_number);
            frappe.model.set_value(new_row.doctype, new_row.name, 'qty', qty_to_use);

            added_count++;
        }
    });

    // Refresh the grid
    frm.refresh_field('items');

    // Trigger aggregation after all rows are updated
    setTimeout(() => {
        aggregate_invoice_numbers(frm);
    }, 200);

    // Show success message
    let message = '';
    if (updated_count > 0 && added_count > 0) {
        message = __('Updated current row and added {0} new items with selected invoices (Total qty: {1})', [added_count, selected_qty]);
    } else if (updated_count > 0) {
        message = __('Updated current row with selected invoice (Qty: {0})', [selected_qty]);
    } else if (added_count > 0) {
        message = __('Added {0} new items with selected invoices (Total qty: {1})', [added_count, selected_qty]);
    }

    frappe.show_alert({
        message: message,
        indicator: 'green'
    }, 5);
}

// Function to setup warehouse column visibility based on stock entry type
function setup_warehouse_column_visibility(frm) {
    if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
        return;
    }

    setTimeout(() => {
        let grid = frm.fields_dict.items.grid;

        if (frm.doc.stock_entry_type === "Material Issue") {
            // For Material Issue: Show s_warehouse, hide t_warehouse
            if (grid.docfields) {
                grid.docfields.forEach(function (field) {
                    if (field.fieldname === 's_warehouse') {
                        field.in_list_view = 1;
                        field.columns = 1;
                    } else if (field.fieldname === 't_warehouse') {
                        field.in_list_view = 0;
                        field.columns = 0;
                    }
                });
            }
        } else if (frm.doc.stock_entry_type === "Material Receipt") {
            // For Material Receipt: Show t_warehouse, hide s_warehouse
            if (grid.docfields) {
                grid.docfields.forEach(function (field) {
                    if (field.fieldname === 't_warehouse') {
                        field.in_list_view = 1;
                        field.columns = 1;
                    } else if (field.fieldname === 's_warehouse') {
                        field.in_list_view = 0;
                        field.columns = 0;
                    }
                });
            }
        }

        // Refresh the grid to apply changes
        if (grid.refresh) {
            grid.refresh();
        }
        frm.refresh_field('items');
    }, 100);
}
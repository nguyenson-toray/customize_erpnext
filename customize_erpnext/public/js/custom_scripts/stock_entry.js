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
            field: 'custom_invoice_number',
            value: frm.doc.custom_invoice_number,
            label: 'Invoice Number'
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
        // {
        //     field: 'custom_inv_lot',
        //     value: frm.doc.custom_inv_lot,
        //     label: 'INV Lot'
        // },
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
                if (!row[field_info.field]) {
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
                                columns: 4
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
                                columns: 2
                            },
                            {
                                fieldname: 'receive_date',
                                fieldtype: 'Date',
                                label: __('Receive Date'),
                                read_only: 1,
                                in_list_view: 1,
                                columns: 2
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

            // Make the dialog wider
            dialog.$wrapper.find('.modal-dialog').css('max-width', '900px');

            // Handle dialog close event
            dialog.$wrapper.on('hidden.bs.modal', function () {
                frm.invoice_dialog_open = false;
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

    selected_invoices.forEach(function (selected, index) {
        // Calculate quantity to use for this invoice (proportional to available quantity)
        let total_selected_available = selected_invoices.reduce((sum, inv) => sum + (inv.available_qty || 0), 0);
        let proportional_qty = (selected.available_qty / total_selected_available) * selected_qty;

        // Use the minimum of proportional quantity or remaining quantity
        let qty_to_use = Math.min(proportional_qty, remaining_qty, selected.available_qty);

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
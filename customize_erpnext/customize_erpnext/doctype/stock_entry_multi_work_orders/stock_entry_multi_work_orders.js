// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on('Stock Entry Multi Work Orders Table Material', {
    required_qty: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Initialize tracking object if not exists
        if (!frm._original_required_qtys) {
            frm._original_required_qtys = {};
        }

        // Set original value if not already set
        if (frm._original_required_qtys[row.name] === undefined) {
            frm._original_required_qtys[row.name] = row.required_qty;
        }

        // Check if new required_qty is less than original
        if (row.required_qty < frm._original_required_qtys[row.name]) {
            // Reset to original value
            frappe.model.set_value(cdt, cdn, 'required_qty', frm._original_required_qtys[row.name]);

            // Show notification
            frappe.show_alert({
                message: __('Cannot enter quantity lower than original value of {0}!', [frm._original_required_qtys[row.name]]),
                indicator: 'red'

            }, 5);

            // frappe.msgprint({
            //     title: __('Not Allowed'),
            //     message: __('You cannot enter a quantity lower than the original quantity ({0})!', [frm._original_required_qtys[row.name]]),
            //     indicator: 'red'
            // });
        }
    }
});




frappe.ui.form.on("Stock Entry Multi Work Orders", {
    // Thêm validation before_submit
    // Thêm validation before_submit
    before_submit: function (frm) {
        // Ngăn submit mặc định
        frappe.validated = false;

        if (!frm.doc.work_orders || frm.doc.work_orders.length === 0) {
            frappe.msgprint(__('No work orders selected'));
            return;
        }

        // Lấy danh sách work orders
        const work_orders = frm.doc.work_orders.map(row => row.work_order);

        // Kiểm tra có Stock Entry nào đã tồn tại không
        frappe.call({
            method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.check_existing_draft_stock_entries',
            args: {
                'work_orders': work_orders
            },
            freeze: true,
            freeze_message: __('Checking for existing Stock Entries...'),
            callback: function (response) {
                if (response.message && response.message.length > 0) {
                    // Có Stock Entry đã tồn tại
                    let message = __('The following Work Orders already have Stock Entries:') + '<br><br>';
                    let existing_work_orders = [];

                    response.message.forEach(entry => {
                        existing_work_orders.push(entry.work_order);
                        message += `${entry.work_order}: <a href="/app/stock-entry/${entry.stock_entry}" target="_blank">${entry.stock_entry}</a><br>`;
                    });

                    // Lọc ra các work orders chưa có Stock Entry
                    let new_work_orders = work_orders.filter(wo => !existing_work_orders.includes(wo));

                    if (new_work_orders.length > 0) {
                        message += '<br>' + __('Do you want to submit and create Stock Entries for the remaining Work Orders?');

                        frappe.confirm(
                            message,
                            function () {
                                // User clicked Yes - submit và tạo Stock Entries cho các work orders còn lại
                                frappe.validated = true;
                                frm.save('Submit', function () {
                                    create_new_stock_entries(frm, new_work_orders);
                                });
                            },
                            function () {
                                // User clicked No - không làm gì
                                frappe.msgprint(__('Submission cancelled'));
                            }
                        );
                    } else {
                        frappe.msgprint({
                            title: __('Cannot Submit'),
                            indicator: 'red',
                            message: __('All selected Work Orders already have Stock Entries.') + '<br><br>' + message
                        });
                    }
                } else {
                    // Không có Stock Entry nào tồn tại - tạo xác nhận và tiến hành
                    frappe.confirm(
                        __('This will submit the document and create {0} separate Stock Entries, one for each Work Order. Continue?', [work_orders.length]),
                        function () {
                            // User clicked Yes - submit và tạo Stock Entries
                            frappe.validated = true;
                            frm.save('Submit', function () {
                                create_new_stock_entries(frm, work_orders);
                            });
                        },
                        function () {
                            // User clicked No - không làm gì
                            frappe.msgprint(__('Submission cancelled'));
                        }
                    );
                }
            }
        });

        // Luôn return false để ngăn submit mặc định
        return false;
    },
    on_submit: function (frm) {
        // Gọi function tạo stock entries khi form được submit
        create_stock_entries(frm);
    },
    refresh(frm) {
        // // Add a custom handler for the delete button
        // frm.add_custom_button(__('Refresh Materials'), function () {
        //     refresh_materials(frm);
        // });

        // Add a direct handler for the delete button
        frm.fields_dict['work_orders'].grid.grid_buttons.find('.grid-delete-row').click(function () {
            setTimeout(function () {
                refresh_materials(frm);
            }, 350);
        });

        if (frm.doc.item_template) {
            // Only run this if item_template is set and color list needs to be populated
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_colors_for_template',
                args: {
                    item_template: frm.doc.item_template
                },
                callback: function (response) {
                    if (response.message && Array.isArray(response.message) && response.message.length > 0) {
                        // Set the options for the Color field
                        frm.set_df_property('color', 'options', response.message.join('\n'));
                        // This will keep the selected color if it exists in the options
                        frm.refresh_field('color');
                    }
                }
            });
        }
        // Thêm nút tạo Stock Entry
        // frm.add_custom_button(__('Create Stock Entry'), function () {
        //     create_stock_entries(frm);
        // }).addClass('btn-primary');

        // Store original required_qty values
        if (!frm._original_required_qtys) {
            frm._original_required_qtys = {};
            if (frm.doc.materials && frm.doc.materials.length) {
                frm.doc.materials.forEach(function (item) {
                    if (item.name && item.required_qty) {
                        frm._original_required_qtys[item.name] = item.required_qty;
                    }
                });
            }
        }

    },
    // Get Color After choosing Item Template
    item_template(frm) {
        if (frm.doc.item_template) {
            // Clear the color field first
            frm.set_value('color', '');
            frm.clear_table('work_orders');
            frm.clear_table('materials');
            frm.refresh_fields(['work_orders', 'materials']);

            frm.set_df_property('color', 'options', ''); // Clear options first 
            // Fetch available colors using the server-side method
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_colors_for_template',
                args: {
                    item_template: frm.doc.item_template
                },
                freeze: true,
                callback: function (response) {
                    if (response.message && Array.isArray(response.message) && response.message.length > 0) {
                        // Set the options for the Color field
                        frm.set_df_property('color', 'options', response.message.join('\n'));
                        frm.refresh_field('color');
                    } else {
                        frappe.msgprint(__('No color variants found for this template'));
                    }
                }
            });
        }
    },

    // Get Work Order After choosing Color:
    color: function (frm) {
        if (frm.doc.item_template && frm.doc.color) {
            // Clear existing rows
            frm.clear_table('work_orders');
            frm.clear_table('materials');

            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_related_work_orders',
                args: {
                    'item_template': frm.doc.item_template,
                    'color': frm.doc.color
                },
                freeze: true,
                callback: function (response) {
                    if (response.message) {
                        // Add work orders to the table
                        if (response.message.work_orders && Array.isArray(response.message.work_orders)) {
                            response.message.work_orders.forEach(function (wo) {
                                let row = frm.add_child('work_orders');
                                row.work_order = wo.work_order;
                                row.item_code = wo.item_code;
                                row.item_name = wo.item_name;
                                row.item_name_detail = wo.item_name_detail;
                                row.qty_to_manufacture = wo.qty_to_manufacture;
                                row.work_order_status = wo.work_order_status;
                                // Update notification and maintain consistent status
                                if (wo.work_order_status != 'Not Started') {
                                    frappe.show_alert({
                                        message: __(`Work Order ${wo.work_order} đã bắt đầu !!!`),
                                        indicator: 'orange'
                                    });
                                }
                            });
                            frm.refresh_field('work_orders');

                            if (response.message.work_orders.length === 0) {
                                frappe.msgprint(__('No work orders found for the selected item and color.'));
                            }
                        }

                        // Add materials to the table
                        const listMaterialsData = response.message.materials || [];
                        const combinedData = combineItemsByCode(listMaterialsData);
                        if (combinedData && Array.isArray(combinedData)) {
                            combinedData.forEach(function (material) {
                                console.log(material)
                                let row = frm.add_child('materials');
                                row.item_code = material.item_code;
                                row.item_name = material.item_name;
                                row.item_name_detail = material.item_name_detail;
                                row.required_qty = material.required_qty;
                                row.qty_available = material.qty_available;
                                row.wip_warehouse = material.wip_warehouse;
                                row.source_warehouse = material.source_warehouse;
                            });
                            frm.refresh_field('materials');
                        }
                    }
                }
            });
        }
    },

    // before_save: function (frm) {
    //     let has_qty_error = false;

    //     if (frm.doc.materials && frm._original_required_qtys) {
    //         frm.doc.materials.forEach(function (item) {
    //             if (frm._original_required_qtys[item.name] && item.required_qty < frm._original_required_qtys[item.name]) {
    //                 has_qty_error = true;
    //                 frappe.msgprint({
    //                     title: __('Not Allowed'),
    //                     message: __('Item "{0}" cannot have quantity ({1}) lower than original value ({2}).',
    //                         [item.item_name || item.item_code, item.required_qty, frm._original_required_qtys[item.name]]),
    //                     indicator: 'red'
    //                 });
    //             }
    //         });
    //     }

    //     if (has_qty_error) {
    //         frappe.validated = false; // Prevent saving
    //     }
    // }

});

// Add event handlers for the child table
frappe.ui.form.on("Stock Entry Multi Work Orders Table WO", {
    work_orders_add: function (frm, cdt, cdn) {
        refresh_materials(frm);
    },


    work_orders_remove: function (frm, cdt, cdn) {
        // Use a small delay to ensure the form state is updated
        setTimeout(function () {
            refresh_materials(frm);
        }, 300);
    },

    work_order: function (frm, cdt, cdn) {
        refresh_materials(frm);
    },

    // update Materials when qty_to_manufacture changes
    qty_to_manufacture: function (frm, cdt, cdn) {
        let wo_row = locals[cdt][cdn];

        // Store original value if not already stored
        if (!frm._original_wo_qtys) {
            frm._original_wo_qtys = {};
        }

        // If this is the first change, store the original value
        if (!frm._original_wo_qtys[wo_row.name]) {
            frm._original_wo_qtys[wo_row.name] = wo_row.qty_to_manufacture;
            return; // Exit early on first setup
        }

        // Calculate the ratio between new and original quantity
        let qty_ratio = wo_row.qty_to_manufacture / frm._original_wo_qtys[wo_row.name];

        // Find materials related to this work order and update them
        frappe.call({
            method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_materials_for_single_work_order',
            args: {
                'work_order': wo_row.work_order
            },
            callback: function (response) {
                if (response.message && Array.isArray(response.message)) {
                    let materials_to_update = response.message;

                    // Update each material's required quantity
                    frm.doc.materials.forEach(function (material_row) {
                        // Find matching materials by item_code
                        let matching_materials = materials_to_update.filter(m =>
                            m.item_code === material_row.item_code);

                        if (matching_materials.length > 0) {
                            // Update the required_qty proportionally
                            let new_qty = material_row.required_qty * qty_ratio;

                            // Update the value in the materials table
                            frappe.model.set_value(
                                'Stock Entry Multi Work Orders Table Material',
                                material_row.name,
                                'required_qty',
                                new_qty
                            );

                            // Also update the stored original value for validation
                            if (frm._original_required_qtys) {
                                frm._original_required_qtys[material_row.name] = new_qty;
                            }
                        }
                    });

                    // Refresh the materials table
                    frm.refresh_field('materials');
                }
            }
        });

        // Update the stored original value for this work order
        frm._original_wo_qtys[wo_row.name] = wo_row.qty_to_manufacture;
    }
});

// Improved refresh_materials function that properly handles work order deletions
function refresh_materials(frm) {

    // Luôn luôn xóa bảng materials, kể cả khi không có work orders
    frm.clear_table('materials');
    frm.refresh_field('materials');

    // Get all work orders from the table
    let work_orders = frm.doc.work_orders
        ? frm.doc.work_orders
            .filter(row => row.work_order && row.work_order.trim() !== '')
            .map(row => row.work_order)
        : [];


    if (work_orders.length > 0) {
        frappe.call({
            method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_materials_for_work_orders',
            args: {
                'work_orders': work_orders
            },
            freeze: true,
            callback: function (response) {
                if (response.message && Array.isArray(response.message)) {
                    // Combine items with the same item_code
                    const combinedData = combineItemsByCode(response.message);

                    // Add materials to the table
                    combinedData.forEach(function (material) {
                        let row = frm.add_child('materials');
                        row.item_code = material.item_code;
                        row.item_name = material.item_name;
                        row.item_name_detail = material.item_name_detail;
                        row.required_qty = material.required_qty;
                        row.qty_available_in_source_warehouse = material.qty_available;
                        row.wip_warehouse = material.wip_warehouse;
                        row.source_warehouse = material.source_warehouse;
                    });

                    frm.refresh_field('materials');
                    frappe.show_alert({
                        message: __('Materials retrieved successfully'),
                        indicator: 'green'
                    });
                } else {
                    frappe.msgprint(__('No materials found for the selected work orders.'));
                }
            }
        });
    } else {
        frappe.msgprint(__('No work orders selected. Please select at least one work order.'));
    }
}


// Hàm tạo nhiều Stock Entry
// Replace your current create_stock_entries function with this
function create_stock_entries(frm) {
    if (!frm.doc.work_orders || frm.doc.work_orders.length === 0) {
        frappe.msgprint(__('No work orders selected'));
        return;
    }

    // Get the list of work orders
    const work_orders = frm.doc.work_orders.map(row => row.work_order);

    // First check for existing draft Stock Entries
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.check_existing_draft_stock_entries',
        args: {
            'work_orders': work_orders
        },
        freeze: true,
        freeze_message: __('Checking for existing Stock Entries...'),
        callback: function (response) {
            if (response.message && response.message.length > 0) {
                // There are existing draft Stock Entries
                let message = __('The following Work Orders already have draft Stock Entries:') + '<br><br>';
                let existing_work_orders = [];

                response.message.forEach(entry => {
                    existing_work_orders.push(entry.work_order);
                    message += `${entry.work_order}: <a href="/app/stock-entry/${entry.stock_entry}" target="_blank">${entry.stock_entry}</a><br>`;
                });

                // Filter out work orders that already have drafts
                let new_work_orders = work_orders.filter(wo => !existing_work_orders.includes(wo));

                if (new_work_orders.length > 0) {
                    frappe.confirm(
                        message,
                        function () {
                            // User clicked Yes - create Stock Entries for remaining work orders
                            create_new_stock_entries(frm, new_work_orders);
                        },
                        function () {
                            // User clicked No - do nothing
                            frappe.msgprint(__('Operation cancelled'));
                        }
                    );
                } else {
                    frappe.msgprint({
                        title: __('Cannot Create Stock Entries'),
                        indicator: 'red',
                        message: __('All selected Work Orders already have draft Stock Entries.') + '<br><br>' + message
                    });
                }
            } else {
                // No existing drafts, proceed with all work orders
                frappe.confirm(
                    __('This will create {0} separate Stock Entries, one for each Work Order. Continue?', [work_orders.length]),
                    function () {
                        create_new_stock_entries(frm, work_orders);
                    }
                );
            }
        }
    });
}

// Helper function to create the actual Stock Entries
function create_new_stock_entries(frm, work_orders) {
    if (work_orders.length === 0) {
        return;
    }

    // Display progress indicator
    frappe.show_progress(__('Creating Stock Entries'), 0, work_orders.length);

    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.create_individual_stock_entries',
        args: {
            'doc_name': frm.doc.name,
            'work_orders': work_orders
        },
        freeze: true,
        freeze_message: __('Creating Stock Entries...'),
        callback: function (response) {
            // Ensure the progress indicator is properly closed
            frappe.hide_progress();

            if (response.message && response.message.length) {
                let message = __('Created the following Stock Entries:') + '<br><br>';
                response.message.forEach(entry => {
                    message += `<a href="/app/stock-entry/${entry}" target="_blank">${entry}</a><br>`;
                });

                frappe.msgprint({
                    title: __('Stock Entries Created'),
                    indicator: 'green',
                    message: message
                });
            }
        }
    });
}

/**
 * Simplified quantity adjustment dialog - removed validation for qty reductions
 * @param {Object} frm - Form object
 * @param {Array} selected_items - Selected material items
 */
function show_qty_adjustment_dialog(frm, selected_items) {
    console.log("show_qty_adjustment_dialog");
    if (selected_items.length === 0) return;

    let fields = [];

    selected_items.forEach(item => {
        // Use grid_idx instead of idx
        fields.push({
            fieldtype: 'Float',
            fieldname: `qty_${item.grid_idx}`,
            label: `${item.item_code} - ${item.item_name || ''} (Current: ${item.required_qty})`,
            default: item.required_qty
        });
    });

    let d = new frappe.ui.Dialog({
        title: __('Adjust Quantities'),
        fields: fields,
        primary_action_label: __('Update'),
        primary_action: function () {
            let values = d.get_values();

            // Update quantities in the materials table
            selected_items.forEach(item => {
                // Use grid_idx instead of idx
                let new_qty = values[`qty_${item.grid_idx}`];

                // Update the quantity in the grid
                frappe.model.set_value(item.doctype, item.name, 'required_qty', new_qty);
            });

            frm.refresh_field('materials');
            d.hide();
        }
    });

    d.show();
}

/**
 * Combines items with the same item_code and sums their required_qty values
 * @param {Array} items - Array of item objects
 * @returns {Array} - Array of combined items
 */
const combineItemsByCode = (items) => {
    const groupedItems = {};

    items.forEach(item => {
        const itemCode = item.item_code;

        if (!groupedItems[itemCode]) {
            // First occurrence of this item_code, create new entry
            groupedItems[itemCode] = { ...item };
        } else {
            // Item already exists, sum the required_qty
            groupedItems[itemCode].required_qty = flt(groupedItems[itemCode].required_qty) + flt(item.required_qty);
        }
    });

    // Convert the object back to array
    return Object.values(groupedItems);
}

/**
 * Helper function to safely convert string to float
 * @param {*} val - Value to convert
 * @returns {number} - Float value
 */
function flt(val) {
    return parseFloat(val || 0);
}
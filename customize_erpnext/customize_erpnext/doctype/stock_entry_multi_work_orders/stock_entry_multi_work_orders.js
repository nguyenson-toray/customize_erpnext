// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

// Biến global theo dõi trạng thái hiển thị của error dialog
var isErrorDialogShowing = false;

frappe.ui.form.on("Stock Entry Multi Work Orders", {
    refresh(frm) {
        frm.set_intro(null);
        frm.set_intro(__("Sau khi Submit, hệ thống sẽ tạo các Stock Entry (Draft) kiểu Material Transfer for Manufacture cho các Work Order tương ứng"), 'orange');
        // Add refresh materials button
        frm.add_custom_button(__('Refresh Materials'), function () {
            refresh_materials(frm);
        });

        // Cải thiện xử lý nút xóa bảng work_orders
        $(frm.fields_dict['work_orders'].grid.wrapper).on('click', '.grid-delete-row', function () {
            setTimeout(function () {
                refresh_materials(frm);
            }, 300);
        });

        // Handle item_template color list population
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

        // Add create Stock Entry button
        // if (frm.doc.docstatus === 0) {
        //     frm.add_custom_button(__('Create Stock Entry'), function () {
        //         create_stock_entries(frm);
        //     }).addClass('btn-primary');
        // }

        // Add view Stock Entries button if doc is submitted
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('View Stock Entries'), function () {
                frappe.route_options = {
                    "stock_entry_multi_work_orders": frm.doc.name
                };
                frappe.set_route("List", "Stock Entry");
            });
        }

        // Custom validation for materials table
        frm.fields_dict['materials'].grid.wrapper.on('click', '.grid-row-check', function () {
            let grid = frm.fields_dict['materials'].grid;
            let selected = grid.get_selected();

            // Get selected rows data
            let selected_items = [];
            selected.forEach(idx => {
                // Lấy row và gán lại idx vào object
                let item = frm.doc.materials[idx];
                if (item) {
                    // Gán lại index đúng vào từng item
                    item.grid_idx = idx;
                    selected_items.push(item);
                }
            });

            // Show qty adjustment dialog if items are selected
            if (selected_items.length > 0) {
                show_qty_adjustment_dialog(frm, selected_items);
            }
        });

        // Lưu trữ giá trị gốc trong một cache riêng biệt
        if (!frm.doc.__original_required_qty_cache) {
            frm.doc.__original_required_qty_cache = {};
        }

        // Lưu giá trị ban đầu của required_qty cho tất cả dòng hiện tại
        if (frm.doc.materials && frm.doc.materials.length) {
            frm.doc.materials.forEach(function (row) {
                if (!frm.doc.__original_required_qty_cache[row.name]) {
                    frm.doc.__original_required_qty_cache[row.name] = row.required_qty;
                }
            });
        }

        // Override the grid row's validate function
        frm.fields_dict['materials'].grid.wrapper.on('click', '.grid-row', function () {
            const $row = $(this);
            const idx = $row.attr('data-idx') - 1;

            if (idx >= 0 && frm.doc.materials && frm.doc.materials[idx]) {
                const material = frm.doc.materials[idx];

                // Lưu giá trị gốc khi click vào row (trước khi edit)
                if (!frm.doc.__original_required_qty_cache[material.name]) {
                    frm.doc.__original_required_qty_cache[material.name] = material.required_qty;
                }

                // Gán event handler vào ô required_qty
                setTimeout(() => {
                    const $input = $row.find('input[data-fieldname="required_qty"]');
                    if ($input.length) {
                        const originalQty = frm.doc.__original_required_qty_cache[material.name];

                        $input.off('change.validate_qty').on('change.validate_qty', function () {
                            const newQty = parseFloat($(this).val() || 0);

                            if (newQty < originalQty && !isErrorDialogShowing) {
                                isErrorDialogShowing = true;

                                // Hiển thị thông báo lỗi chi tiết
                                const errorDialog = new frappe.ui.Dialog({
                                    title: __('Không thể giảm số lượng'),
                                    indicator: 'red',
                                    fields: [
                                        {
                                            fieldtype: 'HTML',
                                            fieldname: 'message',
                                            options: `
                                                <div class="alert alert-danger">
                                                    <p><strong>Item:</strong> ${material.item_code} - ${material.item_name || ''}</p>
                                                    <p><strong>Số lượng gốc:</strong> ${originalQty}</p>
                                                    <p><strong>Số lượng mới:</strong> ${newQty}</p>
                                                    <p>Chỉ được phép tăng số lượng, không được giảm!</p>
                                                </div>
                                            `
                                        }
                                    ],
                                    primary_action_label: __('OK'),
                                    primary_action: () => {
                                        // Reset lại giá trị
                                        frappe.model.set_value(material.doctype, material.name, 'required_qty', originalQty);
                                        frm.refresh_field('materials');
                                        errorDialog.hide();
                                    },
                                    onhide: () => {
                                        // Reset flag khi dialog được đóng
                                        setTimeout(() => {
                                            isErrorDialogShowing = false;
                                        }, 300);
                                    }
                                });

                                errorDialog.show();

                                // Reset lại giá trị trực tiếp trên input
                                $(this).val(originalQty);

                                // Cập nhật giá trị trong model
                                frappe.model.set_value(material.doctype, material.name, 'required_qty', originalQty);
                            }
                        });
                    }
                }, 100);
            }
        });
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

            // Reset cache
            frm.doc.__original_required_qty_cache = {};

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
                                // row.stock_transfer_status = wo.stock_transfer_status;
                                row.work_order_status = wo.work_order_status;
                                // Cập nhật thông báo và duy trì nhất quán trạng thái
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
                                let row = frm.add_child('materials');
                                row.item_code = material.item_code;
                                row.item_name = material.item_name;
                                row.item_name_detail = material.item_name_detail;
                                row.required_qty = material.required_qty;
                                row.qty_available_in_source_warehouse = material.qty_available;
                                row.wip_warehouse = material.wip_warehouse;
                                row.source_warehouse = material.source_warehouse;

                                // Lưu giá trị gốc trong cache
                                if (!frm.doc.__original_required_qty_cache) {
                                    frm.doc.__original_required_qty_cache = {};
                                }
                                frm.doc.__original_required_qty_cache[row.name] = material.required_qty;
                            });
                            frm.refresh_field('materials');
                        }
                    }
                }
            });
        }
    },
});

// Event handler cho child table "Stock Entry Multi Work Orders Table WO"
frappe.ui.form.on("Stock Entry Multi Work Orders Table WO", {
    work_orders_add: function (frm, cdt, cdn) {
        refresh_materials(frm);
    },

    work_orders_remove: function (frm, cdt, cdn) {
        refresh_materials(frm);
    }
});

// Event handler cho child table "Stock Entry Multi Work Orders Table Material"
frappe.ui.form.on("Stock Entry Multi Work Orders Table Material", {
    required_qty: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Lấy giá trị gốc từ cache
        if (!frm.doc.__original_required_qty_cache) {
            frm.doc.__original_required_qty_cache = {};
        }

        let original_qty = frm.doc.__original_required_qty_cache[cdn];

        // Nếu chưa có giá trị gốc, lưu giá trị hiện tại
        if (!original_qty) {
            frm.doc.__original_required_qty_cache[cdn] = row.required_qty;
            return;
        }

        // Kiểm tra giá trị mới
        if (flt(row.required_qty) < flt(original_qty) && !isErrorDialogShowing) {
            isErrorDialogShowing = true;

            // Hiển thị thông báo lỗi chi tiết
            const errorDialog = new frappe.ui.Dialog({
                title: __('Không thể giảm số lượng'),
                indicator: 'red',
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'message',
                        options: `
                            <div class="alert alert-danger">
                                <p><strong>Item:</strong> ${row.item_code} - ${row.item_name || ''}</p>
                                <p><strong>Số lượng gốc:</strong> ${original_qty}</p>
                                <p><strong>Số lượng mới:</strong> ${row.required_qty}</p>
                                <p>Chỉ được phép tăng số lượng, không được giảm!</p>
                            </div>
                        `
                    }
                ],
                primary_action_label: __('OK'),
                primary_action: () => {
                    // Reset lại giá trị
                    frappe.model.set_value(cdt, cdn, 'required_qty', original_qty);
                    errorDialog.hide();
                },
                onhide: () => {
                    // Reset flag khi dialog được đóng
                    setTimeout(() => {
                        isErrorDialogShowing = false;
                    }, 300);
                }
            });

            errorDialog.show();

            // Reset lại giá trị
            frappe.model.set_value(cdt, cdn, 'required_qty', original_qty);
        }
    }
});

// Improved refresh_materials function that properly handles work order deletions
function refresh_materials(frm) {
    console.log("refresh_materials");
    // Get all work orders from the table
    let work_orders = frm.doc.work_orders
        ? frm.doc.work_orders
            .filter(row => row.work_order && row.work_order.trim() !== '')
            .map(row => row.work_order)
        : [];

    // Lưu giá trị hiện tại của materials để giữ lại số lượng đã điều chỉnh
    let current_materials = {};
    if (frm.doc.materials && frm.doc.materials.length) {
        frm.doc.materials.forEach(function (row) {
            current_materials[row.item_code] = {
                qty: flt(row.required_qty),
                original_qty: frm.doc.__original_required_qty_cache ?
                    frm.doc.__original_required_qty_cache[row.name] || row.required_qty :
                    row.required_qty
            };
        });
    }

    // Backup cache
    let original_required_qty_cache = frm.doc.__original_required_qty_cache || {};

    // Luôn luôn xóa bảng materials, kể cả khi không có work orders
    frm.clear_table('materials');
    frm.refresh_field('materials');

    // Khởi tạo lại cache nếu cần
    if (!frm.doc.__original_required_qty_cache) {
        frm.doc.__original_required_qty_cache = {};
    }

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

                        // Sử dụng số lượng đã điều chỉnh nếu có, hoặc số lượng tính toán
                        let calculated_qty = flt(material.required_qty);
                        let original_qty = calculated_qty;

                        if (current_materials[material.item_code]) {
                            // Lưu giá trị gốc trước khi điều chỉnh
                            original_qty = Math.min(calculated_qty, current_materials[material.item_code].original_qty || calculated_qty);

                            // Sử dụng giá trị lớn nhất giữa số lượng đã điều chỉnh và số lượng tính toán
                            calculated_qty = Math.max(calculated_qty, current_materials[material.item_code].qty || 0);
                        }

                        row.required_qty = calculated_qty;
                        row.qty_available_in_source_warehouse = material.qty_available;
                        row.wip_warehouse = material.wip_warehouse;
                        row.source_warehouse = material.source_warehouse;

                        // Lưu lại giá trị gốc vào cache
                        frm.doc.__original_required_qty_cache[row.name] = original_qty;
                    });

                    frm.refresh_field('materials');
                }
            }
        });
    }
}

// Hàm tạo nhiều Stock Entry - cải thiện báo lỗi và xử lý
function create_stock_entries(frm) {
    if (!frm.doc.work_orders || frm.doc.work_orders.length === 0) {
        frappe.msgprint(__('No work orders selected'));
        return;
    }

    frappe.confirm(
        __('This will create {0} separate Stock Entries, one for each Work Order. Continue?', [frm.doc.work_orders.length]),
        function () {
            // Hiển thị thông báo đang xử lý
            frappe.show_progress(__('Creating Stock Entries'), 0, frm.doc.work_orders.length);

            // Lấy danh sách work order
            const work_orders = frm.doc.work_orders.map(row => row.work_order);

            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.create_individual_stock_entries',
                args: {
                    'doc_name': frm.doc.name,
                    'work_orders': work_orders
                },
                freeze: true,
                freeze_message: __('Creating Stock Entries...'),
                callback: function (response) {
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

                        // Refresh work order status
                        frm.reload_doc();
                    } else {
                        frappe.msgprint({
                            title: __('Warning'),
                            indicator: 'orange',
                            message: __('No Stock Entries were created. Check the server error log for details.')
                        });
                    }
                },
                error: function (err) {
                    frappe.msgprint({
                        title: __('Error'),
                        indicator: 'red',
                        message: __('Failed to create Stock Entries: ') + (err.message || 'Unknown error')
                    });
                }
            });
        }
    );
}

/**
 * Cải thiện dialog điều chỉnh số lượng - yêu cầu nghiêm ngặt về việc chỉ được tăng số lượng
 * @param {Object} frm - Form object
 * @param {Array} selected_items - Selected material items
 */
function show_qty_adjustment_dialog(frm, selected_items) {
    console.log("show_qty_adjustment_dialog");
    if (selected_items.length === 0) return;

    let fields = [];

    selected_items.forEach(item => {
        // Dùng grid_idx thay vì idx
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
            let has_errors = false;

            // Update quantities in the materials table
            selected_items.forEach(item => {
                // Dùng grid_idx thay vì idx
                let new_qty = values[`qty_${item.grid_idx}`];

                // Lấy giá trị gốc từ cache
                let original_qty = frm.doc.__original_required_qty_cache ?
                    frm.doc.__original_required_qty_cache[item.name] || item.required_qty :
                    item.required_qty;

                // Chỉ cho phép tăng số lượng
                if (flt(new_qty) < flt(original_qty)) {
                    // Kiểm tra nếu đang có dialog hiển thị
                    if (!isErrorDialogShowing) {
                        isErrorDialogShowing = true;

                        // Hiển thị thông báo lỗi chi tiết
                        const errorDialog = new frappe.ui.Dialog({
                            title: __('Không thể giảm số lượng'),
                            indicator: 'red',
                            fields: [
                                {
                                    fieldtype: 'HTML',
                                    fieldname: 'message',
                                    options: `
                                        <div class="alert alert-danger">
                                            <p><strong>Item:</strong> ${item.item_code} - ${item.item_name || ''}</p>
                                            <p><strong>Số lượng gốc:</strong> ${original_qty}</p>
                                            <p><strong>Số lượng mới:</strong> ${new_qty}</p>
                                            <p>Chỉ được phép tăng số lượng, không được giảm!</p>
                                        </div>
                                    `
                                }
                            ],
                            primary_action_label: __('OK'),
                            primary_action: () => {
                                errorDialog.hide();
                            },
                            onhide: () => {
                                // Reset flag khi dialog được đóng
                                setTimeout(() => {
                                    isErrorDialogShowing = false;
                                }, 300);
                            }
                        });

                        errorDialog.show();
                    }

                    has_errors = true;
                    // Reset lại giá trị ban đầu
                    d.set_value(`qty_${item.grid_idx}`, item.required_qty);
                } else {
                    // Update the quantity in the grid
                    frappe.model.set_value(item.doctype, item.name, 'required_qty', new_qty);
                }
            });

            if (!has_errors) {
                frm.refresh_field('materials');
                d.hide();
            }
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
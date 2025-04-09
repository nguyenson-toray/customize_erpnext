frappe.ui.form.on('Stock Entry Multi Work Orders', {
    refresh: function (frm) {
        // Add custom buttons only if the document is not submitted
        if (!frm.doc.__islocal && frm.doc.docstatus == 0) {
            frm.add_custom_button(__('Get Work Orders'), function () {
                getWorkOrders(frm);
            });

            frm.add_custom_button(__('Create Stock Entries'), function () {
                createStockEntries(frm);
            }).addClass('btn-primary');
        }
    },

    item_template: function (frm) {
        // When item template changes, fetch colors available for this template
        if (frm.doc.item_template) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Item',
                    name: frm.doc.item_template
                },
                callback: function (r) {
                    if (r.message) {
                        // Get color attribute values for this template
                        getColorAttributeValues(frm, r.message.name);
                    }
                }
            });
        }
    },

    color: function (frm) {
        // Clear the tables when color changes
        frm.clear_table('work_orders');
        frm.clear_table('materials');
        frm.refresh_fields(['work_orders', 'materials']);
    }
});

function getColorAttributeValues(frm, item_template) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Item Variant Attribute',
            filters: {
                'parent': item_template,
                'attribute': 'Color'
            },
            fields: ['attribute_value']
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                // Get unique color values
                let colors = r.message.map(row => row.attribute_value);
                frm.set_df_property('color', 'options', [''].concat(colors));
                frm.refresh_field('color');
            }
        }
    });
}

function getWorkOrders(frm) {
    if (!frm.doc.item_template || !frm.doc.color) {
        frappe.msgprint(__('Please select Item Template and Color first'));
        return;
    }

    // Get all variants of the template with the selected color
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Item',
            filters: {
                'variant_of': frm.doc.item_template,
                'variant_based_on': 'Item Attribute',
            },
            fields: ['name']
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                let item_codes = r.message.map(item => item.name);

                // Filter for items with the selected color
                frappe.call({
                    method: 'erpnext.stock.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_variant_items_by_color',
                    args: {
                        item_codes: item_codes,
                        color: frm.doc.color
                    },
                    callback: function (r) {
                        if (r.message && r.message.length > 0) {
                            let filtered_items = r.message;
                            // Now get all submitted work orders for these items
                            showWorkOrderSelection(frm, filtered_items);
                        } else {
                            frappe.msgprint(__('No items found with the selected template and color'));
                        }
                    }
                });
            }
        }
    });
}

function showWorkOrderSelection(frm, item_codes) {
    frappe.call({
        method: 'erpnext.stock.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_submitted_work_orders',
        args: {
            item_codes: item_codes
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                // Show dialog with work orders
                showMultiSelectDialog(frm, r.message);
            } else {
                frappe.msgprint(__('No submitted work orders found for the selected items'));
            }
        }
    });
}

function showMultiSelectDialog(frm, work_orders) {
    let fields = [
        {
            fieldtype: 'Check',
            fieldname: 'select_all',
            label: __('Select All'),
            onchange: function () {
                let checked = this.get_value();
                dialog.fields_dict.work_orders.df.data.forEach(row => {
                    row.check = checked ? 1 : 0;
                });
                dialog.fields_dict.work_orders.refresh();
            }
        },
        {
            fieldtype: 'Table',
            fieldname: 'work_orders',
            label: __('Work Orders'),
            cannot_add_rows: true,
            in_place_edit: true,
            data: work_orders,
            get_data: () => {
                return work_orders;
            },
            fields: [
                {
                    fieldtype: 'Check',
                    fieldname: 'check',
                    label: __('Select'),
                    in_list_view: 1,
                    columns: 1
                },
                {
                    fieldtype: 'Link',
                    fieldname: 'name',
                    label: __('Work Order'),
                    options: 'Work Order',
                    in_list_view: 1,
                    columns: 2,
                    read_only: 1
                },
                {
                    fieldtype: 'Link',
                    fieldname: 'production_item',
                    label: __('Item'),
                    options: 'Item',
                    in_list_view: 1,
                    columns: 2,
                    read_only: 1
                },
                {
                    fieldtype: 'Data',
                    fieldname: 'item_name_detail',
                    label: __('Item Name Detail'),
                    in_list_view: 1,
                    columns: 2,
                    read_only: 1
                },
                {
                    fieldtype: 'Float',
                    fieldname: 'qty',
                    label: __('Qty to Manufacture'),
                    in_list_view: 1,
                    columns: 1,
                    read_only: 1
                },
                {
                    fieldtype: 'Float',
                    fieldname: 'material_transferred_for_manufacturing',
                    label: __('Material Transferred'),
                    in_list_view: 1,
                    columns: 1,
                    read_only: 1
                },
                {
                    fieldtype: 'Date',
                    fieldname: 'expected_delivery_date',
                    label: __('Expected Delivery Date'),
                    in_list_view: 1,
                    columns: 1,
                    read_only: 1
                }
            ]
        }
    ];

    let dialog = new frappe.ui.Dialog({
        title: __('Select Work Orders'),
        fields: fields,
        size: 'large',
        primary_action_label: __('Get Materials'),
        primary_action: function () {
            let selected_work_orders = dialog.get_values().work_orders.filter(row => row.check);
            if (selected_work_orders.length === 0) {
                frappe.msgprint(__('Please select at least one work order'));
                return;
            }

            // Add selected work orders to the form
            addWorkOrdersToForm(frm, selected_work_orders);

            // Get materials for the selected work orders
            getMaterialsForWorkOrders(frm, selected_work_orders);

            dialog.hide();
        }
    });

    dialog.show();
}

function addWorkOrdersToForm(frm, selected_work_orders) {
    // Clear existing work orders
    frm.clear_table('work_orders');

    // Add selected work orders to the table
    selected_work_orders.forEach(wo => {
        let child = frm.add_child('work_orders');
        child.work_order = wo.name;
        child.item_code = wo.production_item;
        child.item_name = wo.item_name;
        child.item_name_detail = wo.item_name_detail;
        child.qty_to_manufacture = wo.qty;
    });

    frm.refresh_field('work_orders');
}

function getMaterialsForWorkOrders(frm, selected_work_orders) {
    let work_order_names = selected_work_orders.map(wo => wo.name);

    frappe.call({
        method: 'erpnext.stock.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_materials_for_work_orders',
        args: {
            work_orders: work_order_names
        },
        callback: function (r) {
            if (r.message) {
                // Clear existing materials
                frm.clear_table('materials');

                // Add materials to the table
                r.message.forEach(item => {
                    let child = frm.add_child('materials');
                    child.item_code = item.item_code;
                    child.item_name = item.item_name;
                    child.item_name_detail = item.item_name_detail;
                    child.required_qty = item.required_qty;
                    child.srource_warehouse = item.source_warehouse;
                    child.qty_available_in_source_warehouse = item.available_qty_at_source;
                    child.wip_warehouse = item.wip_warehouse;
                });

                frm.refresh_field('materials');
                frm.save();
            }
        }
    });
}

function createStockEntries(frm) {
    if (frm.doc.work_orders.length === 0) {
        frappe.msgprint(__('No work orders selected'));
        return;
    }

    if (frm.doc.materials.length === 0) {
        frappe.msgprint(__('No materials found'));
        return;
    }

    frappe.confirm(
        __('This will create Stock Entry documents for all selected Work Orders. Continue?'),
        function () {
            frappe.call({
                method: 'erpnext.stock.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.create_stock_entries',
                args: {
                    doc: frm.doc
                },
                freeze: true,
                freeze_message: __('Creating Stock Entries...'),
                callback: function (r) {
                    if (r.message) {
                        let stock_entries = r.message;
                        frappe.msgprint({
                            title: __('Stock Entries Created'),
                            indicator: 'green',
                            message: __('The following Stock Entries were created: {0}',
                                [stock_entries.map(se =>
                                    '<a href="/app/stock-entry/' + se + '">' + se + '</a>'
                                ).join(', ')]
                            )
                        });
                        frm.reload_doc();
                    }
                }
            });
        }
    );
}
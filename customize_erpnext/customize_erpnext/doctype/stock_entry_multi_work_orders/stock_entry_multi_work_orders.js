// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock Entry Multi Work Orders", {
    refresh(frm) {
        if (!frm.doc.__islocal) {
            frm.add_custom_button(__('Create Stock Entries'), function () {
                create_stock_entries(frm);
            });
        }
    },

    item_template(frm) {
        if (frm.doc.item_template) {
            // Find all color variants for the selected template
            frappe.call({
                method: "customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_item_colors",
                args: {
                    item_template: frm.doc.item_template
                },
                callback: function (r) {
                    if (r.message && r.message.length) {
                        frm.set_df_property('color', 'options', [''].concat(r.message).join('\n'));
                        frm.refresh_field('color');
                    } else {
                        frm.set_df_property('color', 'options', '');
                        frm.refresh_field('color');
                    }
                }
            });
        } else {
            frm.set_value('color', '');
            frm.set_df_property('color', 'options', '');
            frm.refresh_field('color');
        }
    },

    color: async function (frm) { 
        if (frm.doc.item_template && frm.doc.color) { 
            // Find all work orders with the selected template and color
            await frappe.call({
                method: "customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_work_orders",
                args: {
                    item_template: frm.doc.item_template,
                    color: frm.doc.color
                },
                callback: function (r) { 
                    if (r.message) { 
                        frm.clear_table('work_orders');
                        r.message.work_orders.forEach(wo => {

                            let row = frm.add_child('work_orders');
                            row.work_order = wo.name;
                            row.item_code = wo.production_item;
                            row.qty = wo.qty;
                            row.pending_qty = wo.pending_qty;
                        });

                        frm.refresh_field('work_orders');

                        // After adding work orders, get the materials
                        get_materials(frm);
                    }
                }
            });
            console.log("6. After frappe.call()");
        } else {
            frm.clear_table('work_orders');
            frm.clear_table('materials');
            frm.refresh_fields(['work_orders', 'materials']);
        }
    }
});

function get_materials(frm) {
    let work_orders = frm.doc.work_orders || [];
    console.log()
    if (work_orders.length) {
        let work_order_list = work_orders.map(d => d.work_order);

        frappe.call({
            method: "customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_work_order_materials",
            args: {
                work_orders: work_order_list
            },
            callback: function (r) {
                if (r.message) {
                    frm.clear_table('materials');
                    r.message.forEach(item => {
                        let row = frm.add_child('materials');
                        Object.keys(item).forEach(key => {
                            row[key] = item[key];
                        });
                    });

                    frm.refresh_field('materials');
                }
            }
        });
    }
}

function create_stock_entries(frm) {
    frappe.call({
        method: "customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.create_stock_entries",
        args: {
            docname: frm.docname
        },
        freeze: true,
        freeze_message: __("Creating Stock Entries..."),
        callback: function (r) {
            if (r.message) {
                frappe.msgprint(__("Stock Entries created successfully"));
                frm.reload_doc();
            }
        }
    });
}
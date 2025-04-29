frappe.ui.form.on('Material Request', {

    onload: function (frm) {
        if (frm.is_new()) {
            let schedule_date = frappe.datetime.add_days(frappe.datetime.nowdate(), 3);
            frm.set_value('schedule_date', schedule_date);
        }
        frm.add_custom_button(__('Get Material From Production Plan - Purchase - Including Lost Percent'), function () {
            show_production_plan_dialog(frm);
        }, __('Custom Features'));
        frm.add_custom_button(__('Get Material From Production Plan - Customer Provided - Including Lost Percent'), function () {
            show_production_plan_dialog(frm);
        }, __('Custom Features'));
    },
    material_request_type: function (frm) {
        // validate_total_amount(frm); 
        // if (frm.doc.material_request_type == "Purchase") {
        //     frappe.msgprint({
        //         title: __('Notification'),
        //         indicator: 'green',
        //         message: __('Only for Items are material in manufacturing')
        //     });
        //     frm.add_custom_button(__('Get Material From Production Plan - Purchase - Including Lost Percent'), function () {
        //         show_production_plan_dialog(frm);
        //     }, __('Custom Features'));
        // }
        // if (frm.doc.material_request_type == "Customer Provided") {
        //     frm.add_custom_button(__('Get Material From Production Plan - Customer Provided - Including Lost Percent'), function () {
        //         show_production_plan_dialog(frm);
        //     }, __('Custom Features'));
        // }
    },
    validate: function (frm) {
        // validate_total_amount(frm);
    },
    refresh: function (frm) {
        console.log('frm.doc.material_request_type:', frm.doc.material_request_type);
        if (frm.doc.docstatus === 0) {
            // Thêm nhóm button Custom Features 
            frm.add_custom_button(__('Sum Qty Of Duplicate Item'), function () {
                sum_duplicate_items(frm);
            }, __('Custom Features'));
        }
    }
});

function validate_total_amount(frm) {
    if (frm.doc.material_request_type == "Purchase") {
        let total = 0;
        frm.doc.items.forEach(function (item) {
            total += item.amount;
        });
        frm.set_value('custom_total_amount', total);
        // frm.set_value('custom_first_approve_by', 'thaisonqng@gmail.com');
        // frm.set_df_property('custom_first_approve_by', 'hidden', 0);

        if (total == 0 || !total) {
            frm.set_df_property('custom_first_approve_by', 'hidden', 1);
            // // frm.set_value('custom_first_approve_by', '');
            frm.set_df_property('custom_second_approve_by', 'hidden', 1);
            // frm.set_value('custom_second_approve_by', '');

        }
        else if (total > 0 && total < 20000000) {
            // frm.set_value('custom_first_approve_by', 'thaisonqng@gmail.com');
            frm.set_df_property('custom_first_approve_by', 'hidden', 0);
            // frm.set_value('custom_second_approve_by', '');
            frm.set_df_property('custom_second_approve_by', 'hidden', 1);
            frappe.show_alert({
                message: `Total amount: ${total} - Approve by ${frm.doc.custom_first_approve_by}`,
                indicator: 'green'
            }, 5);
        }
        else {
            // > 20M
            // frm.set_value('custom_first_approve_by', 'thaisonqng@gmail.com');
            frm.set_df_property('custom_first_approve_by', 'hidden', 0);
            // frm.set_value('custom_second_approve_by', 'thaisonqng1@gmail.com');
            frm.set_df_property('custom_second_approve_by', 'hidden', 0);
            frappe.show_alert({
                message: `Total amount : ${total} -  Approve by ${frm.doc.custom_first_approve_by} and ${frm.doc.custom_second_approve_by}`,
                indicator: 'green'
            }, 5);
        }
    }
    else {
        //  frm.set_value('custom_first_approve_by', '');
        frm.set_df_property('custom_first_approve_by', 'hidden', 1);
        // frm.set_value('custom_second_approve_by', '');
        frm.set_df_property('custom_second_approve_by', 'hidden', 1);
    }
}
function show_production_plan_dialog(frm) {
    let d = new frappe.ui.Dialog({
        title: 'Select Production Plan',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'production_plans_html'
            }
        ],
        size: 'large', // Set dialog size to large
        primary_action_label: 'Get Items',
        primary_action(values) {
            const selected = this.selected_plan;
            if (!selected) {
                frappe.throw(__('Please select a Production Plan'));
                return;
            }

            frappe.call({
                method: 'customize_erpnext.api.material_request.get_items_from_production_plan',
                args: {
                    production_plan: selected
                },
                freeze: true,
                freeze_message: __('Getting items from Production Plan...'),
                callback: (r) => {
                    if (r.message) {
                        frm.clear_table('items');
                        r.message.items.forEach(item => frm.add_child('items', item));
                        frm.set_value('custom_note', r.message.custom_note);
                        frm.refresh();
                        d.hide();
                        frappe.show_alert({
                            message: __('Items fetched successfully'),
                            indicator: 'green'
                        });
                    }
                }
            });
        }
    });

    // Get latest 10 Production Plans
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Production Plan',
            filters: {
                'docstatus': 1,
                // 'status': 'Submitted'
            },
            fields: ['name', 'posting_date', 'total_planned_qty', 'custom_note'],
            order_by: 'creation desc',
            limit: 10
        },
        callback: function (r) {
            let html = `
                <div class="production-plans-table">
                    <table class="table table-bordered">
                        <thead>
                            <tr>
                                <th style="width: 30px"></th>
                                <th>Production Plan</th>
                                <th>Posting Date</th>
                                <th>Planned Qty</th>
                                <th>Custom Note</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            if (r.message && r.message.length) {
                console.log("message:", r.message);
                r.message.forEach(plan => {
                    html += `
                        <tr class="plan-row" data-plan="${plan.name}">
                            <td>
                                <input type="radio" name="plan" class="plan-select">
                            </td>
                            <td>${plan.name}</td>
                            <td>${frappe.datetime.str_to_user(plan.posting_date)}</td>
                            <td>${plan.total_planned_qty}</td>
                            <td>${plan.custom_note || ''}</td>
                        </tr>
                    `;
                });
            } else {
                html += `
                    <tr>
                        <td colspan="5" class="text-center text-muted">
                            No Production Plans found
                        </td>
                    </tr>
                `;
            }

            html += `
                        </tbody>
                    </table>
                </div>
            `;

            d.fields_dict.production_plans_html.$wrapper.html(html);

            // Handle row selection
            d.$wrapper.find('.plan-row').on('click', function () {
                const plan = $(this).attr('data-plan');
                d.$wrapper.find('.plan-row').removeClass('selected');
                d.$wrapper.find('.plan-select').prop('checked', false);
                $(this).addClass('selected');
                $(this).find('.plan-select').prop('checked', true);
                d.selected_plan = plan;
            });
        }
    });

    d.show();

    // Add custom styles
    d.$wrapper.find('.production-plans-table').css({
        'max-height': '400px',
        'overflow-y': 'auto'
    });

    frappe.dom.set_style(`
        .production-plans-table .plan-row { cursor: pointer; }
        .production-plans-table .plan-row:hover { background-color: var(--hover-bg); }
        .production-plans-table .plan-row.selected { background-color: var(--blue-50); }
        .production-plans-table th { position: sticky; top: 0; background-color: var(--gray-100); z-index: 1; }
        .production-plans-table td { vertical-align: middle; }
    `);
}

function show_split_dialog(frm) {
    if (!frm.doc.items || !frm.doc.items.length) {
        frappe.throw(__('No items to split'));
        return;
    }

    let d = new frappe.ui.Dialog({
        title: 'Split Material Request',
        fields: [{
            label: 'Select Groups',
            fieldname: 'groups',
            fieldtype: 'MultiSelectList',
            options: [
                '3.1 - Material - Fabric',
                '3.2 - Material - Interlining',
                '3.3 - Material - Padding',
                '3.4 - Material - Packing',
                '3.5 - Material - Sewing',
                '3.6 - Material - Thread'
            ],
            reqd: 1
        }],
        primary_action_label: 'Split',
        primary_action(values) {
            if (!values.groups || !values.groups.length) {
                frappe.throw(__('Please select at least one group'));
                return;
            }

            split_material_request(frm, values.groups);
            d.hide();
        }
    });
    d.show();
}

function split_material_request(frm, groups) {
    frappe.call({
        method: 'customize_erpnext.api.material_request.split_items_by_groups',
        args: {
            items: frm.doc.items,
            groups: groups,
            docname: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Splitting Material Request...'),
        callback: function (r) {
            if (r.message) {
                // Refresh the list view and navigate to filtered view of new MRs
                frm.reload_doc();
                frappe.set_route('List', 'Material Request', {
                    name: ['in', r.message]
                });
            }
        },
        error: function (r) {
            // Show error message if split operation fails
            frappe.msgprint({
                title: __('Error'),
                indicator: 'red',
                message: __('Failed to split Material Request. Please try again.')
            });
        }
    });
}
function sum_duplicate_items(frm) {
    if (!frm.doc.items || !frm.doc.items.length) {
        frappe.throw(__('Please add items first'));
        return;
    }

    frappe.confirm(
        __('This will combine duplicate items in the request. Continue?'),
        () => {
            frappe.call({
                method: 'customize_erpnext.api.material_request.sum_duplicate_items',
                args: {
                    doc: frm.doc
                },
                freeze: true,
                freeze_message: __('Combining duplicate items...'),
                callback: (r) => {
                    if (r.message) {
                        frm.clear_table('items');
                        r.message.forEach(item => frm.add_child('items', item));
                        frm.refresh();
                        frappe.show_alert({
                            message: __('Duplicate items have been combined'),
                            indicator: 'green'
                        });
                    }
                }
            });
        }
    );
}
function show_work_order_dialog(frm) {
    let d = new frappe.ui.Dialog({
        title: __('Get Materials from Work Orders'),
        size: 'extra-large', // Make dialog extra large
        fields: [
            {
                fieldtype: 'Link',
                fieldname: 'production_item',
                label: __('Item'),
                options: 'Item',
                get_query: () => {
                    return {
                        filters: {
                            is_stock_item: 1
                        }
                    };
                }
            },
            {
                fieldtype: 'Column Break',
                fieldname: 'col_break_1'
            },
            {
                fieldtype: 'Link',
                fieldname: 'bom_no',
                label: __('BOM'),
                options: 'BOM',
                get_query: () => {
                    return {
                        filters: {
                            is_active: 1
                        }
                    };
                }
            },
            {
                fieldtype: 'Section Break',
                fieldname: 'sec_break_1'
            },
            {
                fieldtype: 'HTML',
                fieldname: 'work_orders_html'
            }
        ],
        primary_action_label: __('Get Materials'),
        primary_action: function () {
            let selected_work_orders = [];
            d.$wrapper.find('.work-order-row').each(function () {
                if ($(this).find('.work-order-check').is(':checked')) {
                    selected_work_orders.push($(this).attr('data-work-order'));
                }
            });

            if (!selected_work_orders.length) {
                frappe.throw(__('Please select at least one Work Order'));
                return;
            }

            frappe.call({
                method: 'customize_erpnext.api.material_request.get_materials_from_work_orders',
                args: {
                    work_orders: selected_work_orders
                },
                freeze: true,
                freeze_message: __('Getting materials from Work Orders...'),
                callback: (r) => {
                    if (r.message) {
                        frm.clear_table('items');
                        r.message.items.forEach(item => frm.add_child('items', item));
                        frm.set_value('material_request_type', 'Material Transfer');
                        frm.set_value('custom_note', r.message.custom_note);
                        frm.refresh();
                        d.hide();
                        frappe.show_alert({
                            message: __('Materials fetched successfully'),
                            indicator: 'green'
                        });
                    }
                }
            });
        }
    });

    // Update work orders table when filters change
    d.fields_dict.production_item.df.onchange = () => refresh_work_orders_table(d);
    d.fields_dict.bom_no.df.onchange = () => refresh_work_orders_table(d);

    // Initial load of work orders
    refresh_work_orders_table(d);
    d.show();
}

function refresh_work_orders_table(dialog) {
    let filters = {
        docstatus: 1,
        status: ['not in', ['Completed', 'Stopped']],
    };

    if (dialog.get_value('production_item')) {
        filters.production_item = dialog.get_value('production_item');
    }
    if (dialog.get_value('bom_no')) {
        filters.bom_no = dialog.get_value('bom_no');
    }

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Work Order',
            filters: filters,
            fields: [
                'name', 'production_item', 'item_name', 'qty', 'produced_qty',
                'material_transferred_for_manufacturing', 'expected_delivery_date'
            ],
            order_by: 'creation desc',
            limit: 50
        },
        callback: function (r) {
            let html = `
                <div class="work-orders-table">
                    <table class="table table-bordered">
                        <thead>
                            <tr>
                                <th style="width: 30px">
                                    <input type="checkbox" class="select-all">
                                </th>
                                <th>Work Order</th>
                                <th>Item Name</th>
                                <th>Qty to Manufacture</th>
                                <th>Material Transferred</th>
                                <th>Expected Delivery Date</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            if (r.message && r.message.length) {
                r.message.forEach(wo => {
                    const pending_qty = wo.qty - wo.material_transferred_for_manufacturing;
                    if (pending_qty > 0) {
                        html += `
                            <tr class="work-order-row" data-work-order="${wo.name}">
                                <td>
                                    <input type="checkbox" class="work-order-check">
                                </td>
                                <td>${wo.name}</td>
                                <td>${wo.item_name || wo.production_item}</td>
                                <td>${pending_qty}</td>
                                <td>${wo.material_transferred_for_manufacturing}</td>
                                <td>${frappe.datetime.str_to_user(wo.expected_delivery_date)}</td>
                            </tr>
                        `;
                    }
                });
            } else {
                html += `
                    <tr>
                        <td colspan="6" class="text-center text-muted">
                            No pending Work Orders found
                        </td>
                    </tr>
                `;
            }

            html += `
                        </tbody>
                    </table>
                </div>
            `;

            dialog.fields_dict.work_orders_html.$wrapper.html(html);

            // Handle select all
            dialog.$wrapper.find('.select-all').on('click', function () {
                const isChecked = $(this).is(':checked');
                dialog.$wrapper.find('.work-order-check').prop('checked', isChecked);
            });
        }
    });

    // Add custom styles
    dialog.$wrapper.find('.work-orders-table').css({
        'max-height': '600px',
        'overflow-y': 'auto',
        'margin': '10px 0'
    });

    // Make dialog wider
    dialog.$wrapper.find('.modal-dialog').css({
        'max-width': '70%',
        'width': '70%'
    });

    // Adjust table columns width
    dialog.$wrapper.find('table').css({
        'width': '100%'
    });

    frappe.dom.set_style(`
        .work-orders-table .work-order-row { cursor: pointer; }
        .work-orders-table .work-order-row:hover { background-color: var(--hover-bg); }
        .work-orders-table th { 
            position: sticky; 
            top: 0; 
            background-color: var(--gray-100); 
            z-index: 1;
            padding: 12px 8px;
            font-size: 14px;
        }
        .work-orders-table td { 
            vertical-align: middle;
            padding: 10px 8px;
            font-size: 13px;
        }
        .modal-body {
            padding: 20px;
        }
        .form-column {
            padding: 0 15px;
        }
        .section-body {
            margin-top: 20px;
        }
    `);
}
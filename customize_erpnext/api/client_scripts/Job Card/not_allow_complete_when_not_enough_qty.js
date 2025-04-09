frappe.ui.form.on('Job Card', {
    refresh: function (frm) {
        // Remove existing Complete Job button if any
        frm.page.remove_inner_button('Complete Job');
        frm.page.inner_toolbar.find('.btn-primary:contains("Submit")').hide();
        // Only show Complete Job button if quantity criteria is met
        if (frm.doc.docstatus === 1 && frm.doc.status !== 'Completed') {
            if (frm.doc.total_completed_qty >= frm.doc.qty_to_manufacture) {
                frm.page.add_inner_button(__('Complete Job'), function () {
                    frm.events.complete_job(frm);
                });
                frm.page.btn_primary.find('.btn-primary:contains("Submit")').show();
            }
        }

    },
    after_save: function (frm) {
        // Call server method to update Work Order Operation
        frappe.show_alert({
            message: `Total Completed Qty : ${frm.doc.total_completed_qty}`,
            indicator: 'green'
        }, 5);
        if (frm.doc.work_order && frm.doc.operation) {
            frappe.call({
                method: 'custom_features.custom_features.work_order.update_work_order_operation',
                args: {
                    job_card: frm.doc.name
                },
                async: false,  // Ensure update happens before save completes
                callback: function (r) {
                    if (r.exc) {
                        frappe.msgprint(__('Failed to update Work Order Operation'));
                    }
                }
            });
        }
    }
});

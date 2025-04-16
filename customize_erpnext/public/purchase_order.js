frappe.ui.form.on('Purchase Order', {
    onload: function (frm) {
        if (frm.is_new()) {
            let schedule_date = frappe.datetime.add_days(frappe.datetime.nowdate(), 7);
            frm.set_value('schedule_date', schedule_date);
            show_hide_approver(frm);
        }



    },
    refresh: function (frm) {
        show_hide_approver(frm);
        if (frm.doc.workflow_state == 'Approved') {
            frm.remove_button('Update Items');
        }
    }

});

function show_hide_approver(frm) {
    if (!frm.doc.grand_total || frm.doc.grand_total == 0) {
        frm.set_df_property('approver_1', 'hidden', 1);
        frm.set_df_property('approver_2', 'hidden', 1);
    }
    else {
        if (frm.doc.grand_total < 20000000) {
            frm.set_df_property('approver_1', 'hidden', 0);
            frm.set_df_property('approver_2', 'hidden', 1);
        }
        else {
            frm.set_df_property('approver_1', 'hidden', 0);
            frm.set_df_property('approver_2', 'hidden', 0);
        }
    }
}
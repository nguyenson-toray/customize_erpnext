frappe.ui.form.on('Purchase Request', {
    onload: function (frm) {
        if (frm.is_new()) {
            let eta = frappe.datetime.add_days(frappe.datetime.nowdate(), 7);
            frm.set_value('eta', eta);

            let creator = frm.doc.owner;
            let approver = "";
            console.log("Creator:", creator);
            frm.set_value('requester', creator);
            if (creator === 'Administrator') {
                frm.set_value('approver', "erp.tiqn.com.vn");
            }
            else {
                frappe.db.get_value('Employee',
                    { user_id: creator },
                    ['employee', 'employee_name', 'reports_to'],
                    function (emp) {
                        console.log("Employee Details:", emp);
                        if (emp.reports_to) {
                            frm.set_value('emp_id', emp.employee);
                            frm.set_value('requester_name', emp.employee_name);
                            frm.refresh_field(['approver',]);
                            frappe.call({
                                method: 'customize_erpnext.api.purchase_request.get_email_from_emp_id',
                                args: {
                                    emp_id: emp.reports_to
                                },
                                callback: function (r) {
                                    console.log("get_email_from_emp_id", r.message);
                                    if (r.message) {
                                        frm.set_value('approver', r.message);
                                    }
                                }
                            });
                            frappe.call({
                                method: 'customize_erpnext.api.purchase_request.get_employee_name_from_emp_id',
                                args: {
                                    emp_id: emp.reports_to
                                },
                                callback: function (r) {
                                    console.log("get_employee_name_from_emp_id", r.message);
                                    if (r.message) {
                                        frm.set_value('approver_name', r.message);
                                    }
                                }
                            });
                        }
                        else {
                            frappe.throw(__(`reports_to is not defined for ${creator}`))
                        }
                    }
                );
            }

        }
    },
    dept: function (frm) {
        set_value(frm);
    }
});

function set_value(frm) {
    switch (frm.doc.dept) {
        case 'Operation Management - TIQN':
            // frm.set_value('approver', 'son.nt@tiqn.com.vn');
            frm.set_value('dept_short', 'HRA');
            break;
        case 'Accounting':
            // frm.set_value('approver', 'ni.nty@tiqn.com.vn');
            frm.set_value('dept_short', 'ACC');
            break;
        case 'Production':
            // frm.set_value('approver', 'phong.lt@tiqn.com.vn');
            frm.set_value('dept_short', 'PRO');
            break;
        case 'Production':
            frm.set_value('approver', 'uyen.pnt@tiqn.com.vn');
            frm.set_value('dept_short', 'CAN');
            break;
        default:
        // code block
    }
}


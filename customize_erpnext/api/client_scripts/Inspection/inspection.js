frappe.ui.form.on('Inspection', {

    refresh: function (frm) {
        calculate_values(frm);
        validate_quantity(frm);
        calculate_group_quantities(frm);
    },
    quantity: function (frm) {
        calculate_values(frm);
        validate_quantity(frm);
        calculate_group_quantities(frm);
    },
    inspected_qty: function (frm) {
        validate_inspected_qty(frm);
    },
    inspected_qty_ok: function (frm) {
        validate_inspected_qty(frm);
    },
    item: function (frm) {
        if (frm.doc.item) {
            frappe.db.get_value('Item', { 'item_name': frm.doc.item }, ['name'])
                .then(r => {
                    if (r.message && r.message.name) {
                        return frappe.db.get_doc('Item', r.message.name);
                    }
                })
                .then(item_doc => {
                    if (item_doc && item_doc.attributes) {
                        item_doc.attributes.forEach(attr => {
                            if (attr.attribute === 'Color') {
                                frm.set_value('color', attr.attribute_value);
                            }
                            if (attr.attribute === 'Size') {
                                frm.set_value('size', attr.attribute_value);
                            }
                        });
                        frm.refresh_fields(['color', 'size']);
                    }
                });
        } else {
            frm.set_value('color', '');
            frm.set_value('size', '');
            frm.refresh_fields(['color', 'size']);
        }
    },
    after_save: function (frm) {
        // Kiểm tra defect trùng lặp
        let defects = {};
        let qty_defects = 0;
        let hasDuplicate = false;

        if (frm.doc.inspection_detail) {
            frm.doc.inspection_detail.forEach(function (row) {
                if (defects[row.defect]) {
                    hasDuplicate = true;
                    frappe.throw(__(`Defect "${row.defect}" appears multiple times. Duplicate defects are not allowed.`));
                    return false;
                }
                defects[row.defect] = true;
            });
        }

        // Kiểm tra quantity
        validate_quantity();
        validate_inspected_qty();
        calculate_group_quantities(frm);

        // Update Job Card Time Log
        update_job_card_time_log(frm);
    },
});

frappe.ui.form.on('Inspection Detail', {
    quantity: function (frm, cdt, cdn) {
        calculate_values(frm);
        calculate_group_quantities(frm);
    },
    inspection_detail_remove: function (frm, cdt, cdn) {
        calculate_values(frm);
        calculate_group_quantities(frm);
    },
    defect: function (frm, cdt, cdn) {
        calculate_group_quantities(frm);
    }
});

function calculate_group_quantities(frm) {
    if (!frm || !frm.doc || !frm.doc.inspection_detail) return false;

    // Khởi tạo giá trị cho các nhóm
    let groups = {
        group_a: 0,
        group_b: 0,
        group_c: 0,
        group_d: 0,
        group_e: 0,
        group_f: 0,
        group_g: 0,
        group_h: 0
    };

    // Duyệt qua từng dòng trong inspection_detail
    frm.doc.inspection_detail.forEach(function (row) {
        if (!row.defect || !row.quantity) return;

        // Lấy ký tự đầu tiên của defect và chuyển về chữ hoa
        let firstChar = row.defect.charAt(0).toUpperCase();

        // Cộng quantity vào nhóm tương ứng
        switch (firstChar) {
            case 'A':
                groups.group_a += row.quantity;
                break;
            case 'B':
                groups.group_b += row.quantity;
                break;
            case 'C':
                groups.group_c += row.quantity;
                break;
            case 'D':
                groups.group_d += row.quantity;
                break;
            case 'E':
                groups.group_e += row.quantity;
                break;
            case 'F':
                groups.group_f += row.quantity;
                break;
            case 'G':
                groups.group_g += row.quantity;
                break;
            case 'H':
                groups.group_h += row.quantity;
                break;
        }
    });

    // Cập nhật giá trị cho form
    for (let group in groups) {
        frm.set_value(group, groups[group]);
    }

    // Refresh các trường
    frm.refresh_fields(['group_a', 'group_b', 'group_c', 'group_d',
        'group_e', 'group_f', 'group_g', 'group_h']);
}

function calculate_values(frm) {
    if (!frm || !frm.doc) return false;
    let total_ng = 0;
    if (frm.doc.inspection_detail) {
        frm.doc.inspection_detail.forEach(function (row) {
            total_ng += row.quantity || 0;
        });
    }
    if (total_ng > frm.doc.quantity) {
        frappe.throw(__(`Total defect quantity exceeds inspection quantity`));
        return false;
    }
    else {
        frm.set_value('ng', total_ng);
    }

    if (frm.doc.quantity && frm.doc.quantity > 0) {
        let ration = (total_ng / frm.doc.quantity) * 100;
        frm.set_value('ration', ration);
    } else {
        frm.set_value('ration', 0);
    }
    frm.set_value('ok', frm.doc.quantity - total_ng);
    frm.refresh_fields(['quantity', 'ng', 'ration']);
}

function validate_quantity(frm) {
    if (!frm || !frm.doc) return false;

    if (frm.doc.quantity > frm.doc.total_quantity) {
        frappe.throw(__('Quantity must less than or equal Total Quantity'));
        return false;
    }

    if (frm.doc.work_order && frm.doc.inspection12) {
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Inspection',
                filters: {
                    'work_order': frm.doc.work_order,
                    'inspection12': frm.doc.inspection12,
                    'docstatus': ['!=', 2],
                    'name': ['!=', frm.doc.name]
                },
                fields: ['quantity']
            },
            callback: function (r) {
                if (r.message) {
                    let total_existing_qty = 0;
                    r.message.forEach(function (doc) {
                        total_existing_qty += doc.quantity || 0;
                    });

                    let total_qty = total_existing_qty + frm.doc.quantity;

                    frappe.db.get_value('Work Order', frm.doc.work_order, 'qty')
                        .then(r => {
                            if (r.message && r.message.qty) {
                                let work_order_qty = r.message.qty;

                                if (total_qty > work_order_qty) {
                                    frappe.throw(__(
                                        'Total Inspection quantity ({0}) for Work Order {1} exceeds Work Order quantity ({2})',
                                        [total_qty, frm.doc.work_order, work_order_qty]
                                    ));
                                    return false;
                                }
                            }
                        });
                }
            }
        });
    }
}

function validate_inspected_qty(frm) {
    if (!frm || !frm.doc) return false;
    if (frm.doc.inspected_qty > frm.doc.quantity) {
        frappe.throw(__('Inspected Quantity must less than or equal Quantity'));
        return false;
    }
    if (frm.doc.inspected_qty_ok > frm.doc.inspected_qty) {
        frappe.throw(__('Inspected Quantity OK must less than or equal Inspected Quantity'));
        return false;
    }
    frm.set_value('scrap', frm.doc.inspected_qty - frm.doc.inspected_qty_ok);
    frm.refresh_fields(['scrap', 'inspected_qty', 'inspected_qty_ok']);
}
function update_job_card_time_log(frm) {
    if (!frm.doc.job_card) return;

    // Helper function để tạo datetime theo định dạng chuẩn
    function createDateTime(dateStr, timeStr) {
        if (!dateStr || !timeStr) {
            let now = frappe.datetime.now_datetime();
            return now;
        }

        try {
            // Định dạng ngày: dateStr là '2025-01-06' hoặc '06/01/2025'
            let formattedDate = '';
            if (dateStr.includes('/')) {
                let [day, month, year] = dateStr.split('/');
                formattedDate = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
            } else {
                formattedDate = dateStr;
            }

            // Đảm bảo timeStr có format HH:mm:ss
            if (timeStr.length <= 5) { // Nếu chỉ có HH:mm
                timeStr = timeStr + ":00";
            }

            return formattedDate + " " + timeStr;
        } catch (e) {
            console.error("Error formatting date time:", e);
            return frappe.datetime.now_datetime();
        }
    }

    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Job Card',
            name: frm.doc.job_card
        },
        callback: function (r) {
            if (r.message) {
                let job_card = r.message;

                let from_datetime = createDateTime(frm.doc.date, frm.doc.from_time || "08:00:00");
                let to_datetime = createDateTime(frm.doc.date, frm.doc.to_time || "17:00:00");

                console.log("Input values:");
                console.log("Date:", frm.doc.date);
                console.log("From time:", frm.doc.from_time);
                console.log("To time:", frm.doc.to_time);
                console.log("Formatted values:");
                console.log("From datetime:", from_datetime);
                console.log("To datetime:", to_datetime);

                let existing_time_log = job_card.time_logs.find(log =>
                    log.custom_inspection === frm.doc.name
                );

                if (existing_time_log) {
                    frappe.call({
                        method: 'frappe.client.set_value',
                        args: {
                            doctype: 'Job Card Time Log',
                            name: existing_time_log.name,
                            fieldname: {
                                'completed_qty': frm.doc.quantity,
                                'custom_inspection': frm.doc.name,
                                'from_time': from_datetime,
                                'to_time': to_datetime
                            }
                        },
                        callback: function (r) {
                            if (r.exc) {
                                frappe.msgprint(__('Error updating time log: ' + r.exc));
                            }
                        }
                    });
                } else {
                    let insert_data = {
                        doctype: 'Job Card Time Log',
                        parent: frm.doc.job_card,
                        parenttype: 'Job Card',
                        parentfield: 'time_logs',
                        custom_inspection: frm.doc.name,
                        completed_qty: frm.doc.quantity,
                        from_time: from_datetime,
                        to_time: to_datetime
                    };

                    frappe.call({
                        method: 'frappe.client.insert',
                        args: {
                            doc: insert_data
                        },
                        callback: function (r) {
                            if (r.exc) {
                                frappe.msgprint(__('Error creating time log: ' + r.exc));
                            }
                        }
                    });
                }
            }
        }
    });
}
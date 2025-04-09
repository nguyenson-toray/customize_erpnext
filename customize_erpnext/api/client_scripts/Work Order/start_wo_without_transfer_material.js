frappe.ui.form.on('Work Order', {
    refresh: function (frm) {
        // Kiểm tra điều kiện skip_transfer
        if (frm.doc.skip_transfer && frm.doc.docstatus === 1 && frm.doc.status === "Not Started") {

            // Thêm nút Start
            frm.add_custom_button(__('Start'), function () {
                frappe.confirm(
                    'Bạn có chắc chắn muốn bắt đầu Work Order này?',
                    function () {
                        frappe.call({
                            method: 'custom_features.custom_features.work_order.start_wo_without_transfer_material',
                            args: {
                                doc_name: frm.doc.name
                            },
                            callback: function (r) {
                                if (r.message) {
                                    frappe.show_alert({
                                        message: __('Work Order đã bắt đầu thành công'),
                                        indicator: 'green'
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }).addClass('btn-primary');
        }
        // Chỉ kiểm tra khi document chưa submit (docstatus === 0)
        if (frm.doc.docstatus === 0 && frm.doc.work_order) {
            // Lấy tổng quantity của tất cả Inspection liên quan đến Work Order này
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Inspection',
                    filters: {
                        'work_order': frm.doc.work_order,
                        'docstatus': 1  // Chỉ tính các Inspection đã submit
                    },
                    fields: ['quantity']
                },
                callback: function (r) {
                    if (r.message) {
                        // Tính tổng quantity từ các Inspection đã submit
                        let total_inspected_qty = r.message.reduce((sum, inspection) =>
                            sum + (inspection.quantity || 0), 0
                        );

                        // Thêm quantity của inspection hiện tại
                        total_inspected_qty += frm.doc.quantity || 0;

                        // Lấy thông tin Work Order để so sánh quantity
                        frappe.call({
                            method: 'frappe.client.get',
                            args: {
                                doctype: 'Work Order',
                                name: frm.doc.work_order
                            },
                            callback: function (r) {
                                if (r.message) {
                                    let wo = r.message;

                                    // So sánh tổng quantity
                                    if (total_inspected_qty < wo.qty) {
                                        // Ẩn nút Submit nếu tổng quantity vượt quá
                                        frm.page.btn_primary.hide();
                                        frappe.show_alert({
                                            message: __('Tổng số lượng kiểm tra nhỏ hơn số lượng của Work Order'),
                                            indicator: 'red'
                                        });
                                    }
                                }
                            }
                        });
                    }
                }
            });
        }
    },
    // Thêm validate để kiểm tra khi người dùng thay đổi quantity
    quantity: function (frm) {
        // Gọi lại hàm refresh để kiểm tra lại điều kiện
        frm.trigger('refresh');
    }
});
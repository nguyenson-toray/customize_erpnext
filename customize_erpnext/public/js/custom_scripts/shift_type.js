frappe.ui.form.on('Shift Type', {
    after_save: function (frm) {
        // Hiển thị hộp thoại xác nhận
        frappe.confirm(
            __('Update Process Attendance After and Last Sync of Checkin for all other Shift Types?'),
            function () {
                // 1. Lấy danh sách các Shift Type khác
                frappe.db.get_list('Shift Type', {
                    filters: {
                        name: ['!=', frm.doc.name]
                    },
                    fields: ['name'],
                    limit: 1000
                }).then(records => {
                    if (records && records.length > 0) {
                        // 2. Tạo danh sách các lệnh cập nhật
                        let promises = records.map(row => {
                            return frappe.db.set_value('Shift Type', row.name, {
                                'process_attendance_after': frm.doc.process_attendance_after,
                                'last_sync_of_checkin': frm.doc.last_sync_of_checkin
                            });
                        });

                        // 3. Thực thi và thông báo kết quả
                        Promise.all(promises).then(() => {
                            frappe.show_alert({
                                message: __('Finished updating {0} other shift types.', [records.length]),
                                indicator: 'green'
                            });
                        }).catch(err => {
                            console.error(err);
                            frappe.msgprint(__('An error occurred during bulk update.'));
                        });
                    }
                });
            }
        ); // Kết thúc frappe.confirm
    }
});
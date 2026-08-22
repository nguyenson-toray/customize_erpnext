frappe.listview_settings['Resignation Application'] = {
    add_fields: ['docstatus', 'relieving_date', 'handover_progress'],

    get_indicator: function (doc) {
        if (doc.docstatus === 2) return [__('Withdrawn'), 'orange', 'docstatus,=,2'];
        if (doc.docstatus === 0) return [__('Draft'), 'red', 'docstatus,=,0'];

        // Đã duyệt: điều HR cần nhìn thấy là ngày nghỉ tới chưa, không phải "Submitted".
        const today = frappe.datetime.get_today();
        if (doc.relieving_date && doc.relieving_date < today) {
            return [__('Left'), 'gray', 'docstatus,=,1'];
        }
        return [__('Approved'), 'blue', 'docstatus,=,1'];
    },
};

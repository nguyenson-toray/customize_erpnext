frappe.ui.form.on('Batch', {
    refresh: function (frm) {
        if (frm.is_new()) {
            frm.add_custom_button(__('Generate Batch ID'), function () {
                generate_batch_id(frm);
            });
        }
    },
    item: function (frm) {
        if (frm.is_new()) frm.set_value('batch_id', '');
    },
    custom_lot_number: function (frm) {
        if (frm.is_new()) frm.set_value('batch_id', '');
    },
    custom_roll_number: function (frm) {
        if (frm.is_new()) frm.set_value('batch_id', '');
    }
});

async function generate_batch_id(frm) {
    const { item, custom_lot_number, custom_roll_number } = frm.doc;

    if (!item) {
        frappe.throw(__('Vui lòng chọn Item trước'));
    }
    if (!custom_lot_number || !String(custom_lot_number).trim()) {
        frappe.throw(__('Vui lòng nhập Lot Number'));
    }
    if (!custom_roll_number || !String(custom_roll_number).trim()) {
        frappe.throw(__('Vui lòng nhập Roll Number'));
    }

    const r = await frappe.call({
        method: 'customize_erpnext.api.batch.batch_utils.get_batch_id_components',
        args: { item_code: item }
    });

    if (!r || !r.message) {
        frappe.throw(__('Không lấy được thông tin Item'));
    }

    const { template_name, color } = r.message;
    // Use lot & roll exactly as entered (no zero-padding).
    const lot = String(custom_lot_number).trim();
    const roll = String(custom_roll_number).trim();

    const batch_id = color
        ? `${template_name}|${color}|${lot}|${roll}`
        : `${template_name}|${lot}|${roll}`;

    frm.set_value('batch_id', batch_id);
    if (color) frm.set_value('custom_color', color);
    frm.refresh_fields(['batch_id', 'custom_color']);
    frappe.show_alert({ message: __('Batch ID: {0}', [batch_id]), indicator: 'green' }, 5);
}

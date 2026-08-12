frappe.ui.form.on('Batch', {
    refresh: function (frm) {
        if (frm.is_new()) {
            frm.add_custom_button(__('Generate Batch ID'), function () {
                generate_batch_id(frm);
            });
        }
    },
    item: function (frm) {
        if (frm.is_new()) {
            frm.set_value('batch_id', '');
            frm.set_value('custom_color', '');
        }
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
        frappe.throw(__('Please select an Item first'));
    }
    const lot = custom_lot_number ? String(custom_lot_number).trim() : '';
    const roll = custom_roll_number ? String(custom_roll_number).trim() : '';
    if (!lot) {
        frappe.throw(__('Please enter Lot Number'));
    }
    if (!roll) {
        frappe.throw(__('Please enter Roll Number'));
    }
    if (lot.includes('|') || roll.includes('|')) {
        frappe.throw(__('Lot Number and Roll Number must not contain the character |'));
    }

    const r = await frappe.call({
        method: 'customize_erpnext.api.batch.batch_utils.get_batch_id_components',
        args: { item_code: item }
    });

    if (!r || !r.message) {
        frappe.throw(__('Could not fetch Item details'));
    }

    const { template_name, color } = r.message;
    // Use lot & roll exactly as entered (no zero-padding).

    const batch_id = color
        ? `${template_name}|${color}|${lot}|${roll}`
        : `${template_name}|${lot}|${roll}`;

    frm.set_value('batch_id', batch_id);
    if (color) frm.set_value('custom_color', color);
    frappe.show_alert({ message: __('Batch ID: {0}', [batch_id]), indicator: 'green' }, 5);
}

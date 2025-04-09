frappe.ui.form.on('Item', {
  refresh: function (frm) {
    if (frm.doc.item_name && frm.doc.item_code) {
      let value = `${frm.doc.item_name} - ${frm.doc.item_code}`;
      frm.set_value('custom_field_for_test', value);
    }
  }
});

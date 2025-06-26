// Client Script for Stock Reconciliation
// Purpose: Trim custom_invoice_number field in child table rows on save
// Trigger: validate

frappe.ui.form.on('Stock Reconciliation', {
    validate: function (frm) {
        // Iterate through all items in the child table
        if (frm.doc.items && frm.doc.items.length > 0) {
            let trimmed_count = 0;

            frm.doc.items.forEach(function (item) {
                // Check if custom_invoice_number field exists and has a value
                if (item.custom_invoice_number && typeof item.custom_invoice_number === 'string') {
                    let original_value = item.custom_invoice_number;
                    let trimmed_value = original_value.trim();

                    // Update the field only if the value has changed after trimming
                    if (original_value !== trimmed_value) {
                        item.custom_invoice_number = trimmed_value;
                        trimmed_count++;
                    }
                }
            });

            // Show notification if any fields were trimmed
            if (trimmed_count > 0) {
                frappe.show_alert({
                    message: __(`${trimmed_count} invoice number(s) have been trimmed of extra spaces`),
                    indicator: 'blue'
                }, 4);
            }
        }
    }
});

// Event handler for individual child table row changes
frappe.ui.form.on('Stock Reconciliation Item', {
    custom_invoice_number: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Trim the field when user moves out of the field
        if (row.custom_invoice_number && typeof row.custom_invoice_number === 'string') {
            let trimmed_value = row.custom_invoice_number.trim();

            if (row.custom_invoice_number !== trimmed_value) {
                frappe.model.set_value(cdt, cdn, 'custom_invoice_number', trimmed_value);
            }
        }
    }
});
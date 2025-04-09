frappe.ui.form.on('BOM', {
    refresh: function (frm) {
        // Add custom button in Custom Features group
        frm.add_custom_button(__('Copy For All Size - Same Color'), function () {
            frappe.call({
                method: 'custom_features.custom_features.bom.copy_bom_for_same_color',
                args: {
                    doc: frm.doc
                },
                callback: function (r) {
                    if (r.message && r.message.length > 0) {
                        // Open BOM list view with the created BOMs
                        // Add current BOM to the list
                        let bomList = [...r.message, frm.doc.name];
                        frappe.confirm('Created ' + r.message.length + ' BOMs successfully, Are you sure you want to open list?',
                            () => {
                                // action to perform if Yes is selected
                                frappe.set_route('List', 'BOM', {
                                    'name': ['in', bomList]
                                });
                            }, () => {
                                // action to perform if No is selected
                                frm.reload_doc();
                            });
                    }
                }
            });
        }, __('Custom Features'));
        formatAllRows(frm);
        formatIntegerQuantities(frm);
    },

    item: function (frm) {
        if (frm.doc.item) {
            frappe.call({
                method: 'custom_features.custom_features.bom.get_item_name_for_bom',
                args: {
                    item_code: frm.doc.item
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value('custom_item_name_bom', r.message);
                    }
                }
            });
        }
    }
});

// Handle BOM Item events
frappe.ui.form.on('BOM Item', {
    form_render: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        formatRow(cdn, row);
        formatQuantityCell(cdn, row.qty);
    },

    custom_is_difference: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        formatRow(cdn, row);
    },

    qty: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        formatQuantityCell(cdn, row.qty);
    },

    item_code: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        formatRow(cdn, row);
    }
});

// Function to get background color based on item code prefix
function getBackgroundColor(itemCode) {
    if (!itemCode) return '';

    const prefixColors = {
        'M-FAB': '#f0fff0', // honeydew
        'M-INT': '#e6e6fa', // lavender
        'M-PAD': '#f5f5f5', // whitesmoke
        'M-SEW': '#dcdcdc', // gainsboro
        'M-THR': '#e0ffff', // lightcyan
        'M-PAC': '#f5fffa'  // mintcream
    };

    for (let prefix in prefixColors) {
        if (itemCode.startsWith(prefix)) {
            return prefixColors[prefix];
        }
    }
    return '';
}

// Function to format a single row
function formatRow(cdn, row) {
    setTimeout(function () {
        const rowElement = $(`div[data-name="${cdn}"]`);
        // Get background color based on item code prefix
        const backgroundColor = getBackgroundColor(row.item_code);

        if (row.custom_is_difference) {
            // For different items - bold and red text, with background color
            rowElement.find('.field-area').css({
                'font-weight': 'bold',
                'color': '#ff0000'
            });
            rowElement.css({
                'background-color': backgroundColor,
                'border-left': ''
            });
        } else {
            // Reset text style if not different
            rowElement.find('.field-area').css({
                'font-weight': '',
                'color': ''
            });

            // Apply background color based on item code prefix
            rowElement.css({
                'background-color': backgroundColor,
                'border-left': ''
            });
        }
    }, 100);
}

// Function to format all rows
function formatAllRows(frm) {
    if (!frm.doc.items) return;

    frm.doc.items.forEach(function (item) {
        formatRow(item.name, item);
    });
}

// Function to format quantity cell
function formatQuantityCell(cdn, qty) {
    setTimeout(function () {
        const qtyCell = $(`div[data-name="${cdn}"] [data-fieldname="qty"]`);
        if (Number.isInteger(parseFloat(qty))) {
            qtyCell.css({
                'font-weight': 'bold',
                'color': '#0000FF'
            });
        } else {
            qtyCell.css({
                'font-weight': '',
                'color': ''
            });
        }
    }, 100);
}

// Function to format all integer quantities
function formatIntegerQuantities(frm) {
    if (!frm.doc.items) return;

    frm.doc.items.forEach(function (item) {
        formatQuantityCell(item.name, item.qty);
    });
}
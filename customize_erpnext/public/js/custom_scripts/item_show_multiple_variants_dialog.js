// Ghi đè hàm show_multiple_variants_dialog trong erpnext.item
if (!erpnext.item._original_show_multiple_variants_dialog) {
    erpnext.item._original_show_multiple_variants_dialog = erpnext.item.show_multiple_variants_dialog;
}

// 
erpnext.item.show_multiple_variants_dialog = function (frm) {
    var me = this;

    let promises = [];
    let attr_val_fields = {};

    function make_fields_from_attribute_values(attr_dict) {
        let fields = [];
        const sorted_attributes = Object.keys(attr_dict);
        const total_attributes = sorted_attributes.length;
        const cols_per_section = 5; // Số cột trên mỗi hàng

        // Tạo các section với 5 cột
        let current_col = 0;

        sorted_attributes.forEach((name, i) => {
            // Tạo section break mới khi bắt đầu hoặc đạt đến giới hạn cột
            if (i % cols_per_section === 0) {
                fields.push({ fieldtype: 'Section Break' });
                current_col = 0;
            }

            // Tạo column break với label là tên thuộc tính
            fields.push({
                fieldtype: 'Column Break',
                label: name,
                fieldname: `col_${name}`
            });
            current_col++;

            // Thêm trường tìm kiếm cho mỗi thuộc tính
            fields.push({
                fieldtype: 'Data',
                label: __('Tìm kiếm {0}', [name]),
                fieldname: `${name}_search`,
                onchange: function () {
                    let search_value = this.get_value().toLowerCase();
                    // Lọc các hộp kiểm theo giá trị tìm kiếm
                    let checkboxes = $(this.wrapper).parent().find('.checkbox');
                    checkboxes.each(function () {
                        let label = $(this).find('label').text().toLowerCase();
                        if (label.includes(search_value)) {
                            $(this).show();
                        } else {
                            $(this).hide();
                        }
                    });
                }
            });

            // Sử dụng giá trị thuộc tính theo thứ tự gốc
            const sorted_values = attr_dict[name];

            sorted_values.forEach(value => {
                fields.push({
                    fieldtype: 'Check',
                    label: value,
                    fieldname: value,
                    default: 0,
                    onchange: function () {
                        let selected_attributes = get_selected_attributes();
                        let lengths = [];
                        Object.keys(selected_attributes).map(key => {
                            lengths.push(selected_attributes[key].length);
                        });
                        if (lengths.includes(0)) {
                            me.multiple_variant_dialog.get_primary_btn().html(__('Create Variants'));
                            me.multiple_variant_dialog.disable_primary_action();
                        } else {
                            let no_of_combinations = lengths.reduce((a, b) => a * b, 1);
                            let msg;
                            if (no_of_combinations === 1) {
                                msg = __('Make {0} Variant', [no_of_combinations]);
                            } else {
                                msg = __('Make {0} Variants', [no_of_combinations]);
                            }
                            me.multiple_variant_dialog.get_primary_btn().html(msg);
                            me.multiple_variant_dialog.enable_primary_action();
                        }
                    }
                });
            });
        });

        return fields;
    }

    function make_and_show_dialog(fields) {
        me.multiple_variant_dialog = new frappe.ui.Dialog({
            title: __('Select Attribute Values'),
            fields: [
                frm.doc.image ? {
                    fieldtype: 'Check',
                    label: __('Create a variant with the template image.'),
                    fieldname: 'use_template_image',
                    default: 0
                } : null,
                {
                    fieldtype: 'HTML',
                    fieldname: 'help',
                    options: `<label class="control-label">
                        ${__('Select at least one value from each of the attributes.')}
                    </label>`,
                }
            ].concat(fields).filter(Boolean)
        });

        // Thiết lập chiều rộng của dialog lớn hơn
        me.multiple_variant_dialog.$wrapper.find('.modal-dialog').css({
            'max-width': '90%',
            'width': '1200px'  // Dialog rộng hơn
        });

        // CSS để điều chỉnh kích thước cột trong dialog
        me.multiple_variant_dialog.$wrapper.find('.form-column').css({
            'padding-right': '10px',
            'padding-left': '10px'
        });

        me.multiple_variant_dialog.set_primary_action(__('Create Variants'), () => {
            let selected_attributes = get_selected_attributes();
            let use_template_image = me.multiple_variant_dialog.get_value('use_template_image');

            me.multiple_variant_dialog.hide();
            frappe.call({
                method: 'erpnext.controllers.item_variant.enqueue_multiple_variant_creation',
                args: {
                    item: frm.doc.name,
                    args: selected_attributes,
                    use_template_image: use_template_image
                },
                callback: function (r) {
                    if (r.message === 'queued') {
                        frappe.show_alert({
                            message: __('Variant creation has been queued.'),
                            indicator: 'orange'
                        });
                    } else {
                        frappe.show_alert({
                            message: __("{0} variants created.", [r.message]),
                            indicator: 'green'
                        });
                    }
                }
            });
        });

        $($(me.multiple_variant_dialog.$wrapper.find('.form-column')).find('.frappe-control')).css('margin-bottom', '0px');

        me.multiple_variant_dialog.disable_primary_action();
        me.multiple_variant_dialog.clear();
        me.multiple_variant_dialog.show();
    }

    function get_selected_attributes() {
        let selected_attributes = {};
        me.multiple_variant_dialog.$wrapper.find('.form-column').each((i, col) => {
            let column_label = $(col).find('.column-label');
            if (column_label.length === 0) return;

            let attribute_name = column_label.html().trim();
            if (!attribute_name) return;

            selected_attributes[attribute_name] = [];
            let checked_opts = $(col).find('.checkbox input');
            checked_opts.each((i, opt) => {
                if ($(opt).is(':checked')) {
                    selected_attributes[attribute_name].push($(opt).attr('data-fieldname'));
                }
            });
        });

        return selected_attributes;
    }

    frm.doc.attributes.forEach(function (d) {
        if (!d.disabled) {
            let p = new Promise(resolve => {
                if (!d.numeric_values) {
                    frappe.call({
                        method: 'frappe.client.get_list',
                        args: {
                            doctype: 'Item Attribute Value',
                            filters: [
                                ['parent', '=', d.attribute]
                            ],
                            fields: ['attribute_value'],
                            limit_page_length: 0,
                            parent: 'Item Attribute',
                            order_by: 'idx'
                        }
                    }).then((r) => {
                        if (r.message) {
                            attr_val_fields[d.attribute] = r.message.map(function (d) { return d.attribute_value; });
                            resolve();
                        }
                    });
                } else {
                    frappe.call({
                        method: 'frappe.client.get',
                        args: {
                            doctype: 'Item Attribute',
                            name: d.attribute
                        }
                    }).then((r) => {
                        if (r.message) {
                            const from = r.message.from_range;
                            const to = r.message.to_range;
                            const increment = r.message.increment;

                            let values = [];
                            for (var i = from; i <= to; i = flt(i + increment, 6)) {
                                values.push(i);
                            }
                            attr_val_fields[d.attribute] = values;
                            resolve();
                        }
                    });
                }
            });

            promises.push(p);
        }
    }, this);

    Promise.all(promises).then(() => {
        let fields = make_fields_from_attribute_values(attr_val_fields);
        make_and_show_dialog(fields);
    });
};
// Ghi đè hàm show_multiple_variants_dialog trong erpnext.item
if (!erpnext.item._original_show_multiple_variants_dialog) {
    erpnext.item._original_show_multiple_variants_dialog = erpnext.item.show_multiple_variants_dialog;
}

erpnext.item.show_multiple_variants_dialog = function (frm) {
    var me = this;

    let promises = [];
    let attr_val_fields = {};

    function make_fields_from_attribute_values(attr_dict) {
        let fields = [];
        const sorted_attributes = Object.keys(attr_dict);
        const cols_per_section = 5;

        sorted_attributes.forEach((name, i) => {
            if (i % cols_per_section === 0) {
                fields.push({ fieldtype: 'Section Break' });
            }

            fields.push({
                fieldtype: 'Column Break',
                label: name,
                fieldname: `col_${name}`
            });

            fields.push({
                fieldtype: 'Data',
                label: __('Search {0}', [name]),
                fieldname: `${name}_search`,
                onchange: function () {
                    let search_value = this.get_value().toLowerCase();
                    let checkboxes = $(this.wrapper).closest('.form-column').find('.checkbox');
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

            fields.push({
                fieldtype: 'Text',
                label: __('Enter value (one per line)'),
                fieldname: `${name}_manual`,
                onchange: function () {
                    let manual_values = this.get_value().split('\n').map(v => v.trim()).filter(v => v);
                    let attribute_name = name;
                    let not_found_values = [];

                    let available_values = [];
                    let available_values_lower = [];
                    let checkboxes = $(this.wrapper).closest('.form-column').find('.checkbox');
                    checkboxes.each(function () {
                        let value = $(this).find('label').text().trim();
                        available_values.push(value);
                        available_values_lower.push(value.toLowerCase());
                    });

                    // Tạo một tập hợp các giá trị nhập vào để dễ dàng kiểm tra
                    let manual_values_set = new Set(manual_values.map(v => v.toLowerCase()));

                    // Duyệt qua tất cả các checkbox
                    checkboxes.each(function () {
                        let label = $(this).find('label').text().trim();
                        let label_lower = label.toLowerCase();
                        let checkbox_input = $(this).find('input');

                        if (manual_values_set.has(label_lower)) {
                            if (!checkbox_input.is(':checked')) {
                                checkbox_input.prop('checked', true).trigger('change');
                            }
                        } else {
                            if (checkbox_input.is(':checked')) {
                                checkbox_input.prop('checked', false).trigger('change');
                            }
                        }
                    });

                    // Kiểm tra các giá trị không tồn tại
                    manual_values.forEach(value => {
                        if (!available_values_lower.includes(value.toLowerCase())) {
                            not_found_values.push(value);
                        }
                    });

                    if (not_found_values.length > 0) {
                        let attribute_link = `<a href="/app/item-attribute/${encodeURIComponent(attribute_name)}" target="_blank">Thêm giá trị mới</a>`;
                        frappe.msgprint({
                            title: __('Attribute Value Not Found'),
                            indicator: 'orange',
                            message: __('The following values do not exist in the attribute {0}: {1}<br><br>{2}',
                                [attribute_name, not_found_values.join(', '), attribute_link])
                        });
                    }
                }
            });

            // Add HTML containers for checked and unchecked checkboxes
            fields.push({
                fieldtype: 'HTML',
                fieldname: `${name}_checkbox_containers`,
                options: `<div class="checkbox-containers" data-attribute="${name}">
                    <div class="checked-container mb-2" style="display:none;">
                        <div class="checked-header font-weight-bold text-success" style="padding: 5px 0; margin-bottom: 5px; border-bottom: 1px solid #ccc;">
                            ${__('Selected Values')}
                        </div>
                        <div class="checked-checkboxes"></div>
                    </div>
                    <div class="unchecked-container">
                        <div class="unchecked-header font-weight-bold" style="padding: 5px 0; margin-bottom: 5px; border-bottom: 1px solid #ccc;">
                            ${__('Available Values')}
                        </div>
                        <div class="unchecked-checkboxes"></div>
                    </div>
                </div>`
            });

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

                        // Move the checkbox to appropriate container
                        let column = $(this.wrapper).closest('.form-column');
                        let attributeName = column.find('.column-label').text().trim();
                        let isChecked = $(this.wrapper).find('input').is(':checked');

                        // Move checkbox to appropriate container
                        moveCheckboxToGroup(this.wrapper, attributeName, isChecked);
                    }
                });
            });
        });

        return fields;
    }

    // Function to move checkbox to appropriate group (checked or unchecked)
    function moveCheckboxToGroup(checkboxWrapper, attributeName, isChecked) {
        let column = $(checkboxWrapper).closest('.form-column');
        let checkedContainer = column.find('.checked-checkboxes');
        let uncheckedContainer = column.find('.unchecked-checkboxes');

        if (isChecked) {
            checkedContainer.append(checkboxWrapper);
            column.find('.checked-container').show();
        } else {
            uncheckedContainer.append(checkboxWrapper);

            // Hide the checked container if no checkboxes are checked
            if (checkedContainer.find('.checkbox').length === 0) {
                column.find('.checked-container').hide();
            }
        }
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

        me.multiple_variant_dialog.$wrapper.find('.modal-dialog').css({
            'max-width': '90%',
            'width': '1200px'
        });

        me.multiple_variant_dialog.$wrapper.find('.form-column').css({
            'padding-right': '10px',
            'padding-left': '10px'
        });

        me.multiple_variant_dialog.$wrapper.find('textarea').css({
            'height': '140px',
            'min-height': '140px',
            'max-height': '140px',
            'overflow-y': 'auto'
        });

        // For each column, reorganize checkboxes
        setTimeout(function () {
            me.multiple_variant_dialog.$wrapper.find('.form-column').each(function () {
                let column = $(this);
                let attributeName = column.find('.column-label').text().trim();
                if (!attributeName) return;

                let checkboxContainers = column.find(`.checkbox-containers[data-attribute="${attributeName}"]`);
                if (checkboxContainers.length === 0) return;

                let checkedContainer = checkboxContainers.find('.checked-checkboxes');
                let uncheckedContainer = checkboxContainers.find('.unchecked-checkboxes');

                // Move all checkboxes to the unchecked container initially
                column.find('.frappe-control[data-fieldtype="Check"]').each(function () {
                    let checkbox = $(this);
                    let isChecked = checkbox.find('input').is(':checked');

                    if (isChecked) {
                        checkedContainer.append(checkbox);
                        checkboxContainers.find('.checked-container').show();
                    } else {
                        uncheckedContainer.append(checkbox);
                    }
                });
            });
        }, 100);

        me.multiple_variant_dialog.set_primary_action(__('Create Variants'), () => {
            let selected_attributes = get_selected_attributes();
            let use_template_image = me.multiple_variant_dialog.get_value('use_template_image');

            // Kiểm tra xem tất cả các thuộc tính đã được chọn ít nhất một giá trị
            let incomplete = Object.keys(selected_attributes).some(attr => selected_attributes[attr].length === 0);
            if (incomplete) {
                frappe.msgprint(__('Please select at least one value for each attribute.'));
                return;
            }

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
                    selected_attributes[attribute_name].push($(opt).attr('data-fieldname') || $(opt).next('label').text().trim());
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
                            const increment = r.message.increment || 1;

                            let values = [];
                            for (let i = from; i <= to; i += increment) {
                                values.push(i.toString());
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
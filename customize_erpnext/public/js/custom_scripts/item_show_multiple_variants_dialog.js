// Ghi đè hàm show_multiple_variants_dialog trong erpnext.item
// Cải tiến: 
// - Thêm nút "Update Attribute Values" để refresh danh sách attributes
// - Cố định thứ tự attributes: Color, Size, Brand, Season, Info
// - Tổ chức checkboxes thành Selected/Available groups
// - Thêm search và bulk input cho mỗi attribute
if (!erpnext.item._original_show_multiple_variants_dialog) {
    erpnext.item._original_show_multiple_variants_dialog = erpnext.item.show_multiple_variants_dialog;
}

erpnext.item.show_multiple_variants_dialog = function (frm) {
    var me = this;

    let promises = [];
    let attr_val_fields = {};

    // Định nghĩa thứ tự cố định cho attributes
    // Có thể thay đổi thứ tự này theo nhu cầu của bạn
    const FIXED_ATTRIBUTE_ORDER = ['Color', 'Size', 'Brand', 'Season', 'Info'];

    function make_fields_from_attribute_values(attr_dict) {
        let fields = [];

        // Lấy tất cả attributes và sắp xếp theo thứ tự cố định
        let all_attributes = Object.keys(attr_dict);
        let sorted_attributes = [];

        // Thêm attributes theo thứ tự cố định trước
        FIXED_ATTRIBUTE_ORDER.forEach(attr => {
            if (all_attributes.includes(attr)) {
                sorted_attributes.push(attr);
            }
        });

        // Thêm các attributes còn lại (nếu có) không nằm trong FIXED_ATTRIBUTE_ORDER
        all_attributes.forEach(attr => {
            if (!sorted_attributes.includes(attr)) {
                sorted_attributes.push(attr);
            }
        });

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
                    let column = $(this.wrapper).closest('.form-column');
                    let checkboxes = column.find('.unchecked-checkboxes .checkbox');

                    let visibleCount = 0;
                    checkboxes.each(function () {
                        let label = $(this).find('label').text().toLowerCase();
                        if (label.includes(search_value)) {
                            $(this).show();
                            visibleCount++;
                        } else {
                            $(this).hide();
                        }
                    });

                    // Update available values count after search
                    let attributeName = column.find('.column-label').text().trim();
                    let checkboxContainers = column.find(`.checkbox-containers[data-attribute="${attributeName}"]`);
                    checkboxContainers.find('.available-values-count').text(`(${visibleCount})`);
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

                    // Update counts after setting values
                    updateValueCounts($(this.wrapper).closest('.form-column'));
                }
            });

            // Add HTML containers for checked and unchecked checkboxes
            fields.push({
                fieldtype: 'HTML',
                fieldname: `${name}_checkbox_containers`,
                options: `<div class="checkbox-containers" data-attribute="${name}">
                    <div class="checked-container mb-2" style="display:none;">
                        <div class="checked-header font-weight-bold text-success" style="padding: 5px 0; margin-bottom: 5px; border-bottom: 1px solid #ccc;">
                            ${__('Selected Values')} <span class="selected-values-count">(0)</span>
                        </div>
                        <div class="checked-checkboxes"></div>
                    </div>
                    <div class="unchecked-container">
                        <div class="unchecked-header font-weight-bold" style="padding: 5px 0; margin-bottom: 5px; border-bottom: 1px solid #ccc;">
                            ${__('Available Values')} <span class="available-values-count">(${attr_dict[name].length})</span>
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
                        let total_selected = 0;

                        Object.keys(selected_attributes).map(key => {
                            lengths.push(selected_attributes[key].length);
                            total_selected += selected_attributes[key].length;
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

    // Function to update the count of checked and unchecked values
    function updateValueCounts(column) {
        let attributeName = column.find('.column-label').text().trim();
        if (!attributeName) return;

        let checkboxContainers = column.find(`.checkbox-containers[data-attribute="${attributeName}"]`);
        if (checkboxContainers.length === 0) return;

        // Count the checkboxes
        let checkedCount = column.find('.checked-checkboxes .checkbox').length;
        let visibleUncheckedCount = column.find('.unchecked-checkboxes .checkbox:visible').length;

        // Update the count displays
        checkboxContainers.find('.selected-values-count').text(`(${checkedCount})`);
        checkboxContainers.find('.available-values-count').text(`(${visibleUncheckedCount})`);
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

        // Update counts after moving
        updateValueCounts(column);
    }

    // Hàm xử lý tạo variant theo batch để tránh timeout
    function create_variants_in_batches(selected_attributes, use_template_image) {
        const batch_size = 10; // Mặc định batch size là 10

        // Tạo danh sách các tổ hợp thuộc tính theo thứ tự cố định
        let ordered_attributes = {};
        let attribute_names = [];

        FIXED_ATTRIBUTE_ORDER.forEach(attr => {
            if (selected_attributes[attr]) {
                ordered_attributes[attr] = selected_attributes[attr];
                attribute_names.push(attr);
            }
        });

        // Thêm các attributes còn lại
        Object.keys(selected_attributes).forEach(attr => {
            if (!ordered_attributes[attr]) {
                ordered_attributes[attr] = selected_attributes[attr];
                attribute_names.push(attr);
            }
        });

        let attribute_values = attribute_names.map(name => ordered_attributes[name]);

        // Tổng số biến thể cần tạo
        let total_variants = attribute_values.reduce((a, b) => a * b.length, 1);
        let current_batch_index = 0;
        let variants_created = 0;
        let progress_dialog;

        // Tạo progress dialog để hiển thị tiến trình
        function show_progress_dialog() {
            progress_dialog = new frappe.ui.Dialog({
                title: __('Creating Variants'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'progress_area',
                        options: `
                            <div class="progress" style="height: 20px;">
                                <div class="progress-bar" role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">0%</div>
                            </div>
                            <p class="text-muted mt-2 mb-0">${__('Creating variants... Please do not close this dialog.')}</p>
                            <p class="text-muted mb-2"><span class="variants-created">0</span> ${__('of')} ${total_variants} ${__('variants created')}</p>
                        `
                    }
                ]
            });
            progress_dialog.show();

            // Vô hiệu hóa nút đóng để ngăn người dùng đóng dialog khi đang xử lý
            progress_dialog.$wrapper.find('.modal-header .btn-modal-close').addClass('d-none');
        }

        // Cập nhật tiến trình
        function update_progress(created_count) {
            let percent = Math.floor((created_count / total_variants) * 100);
            progress_dialog.$wrapper.find('.progress-bar').css('width', percent + '%').attr('aria-valuenow', percent).text(percent + '%');
            progress_dialog.$wrapper.find('.variants-created').text(created_count);
        }

        // Tạo các tổ hợp theo Cartesian product
        function get_combinations(arrays, current = [], index = 0, results = []) {
            if (index === arrays.length) {
                results.push([...current]);
                return;
            }

            for (let i = 0; i < arrays[index].length; i++) {
                current[index] = arrays[index][i];
                get_combinations(arrays, current, index + 1, results);
            }

            return results;
        }

        // Lấy tất cả các tổ hợp thuộc tính
        let all_combinations = get_combinations(attribute_values);

        // Chia thành các batch nhỏ hơn
        let batches = [];
        for (let i = 0; i < all_combinations.length; i += batch_size) {
            batches.push(all_combinations.slice(i, i + batch_size));
        }

        // Hàm xử lý từng batch
        function process_batch() {
            if (current_batch_index >= batches.length) {
                // Hoàn thành tất cả các batch
                setTimeout(() => {
                    progress_dialog.hide();
                    frappe.show_alert({
                        message: __("{0} variants created successfully.", [variants_created]),
                        indicator: 'green'
                    });
                }, 1000);
                return;
            }

            let current_batch = batches[current_batch_index];
            let batch_attributes = {};

            // Chuyển đổi định dạng cho batch hiện tại theo thứ tự cố định
            attribute_names.forEach((attr_name, attr_index) => {
                batch_attributes[attr_name] = [];
                current_batch.forEach(combination => {
                    if (!batch_attributes[attr_name].includes(combination[attr_index])) {
                        batch_attributes[attr_name].push(combination[attr_index]);
                    }
                });
            });

            // Gọi API để tạo biến thể cho batch hiện tại
            frappe.call({
                method: 'erpnext.controllers.item_variant.enqueue_multiple_variant_creation',
                args: {
                    item: frm.doc.name,
                    args: batch_attributes,
                    use_template_image: use_template_image
                },
                callback: function (r) {
                    let created_count = 0;
                    if (r.message === 'queued') {
                        // Nếu job được xếp hàng đợi, ước tính số biến thể được tạo
                        created_count = current_batch.length;
                    } else if (typeof r.message === 'number') {
                        created_count = r.message;
                    }

                    variants_created += created_count;
                    update_progress(variants_created);

                    // Xử lý batch tiếp theo
                    current_batch_index++;
                    setTimeout(process_batch, 1000); // Đợi 1 giây giữa các batch để tránh tải quá mức
                },
                error: function (err) {
                    frappe.msgprint({
                        title: __('Error Creating Variants'),
                        indicator: 'red',
                        message: __('An error occurred processing batch {0}. {1} variants were created before the error.',
                            [current_batch_index + 1, variants_created])
                    });

                    console.error("Variant creation error:", err);
                    progress_dialog.hide();
                }
            });
        }

        // Bắt đầu xử lý
        show_progress_dialog();
        process_batch();
    }

    // Hàm load attribute values
    function load_attribute_values(callback) {
        let promises = [];
        let new_attr_val_fields = {};

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
                                new_attr_val_fields[d.attribute] = r.message.map(function (d) { return d.attribute_value; });
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
                                new_attr_val_fields[d.attribute] = values;
                                resolve();
                            }
                        });
                    }
                });

                promises.push(p);
            }
        });

        Promise.all(promises).then(() => {
            // Sắp xếp lại theo thứ tự cố định
            let ordered_attr_val_fields = {};

            // Thêm attributes theo thứ tự cố định
            FIXED_ATTRIBUTE_ORDER.forEach(attr => {
                if (new_attr_val_fields[attr]) {
                    ordered_attr_val_fields[attr] = new_attr_val_fields[attr];
                }
            });

            // Thêm các attributes còn lại
            Object.keys(new_attr_val_fields).forEach(attr => {
                if (!ordered_attr_val_fields[attr]) {
                    ordered_attr_val_fields[attr] = new_attr_val_fields[attr];
                }
            });

            attr_val_fields = ordered_attr_val_fields;
            if (callback) callback();
        });
    }

    // Hàm refresh dialog
    function refresh_dialog_content() {
        // Lưu lại các giá trị đã chọn
        let selected_values = get_selected_attributes();
        let manual_values = {};
        let search_values = {};
        let use_template_image = me.multiple_variant_dialog.get_value('use_template_image');

        // Lưu lại giá trị trong các textarea và search input
        me.multiple_variant_dialog.$wrapper.find('.form-column').each(function () {
            let column = $(this);
            let attribute_name = column.find('.column-label').text().trim();
            if (attribute_name) {
                let manual_field = me.multiple_variant_dialog.get_field(`${attribute_name}_manual`);
                let search_field = me.multiple_variant_dialog.get_field(`${attribute_name}_search`);

                if (manual_field) {
                    manual_values[attribute_name] = manual_field.get_value();
                }
                if (search_field) {
                    search_values[attribute_name] = search_field.get_value();
                }
            }
        });

        // Hiển thị loading
        frappe.show_alert(__('Updating attribute values...'), 3);

        // Load lại attribute values
        load_attribute_values(() => {
            // Đóng dialog cũ
            me.multiple_variant_dialog.hide();

            // Tạo lại dialog mới
            let fields = make_fields_from_attribute_values(attr_val_fields);
            make_and_show_dialog(fields);

            // Khôi phục các giá trị sau khi dialog mới được tạo
            setTimeout(() => {
                // Restore use_template_image
                if (frm.doc.image && use_template_image) {
                    me.multiple_variant_dialog.set_value('use_template_image', use_template_image);
                }

                // Restore manual values và search values
                Object.keys(manual_values).forEach(attr => {
                    let field = me.multiple_variant_dialog.get_field(`${attr}_manual`);
                    if (field && manual_values[attr]) {
                        field.set_value(manual_values[attr]);
                    }
                });

                Object.keys(search_values).forEach(attr => {
                    let field = me.multiple_variant_dialog.get_field(`${attr}_search`);
                    if (field && search_values[attr]) {
                        field.set_value(search_values[attr]);
                        field.$input.trigger('change');
                    }
                });

                // Restore selected values
                Object.keys(selected_values).forEach(attr => {
                    selected_values[attr].forEach(value => {
                        let checkbox = me.multiple_variant_dialog.get_field(value);
                        if (checkbox) {
                            checkbox.set_value(1);
                        }
                    });
                });

                frappe.show_alert({
                    message: __('Attribute values updated successfully'),
                    indicator: 'green'
                });
            }, 200);
        });
    }

    function make_and_show_dialog(fields) {
        me.multiple_variant_dialog = new frappe.ui.Dialog({
            title: __('Select Attribute Values. Least one value from each of the attributes.'),
            fields: [
                frm.doc.image ? {
                    fieldtype: 'Check',
                    label: __('Create a variant with the template image.'),
                    fieldname: 'use_template_image',
                    default: 0
                } : null,
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
            'height': '100px',
            'min-height': '100px',
            'max-height': '100px',
            'overflow-y': 'auto'
        });

        // Thêm nút Update Attribute Values vào footer
        setTimeout(() => {
            let footer = me.multiple_variant_dialog.$wrapper.find('.modal-footer');
            let update_btn = $(`<button class="btn btn-default btn-sm btn-update-attributes">
                ${__('Update Attribute Values')}
            </button>`);

            update_btn.css({
                'margin-right': '5px'
            });

            update_btn.on('click', () => {
                refresh_dialog_content();
            });

            // Thêm button vào trước nút primary
            footer.prepend(update_btn);
        }, 100);

        // Khởi tạo các thống kê lựa chọn khi dialog được mở
        setTimeout(function () {
            // Update selection stats khi dialog mở
            let selected_attributes = get_selected_attributes();
            let lengths = [];

            Object.keys(selected_attributes).map(key => {
                lengths.push(selected_attributes[key].length);
            });

            if (!lengths.includes(0)) {
                let no_of_combinations = lengths.reduce((a, b) => a * b, 1);
            }

            // Sắp xếp lại các checkbox
            me.multiple_variant_dialog.$wrapper.find('.form-column').each(function () {
                let column = $(this);
                let attributeName = column.find('.column-label').text().trim();
                if (!attributeName) return;

                let checkboxContainers = column.find(`.checkbox-containers[data-attribute="${attributeName}"]`);
                if (checkboxContainers.length === 0) return;

                let checkedContainer = checkboxContainers.find('.checked-checkboxes');
                let uncheckedContainer = checkboxContainers.find('.unchecked-checkboxes');

                // Count the checkboxes
                let checkedCount = 0;

                // Move all checkboxes to the unchecked container initially
                column.find('.frappe-control[data-fieldtype="Check"]').each(function () {
                    let checkbox = $(this);
                    let isChecked = checkbox.find('input').is(':checked');

                    if (isChecked) {
                        checkedContainer.append(checkbox);
                        checkboxContainers.find('.checked-container').show();
                        checkedCount++;
                    } else {
                        uncheckedContainer.append(checkbox);
                    }
                });

                // Update counts after organizing
                updateValueCounts(column);
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

            // Tính toán tổng số biến thể sẽ được tạo
            let total_variants = Object.values(selected_attributes).reduce((total, values) => total * values.length, 1);

            // Hiển thị thông báo xác nhận nếu số lượng biến thể lớn
            if (total_variants > 50) {
                frappe.confirm(
                    __('You are about to create {0} variants. This may take some time. Do you want to continue?', [total_variants]),
                    () => {
                        me.multiple_variant_dialog.hide();
                        create_variants_in_batches(selected_attributes, use_template_image);
                    }
                );
            } else {
                me.multiple_variant_dialog.hide();
                create_variants_in_batches(selected_attributes, use_template_image);
            }
        });

        $($(me.multiple_variant_dialog.$wrapper.find('.form-column')).find('.frappe-control')).css('margin-bottom', '0px');

        me.multiple_variant_dialog.disable_primary_action();
        me.multiple_variant_dialog.clear();
        me.multiple_variant_dialog.show();
    }

    function get_selected_attributes() {
        let selected_attributes = {};

        // Thu thập tất cả attributes
        let temp_attributes = {};
        me.multiple_variant_dialog.$wrapper.find('.form-column').each((i, col) => {
            let column_label = $(col).find('.column-label');
            if (column_label.length === 0) return;

            let attribute_name = column_label.html().trim();
            if (!attribute_name) return;

            temp_attributes[attribute_name] = [];
            let checked_opts = $(col).find('.checkbox input');
            checked_opts.each((i, opt) => {
                if ($(opt).is(':checked')) {
                    temp_attributes[attribute_name].push($(opt).attr('data-fieldname') || $(opt).next('label').text().trim());
                }
            });
        });

        // Sắp xếp lại theo thứ tự cố định
        FIXED_ATTRIBUTE_ORDER.forEach(attr => {
            if (temp_attributes[attr]) {
                selected_attributes[attr] = temp_attributes[attr];
            }
        });

        // Thêm các attributes còn lại không nằm trong FIXED_ATTRIBUTE_ORDER
        Object.keys(temp_attributes).forEach(attr => {
            if (!selected_attributes[attr]) {
                selected_attributes[attr] = temp_attributes[attr];
            }
        });

        return selected_attributes;
    }

    // Load attribute values lần đầu
    load_attribute_values(() => {
        let fields = make_fields_from_attribute_values(attr_val_fields);
        make_and_show_dialog(fields);
    });
};
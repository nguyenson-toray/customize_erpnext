// Ghi đè hàm show_multiple_variants_dialog trong erpnext.item
// Cải tiến: 
// - Thêm nút "Update Attribute Values" để refresh danh sách attributes
// - Cố định thứ tự attributes: Color, Size, Brand, Season, Info
// - Tổ chức checkboxes thành Selected/Available groups
// - Thêm search và bulk input cho mỗi attribute
// - Chỉ thực hiện bulk input khi nhấn Enter thay vì tìm kiếm liên tục
// - Import trực tiếp attribute values khi không tìm thấy
// - Luôn so sánh lowercase và chuyển đổi sang camelCase khi lưu
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

    // Cấu hình format theo attribute - có thể tùy chỉnh : keep, proper
    const ATTRIBUTE_FORMAT_CONFIG = {
        'Color': 'proper',        // Blue1, Red Color
        'Size': 'proper',          // giữ nguyên: S, M, L, XL
        'Brand': 'proper',       // Nike, Adidas Brand
        'Season': 'proper',      // Summer, Winter Sale
        'Info': 'proper',        // New Arrival, Hot Item
        'default': 'proper'      // mặc định cho attributes khác
    };

    // Hàm chuyển đổi sang PROPER case (như Excel) - in hoa chữ cái đầu mỗi từ, giữ khoảng trắng
    function toProperCase(str) {
        if (!str) return str;

        return str.trim()
            .toLowerCase()
            .replace(/\b\w/g, function (char) {
                return char.toUpperCase();
            });
    }

    // Hàm alternative cho camelCase thật (nối từ, không có space)
    function toCamelCaseNoSpace(str) {
        if (!str) return str;

        str = str.trim().toLowerCase();

        // Tách bằng nhiều delimiter: space, dash, underscore
        let words = str.split(/[\s\-_]+/).filter(word => word);

        return words
            .map((word, index) => {
                if (index === 0) {
                    // Word đầu tiên giữ nguyên lowercase
                    return word;
                } else {
                    // Các word tiếp theo capitalize chữ cái đầu
                    return word.charAt(0).toUpperCase() + word.slice(1);
                }
            })
            .join('');
    }

    // Hàm alternative để convert properly với số (PascalCase without space)
    function toPascalCaseNoSpace(str) {
        if (!str) return str;

        str = str.trim().toLowerCase();

        // Tách bằng space, dash, underscore
        let words = str.split(/[\s\-_]+/).filter(word => word);

        return words
            .map(word => {
                if (!word) return '';
                return word.charAt(0).toUpperCase() + word.slice(1);
            })
            .join('');
    }

    // Hàm chuẩn hóa giá trị để so sánh
    function normalizeForComparison(value) {
        return value.toLowerCase().trim();
    }

    // Hàm format giá trị cho display và storage - enhanced với proper case
    function formatValueForStorage(value, attributeName = null) {
        if (!value) return value;

        // Trim trước
        const trimmed = value.trim();

        // Lấy format config cho attribute này
        const formatType = attributeName ?
            (ATTRIBUTE_FORMAT_CONFIG[attributeName] || ATTRIBUTE_FORMAT_CONFIG['default']) :
            ATTRIBUTE_FORMAT_CONFIG['default'];

        switch (formatType) {
            case 'keep':
                // Giữ nguyên case, chỉ trim
                return trimmed;

            case 'camelCaseNoSpace':
                // camelCase không có space: newArrival, hotItem
                return toCamelCaseNoSpace(trimmed);

            case 'pascalCaseNoSpace':
                // PascalCase không có space: NewArrival, HotItem
                return toPascalCaseNoSpace(trimmed);

            case 'proper':
            default:
                // PROPER case như Excel: New Arrival, Hot Item, Blue1
                return toProperCase(trimmed);
        }
    }

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
                fieldname: `${name}_search`,
                onchange: function () {
                    let search_value = normalizeForComparison(this.get_value());
                    let column = $(this.wrapper).closest('.form-column');
                    let checkboxes = column.find('.unchecked-checkboxes .checkbox');

                    let visibleCount = 0;
                    checkboxes.each(function () {
                        let label = normalizeForComparison($(this).find('label').text());
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
                fieldtype: 'Small Text',
                fieldname: `${name}_manual`,
                onchange: function () {
                    // Không làm gì trong onchange
                }
            });

            // Add status display area
            fields.push({
                fieldtype: 'HTML',
                fieldname: `${name}_status`,
                options: `<div class="value-status-area" data-attribute="${name}" style="margin-bottom: 10px; display: none;">
                    <div class="status-content" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px; background: #f9f9f9;">
                        <div class="status-info" style="font-size: 12px; margin-bottom: 5px;"></div>
                        <div class="missing-values" style="margin-bottom: 8px;"></div>
                        <button class="btn btn-primary btn-xs import-missing-btn" style="display: none;">
                            ${__('Import Missing Values')}
                        </button>
                    </div>
                </div>`
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

    // === Merge functions from item_attribute_import.js ===

    // Enhanced import function với camelCase conversion
    function importMissingValues(attributeName, missingValues, selectedValues, callback) {
        if (!missingValues || missingValues.length === 0) {
            if (callback) callback();
            return;
        }

        // Convert missing values to configured format for storage
        const formattedMissingValues = missingValues.map(value => formatValueForStorage(value, attributeName));

        // Show progress
        frappe.show_alert(__('Adding {0} values to {1}...', [formattedMissingValues.length, attributeName]), 5);

        // Get attribute document and add values
        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Item Attribute',
                name: attributeName
            },
            callback: function (r) {
                if (r.message) {
                    let attr_doc = r.message;
                    let existingValues = attr_doc.item_attribute_values || [];
                    let lastAbbr = getLastAbbreviation(attributeName, existingValues);

                    // Check for duplicates using normalized comparison
                    let existingNormalized = existingValues.map(item =>
                        normalizeForComparison(item.attribute_value)
                    );

                    let valuesToAdd = [];
                    formattedMissingValues.forEach(value => {
                        let normalizedValue = normalizeForComparison(value);
                        if (!existingNormalized.includes(normalizedValue)) {
                            valuesToAdd.push(value);
                        }
                    });

                    if (valuesToAdd.length === 0) {
                        frappe.show_alert({
                            message: __('All values already exist in {0}', [attributeName]),
                            indicator: 'blue'
                        });

                        // Still refresh to update UI
                        setTimeout(() => {
                            refresh_dialog_content_with_selection(selectedValues);
                        }, 500);
                        return;
                    }

                    // Add new values to the document
                    valuesToAdd.forEach(value => {
                        lastAbbr = get_next_code(lastAbbr);

                        // Add to item_attribute_values array
                        if (!attr_doc.item_attribute_values) {
                            attr_doc.item_attribute_values = [];
                        }

                        attr_doc.item_attribute_values.push({
                            attribute_value: value, // Already in camelCase format
                            abbr: lastAbbr
                        });
                    });

                    // Save the document
                    frappe.call({
                        method: 'frappe.client.save',
                        args: {
                            doc: attr_doc
                        },
                        callback: function (save_r) {
                            if (save_r.message) {
                                frappe.show_alert({
                                    message: __('Successfully added {0} values to {1}', [valuesToAdd.length, attributeName]),
                                    indicator: 'green'
                                });

                                // Update selected values with new camelCase values
                                let updatedSelectedValues = { ...selectedValues };
                                if (!updatedSelectedValues[attributeName]) {
                                    updatedSelectedValues[attributeName] = [];
                                }

                                // Add the new camelCase values to selected
                                valuesToAdd.forEach(camelValue => {
                                    if (!updatedSelectedValues[attributeName].includes(camelValue)) {
                                        updatedSelectedValues[attributeName].push(camelValue);
                                    }
                                });

                                // Refresh dialog với selected values để restore
                                setTimeout(() => {
                                    refresh_dialog_content_with_selection(updatedSelectedValues);
                                }, 500);

                                if (callback) callback();
                            } else {
                                frappe.msgprint({
                                    title: __('Error'),
                                    indicator: 'red',
                                    message: __('Failed to save {0} values. Please try again.', [attributeName])
                                });
                            }
                        },
                        error: function (err) {
                            console.error('Save error:', err);
                            frappe.msgprint({
                                title: __('Error'),
                                indicator: 'red',
                                message: __('Error saving attribute values: {0}', [err.message || 'Unknown error'])
                            });
                        }
                    });
                } else {
                    frappe.msgprint({
                        title: __('Error'),
                        indicator: 'red',
                        message: __('Could not load {0} attribute document', [attributeName])
                    });
                }
            },
            error: function (err) {
                console.error('Get attribute error:', err);
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: __('Error loading attribute: {0}', [err.message || 'Unknown error'])
                });
            }
        });
    }

    // Lấy mã viết tắt cuối cùng dựa trên loại thuộc tính
    function getLastAbbreviation(attributeName, existingValues = []) {
        if (existingValues.length > 0) {
            return existingValues[existingValues.length - 1].abbr;
        }

        // Mã mặc định dựa trên loại thuộc tính
        if (attributeName === "Color" || attributeName === "Size" || attributeName === "Info") {
            return "000"; // 3-character code
        } else if (attributeName === "Brand" || attributeName === "Season") {
            return "00";  // 2-character code
        } else {
            return "000"; // Default 3-character code
        }
    }

    // Hàm tạo mã code tiếp theo
    function get_next_code(max_code) {
        try {
            // Xác định độ dài mã
            const codeLength = max_code ? max_code.length : 3;

            // Nếu max_code rỗng hoặc không hợp lệ, trả về mã mặc định
            if (!max_code || (codeLength !== 2 && codeLength !== 3)) {
                return codeLength === 2 ? '00' : '000';
            }

            // Định nghĩa ký tự hợp lệ (0-9 và A-Z)
            const validChars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';

            // Chuyển đổi mã hiện tại thành mảng ký tự
            const codeChars = max_code.split('');

            // Bắt đầu từ ký tự ngoài cùng bên phải
            let position = codeLength - 1;
            let carry = true;

            // Xử lý từng ký tự từ phải sang trái
            while (position >= 0 && carry) {
                // Lấy ký tự hiện tại tại vị trí này
                const currentChar = codeChars[position];

                // Tìm index của nó trong chuỗi validChars
                const currentIndex = validChars.indexOf(currentChar);

                if (currentIndex === validChars.length - 1) {
                    // Nếu là ký tự cuối cùng (Z), reset về đầu tiên (0) và nhớ
                    codeChars[position] = '0';
                    carry = true;
                } else {
                    // Ngược lại, tăng lên ký tự tiếp theo và dừng nhớ
                    codeChars[position] = validChars[currentIndex + 1];
                    carry = false;
                }

                // Di chuyển đến vị trí bên trái tiếp theo
                position--;
            }

            // Nếu vẫn còn nhớ sau khi xử lý tất cả các vị trí,
            // chúng ta đã vượt quá mã tối đa có thể (ZZ hoặc ZZZ)
            if (carry) {
                console.warn('Warning: Code sequence overflow, returning to ' + '0'.repeat(codeLength));
                return '0'.repeat(codeLength);
            }

            // Nối các ký tự lại thành một chuỗi
            return codeChars.join('');
        } catch (error) {
            console.error('Error generating next code:', error);
            // Fallback là mã mặc định trong trường hợp lỗi
            return max_code && max_code.length === 2 ? '00' : '000';
        }
    }

    // === End merge from item_attribute_import.js ===

    // Hàm refresh dialog với selected values
    function refresh_dialog_content_with_selection(selectedValues) {
        // Lưu lại các giá trị khác
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

                // Restore và apply selected values (bao gồm cả values mới import)
                Object.keys(selectedValues).forEach(attr => {
                    selectedValues[attr].forEach(value => {
                        let checkbox = me.multiple_variant_dialog.get_field(value);
                        if (checkbox) {
                            checkbox.set_value(1);
                        }
                    });
                });

                frappe.show_alert({
                    message: __('Attribute values updated and selections restored'),
                    indicator: 'green'
                });
            }, 200);
        });
    }

    // Enhanced bulk input handler với improved comparison và camelCase conversion
    function handleBulkInput(manual_field, attribute_name) {
        let manual_values = manual_field.get_value().split('\n').map(v => v.trim()).filter(v => v);

        if (manual_values.length === 0) {
            // Hide status area if no input
            let column = $(manual_field.wrapper).closest('.form-column');
            column.find('.value-status-area').hide();
            return;
        }

        let available_values = [];
        let available_values_normalized = [];
        let checkboxes = $(manual_field.wrapper).closest('.form-column').find('.checkbox');

        checkboxes.each(function () {
            let value = $(this).find('label').text().trim();
            available_values.push(value);
            available_values_normalized.push(normalizeForComparison(value));
        });

        // Categorize values into existing and missing với improved comparison
        let existing_values = [];
        let missing_values = [];

        manual_values.forEach(inputValue => {
            let normalizedInput = normalizeForComparison(inputValue);
            let matchFound = false;

            // Tìm exact match trong available values
            for (let i = 0; i < available_values_normalized.length; i++) {
                if (available_values_normalized[i] === normalizedInput) {
                    existing_values.push(available_values[i]); // Use the exact value from available
                    matchFound = true;
                    break;
                }
            }

            if (!matchFound) {
                // Convert to configured format for consistency before adding to missing
                missing_values.push(formatValueForStorage(inputValue, attribute_name));
            }
        });

        // Apply existing values to checkboxes với normalized comparison
        let existing_values_normalized = new Set(existing_values.map(v => normalizeForComparison(v)));
        let appliedCount = 0;

        checkboxes.each(function () {
            let label = $(this).find('label').text().trim();
            let label_normalized = normalizeForComparison(label);
            let checkbox_input = $(this).find('input');

            if (existing_values_normalized.has(label_normalized)) {
                if (!checkbox_input.is(':checked')) {
                    checkbox_input.prop('checked', true).trigger('change');
                    appliedCount++;
                }
            } else {
                if (checkbox_input.is(':checked')) {
                    checkbox_input.prop('checked', false).trigger('change');
                }
            }
        });

        // Update counts after setting values
        updateValueCounts($(manual_field.wrapper).closest('.form-column'));

        // Show status and import button if needed
        showValueStatus(manual_field, attribute_name, existing_values, missing_values);

        // Show success message for applied values
        if (appliedCount > 0) {
            frappe.show_alert({
                message: __('Applied {0} existing values for {1}', [appliedCount, attribute_name]),
                indicator: 'green'
            });
        }
    }

    // Enhanced status display with camelCase preview
    function showValueStatus(manual_field, attribute_name, existing_values, missing_values) {
        let column = $(manual_field.wrapper).closest('.form-column');
        let statusArea = column.find('.value-status-area');
        let statusInfo = statusArea.find('.status-info');
        let missingDiv = statusArea.find('.missing-values');
        let importBtn = statusArea.find('.import-missing-btn');

        if (existing_values.length === 0 && missing_values.length === 0) {
            statusArea.hide();
            return;
        }

        statusArea.show();

        // Create status display
        let statusHtml = '';
        if (existing_values.length > 0) {
            statusHtml += `<span style="color: green; font-weight: bold;">✓ ${existing_values.length} existing:</span> `;
            statusHtml += existing_values.map(v => `<span style="color: green;">${v}</span>`).join(', ');
        }

        if (missing_values.length > 0) {
            if (existing_values.length > 0) statusHtml += '<br>';

            // Get format type for this attribute
            const formatType = ATTRIBUTE_FORMAT_CONFIG[attribute_name] || ATTRIBUTE_FORMAT_CONFIG['default'];
            let formatDescription;
            switch (formatType) {
                case 'keep': formatDescription = 'as-is'; break;
                case 'camelCaseNoSpace': formatDescription = 'camelCase'; break;
                case 'pascalCaseNoSpace': formatDescription = 'PascalCase'; break;
                case 'proper':
                default: formatDescription = 'Proper Case'; break;
            }

            statusHtml += `<span style="color: red; font-weight: bold;">✗ ${missing_values.length} missing (will be saved as ${formatDescription}):</span> `;
            statusHtml += missing_values.map(v => `<span style="color: red;">${v}</span>`).join(', ');
        }

        statusInfo.html(statusHtml);

        // Show/hide import button
        if (missing_values.length > 0) {
            importBtn.show();
            importBtn.off('click').on('click', function () {
                // Get current selected values to restore after import
                let currentSelected = get_selected_attributes();
                // Add missing values (already in camelCase) to current selected for this attribute
                if (!currentSelected[attribute_name]) {
                    currentSelected[attribute_name] = [];
                }
                missing_values.forEach(val => {
                    if (!currentSelected[attribute_name].includes(val)) {
                        currentSelected[attribute_name].push(val);
                    }
                });

                importMissingValues(attribute_name, missing_values, currentSelected);
            });
        } else {
            importBtn.hide();
        }
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

        // Thêm event listener cho phím Enter và tooltip
        setTimeout(() => {
            me.multiple_variant_dialog.$wrapper.find('textarea').each(function () {
                let textarea = $(this);
                let fieldname = textarea.attr('data-fieldname');

                // Tìm attribute name từ fieldname
                let attribute_name = '';
                if (fieldname && fieldname.endsWith('_manual')) {
                    attribute_name = fieldname.replace('_manual', '');
                }

                if (attribute_name) {
                    textarea.on('keydown', function (e) {
                        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                            // Ctrl+Enter hoặc Cmd+Enter để apply
                            e.preventDefault();
                            let manual_field = me.multiple_variant_dialog.get_field(fieldname);
                            if (manual_field) {
                                handleBulkInput(manual_field, attribute_name);
                            }
                        }
                    });

                    // Enhanced tooltip với format info
                    const formatType = ATTRIBUTE_FORMAT_CONFIG[attribute_name] || ATTRIBUTE_FORMAT_CONFIG['default'];
                    let formatDescription;
                    switch (formatType) {
                        case 'keep': formatDescription = 'as-is'; break;
                        case 'camelCaseNoSpace': formatDescription = 'camelCase'; break;
                        case 'pascalCaseNoSpace': formatDescription = 'PascalCase'; break;
                        case 'proper':
                        default: formatDescription = 'Proper Case'; break;
                    }

                    textarea.attr('title', `Search & Bulk Input for ${attribute_name}\nPress Ctrl+Enter to apply\nGreen = existing, Red = missing (will be converted to ${formatDescription})`);
                    textarea.attr('placeholder', `${attribute_name} values (one per line)\nCtrl+Enter to apply\nMissing values → ${formatDescription}`);
                }
            });

            // Thêm tooltip cho search inputs
            me.multiple_variant_dialog.$wrapper.find('input[data-fieldname$="_search"]').each(function () {
                let input = $(this);
                let fieldname = input.attr('data-fieldname');
                let attribute_name = fieldname.replace('_search', '');
                input.attr('title', `Search ${attribute_name} values (case-insensitive)`);
                input.attr('placeholder', `Search ${attribute_name}...`);
            });
        }, 200);

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
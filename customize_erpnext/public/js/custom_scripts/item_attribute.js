/**
 * Hàm tạo mã code tiếp theo từ mã hiện tại
 * Hỗ trợ cả mã 2 ký tự và 3 ký tự
 * @param {String} max_code - Mã code hiện tại
 * @returns {String} Mã code tiếp theo
 */
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

/**
 * Converts a string to Proper Case (like Excel PROPER function)
 * Capitalizes first letter of each word, preserves spaces
 * Special handling: first non-number character is uppercase (e.g., "26ss" → "26Ss")
 * @param {String} str - The string to convert
 * @returns {String} The proper case string
 */
function toProperCase(str) {
    if (!str) return str;

    let result = str.trim().toLowerCase();
    
    // First, handle regular word boundaries (spaces, punctuation)
    result = result.replace(/\b\w/g, function (char) {
        return char.toUpperCase();
    });
    
    // Special handling: ensure first non-number character is uppercase
    // This handles cases like "26ss" → "26Ss"
    result = result.replace(/^(\d*)([a-z])/, function(_, numbers, firstLetter) {
        return numbers + firstLetter.toUpperCase();
    });
    
    return result;
}

/**
 * Legacy function name for backward compatibility
 * Now redirects to toProperCase for consistent formatting
 * @param {String} str - The string to convert
 * @returns {String} The proper case string
 */
function toCamelCase(str) {
    return toProperCase(str);
}

/**
 * Validates a new Item Attribute to ensure there are no duplicate Attribute Values or Abbreviations
 * @param {Object} newAttribute - The new attribute object being created
 * @param {Array} existingAttributes - Array of existing attributes to check against
 * @returns {Object} Validation result with status and message
 */
function validateItemAttribute(newAttribute, existingAttributes) {
    // Initialize validation result
    const validationResult = {
        isValid: true,
        message: "Attribute is valid"
    };

    // Early return if no existing attributes to compare against
    if (!existingAttributes || existingAttributes.length === 0) {
        return validationResult;
    }

    // Check for duplicate attribute values
    const duplicateValues = [];
    const duplicateAbbreviations = [];

    // Extract attribute values from new attribute
    const newValues = newAttribute.item_attribute_values || [];

    // Iterate through existing attributes
    existingAttributes.forEach(existingAttr => {
        // Skip comparison with self (for updates)
        if (existingAttr.name === newAttribute.name) {
            return;
        }

        // Get existing attribute values
        const existingValues = existingAttr.item_attribute_values || [];

        // Compare each new value with existing values
        newValues.forEach(newValue => {
            existingValues.forEach(existingValue => {
                // Check for duplicate attribute value (case insensitive)
                if (newValue.attribute_value && existingValue.attribute_value &&
                    newValue.attribute_value.toLowerCase() === existingValue.attribute_value.toLowerCase()) {
                    duplicateValues.push({
                        value: newValue.attribute_value,
                        existingIn: existingAttr.attribute_name
                    });
                }

                // Check for duplicate abbreviation (case insensitive)
                if (newValue.abbr && existingValue.abbr &&
                    newValue.abbr.toLowerCase() === existingValue.abbr.toLowerCase()) {
                    duplicateAbbreviations.push({
                        abbr: newValue.abbr,
                        existingIn: existingAttr.attribute_name
                    });
                }
            });
        });
    });

    // Check for internal duplicates (within the new attribute values)
    const valueSet = new Set();
    const abbrSet = new Set();

    newValues.forEach(value => {
        // Check for duplicate attribute values within the same attribute (case insensitive)
        if (value.attribute_value) {
            const lowercaseValue = value.attribute_value.toLowerCase();
            if (valueSet.has(lowercaseValue)) {
                duplicateValues.push({
                    value: value.attribute_value,
                    existingIn: "current attribute"
                });
            } else {
                valueSet.add(lowercaseValue);
            }
        }

        // Check for duplicate abbreviations within the same attribute (case insensitive)
        if (value.abbr) {
            const lowercaseAbbr = value.abbr.toLowerCase();
            if (abbrSet.has(lowercaseAbbr)) {
                duplicateAbbreviations.push({
                    abbr: value.abbr,
                    existingIn: "current attribute"
                });
            } else {
                abbrSet.add(lowercaseAbbr);
            }
        }
    });

    // Prepare validation message if duplicates found
    if (duplicateValues.length > 0 || duplicateAbbreviations.length > 0) {
        validationResult.isValid = false;
        let errorMessage = "Cannot create Item Attribute due to the following issues:";

        if (duplicateValues.length > 0) {
            errorMessage += "\n\nDuplicate Attribute Values:";
            duplicateValues.forEach(dup => {
                errorMessage += `\n- "${dup.value}" already exists in "${dup.existingIn}"`;
            });
        }

        if (duplicateAbbreviations.length > 0) {
            errorMessage += "\n\nDuplicate Abbreviations:";
            duplicateAbbreviations.forEach(dup => {
                errorMessage += `\n- "${dup.abbr}" already exists in "${dup.existingIn}"`;
            });
        }

        validationResult.message = errorMessage;
    }

    return validationResult;
}

/**
 * Implementation integrated with your existing code
 */
frappe.ui.form.on('Item Attribute', {
    refresh: function (frm) {
        console.log('Form refreshed - ');
        console.log('Is numeric:', frm.doc.numeric_values);

        // Add a note about Proper Case formatting
        if (!frm.doc.numeric_values) {
            frm.add_custom_button(__('Format Note'), function () {
                frappe.msgprint({
                    title: __('Attribute Value Formatting'),
                    message: __('All attribute values will be automatically converted to Proper Case (like Excel PROPER function) before saving.<br><br>Examples:<br>• "red color" → "Red Color"<br>• "blue1" → "Blue1"<br>• "DARK-BLUE" → "Dark-Blue"'),
                    indicator: 'blue'
                });
            });
        }
    },

    before_save: function (frm) {
        // Convert all attribute values to Proper Case before saving
        const values = frm.doc.item_attribute_values || [];
        let hasChanges = false;

        values.forEach(value => {
            if (value.attribute_value) {
                const originalValue = value.attribute_value;
                const properCaseValue = toProperCase(value.attribute_value);

                if (originalValue !== properCaseValue) {
                    value.attribute_value = properCaseValue;
                    hasChanges = true;
                }
            }
        });

        // Show message if values were converted
        if (hasChanges) {
            frappe.show_alert({
                message: __('Attribute values converted to Proper Case format'),
                indicator: 'blue'
            }, 3);
        }

        // Validate abbreviation format based on attribute type
        validateAttributeFormat(frm);

        // Fetch all existing attributes from the system for duplicate validation
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Item Attribute",
                fields: ["name", "attribute_name", "item_attribute_values"],
            },
            callback: function (response) {
                if (response.message) {
                    const existingAttributes = response.message;

                    // Prepare the new attribute data from the form
                    const newAttribute = {
                        name: frm.doc.name,
                        attribute_name: frm.doc.attribute_name,
                        item_attribute_values: frm.doc.item_attribute_values
                    };

                    // Validate the new attribute
                    const validation = validateItemAttribute(newAttribute, existingAttributes);

                    // If validation fails, show warning and prevent save
                    if (!validation.isValid) {
                        frappe.validated = false;
                        frappe.throw(validation.message);
                    }
                }
            }
        });
    }
});

/**
 * Validates abbreviation format based on attribute type
 */
function validateAttributeFormat(frm) {
    const attributeName = frm.doc.attribute_name;
    const values = frm.doc.item_attribute_values || [];
    let formatError = false;
    let errorMessage = "Abbreviation format invalid:";

    values.forEach(row => {
        let isValidFormat = true;
        let requiredFormat = "";

        // Check format based on attribute name
        if (attributeName === "Color" || attributeName === "Size" || attributeName === "Info") {
            // Mã 3 ký tự phải chứa số và chữ
            requiredFormat = "3 ký tự (số và chữ in hoa)";
            isValidFormat = /^[0-9A-Z]{3}$/.test(row.abbr);
        } else if (attributeName === "Brand" || attributeName === "Season") {
            // Mã 2 ký tự phải chứa số và chữ
            requiredFormat = "2 ký tự (số và chữ in hoa)";
            isValidFormat = /^[0-9A-Z]{2}$/.test(row.abbr);
        }

        // Add to error message if format is invalid
        if (!isValidFormat) {
            formatError = true;
            errorMessage += `\n- "${row.attribute_value}" có mã viết tắt "${row.abbr}" không đúng định dạng. Cần ${requiredFormat}.`;
        }
    });

    // Throw error if any format is invalid
    if (formatError) {
        frappe.validated = false;
        frappe.throw(errorMessage);
    }
}

// Handle row addition in child table
frappe.ui.form.on('Item Attribute Value', {
    item_attribute_values_add: function (frm, cdt, cdn) {
        console.log('New row added');

        if (!frm.doc.numeric_values) {
            let row = locals[cdt][cdn];
            let values = frm.doc.item_attribute_values || [];
            console.log('Current values:', values);

            // Lấy giá trị abbreviation của hàng cuối cùng (không bao gồm hàng hiện tại)
            let lastRow = values.filter(r => r.name !== row.name).pop();
            console.log('Last row:', lastRow);

            let lastAbbr = lastRow ? lastRow.abbr : null;
            console.log('Last abbr:', lastAbbr);

            // Tạo mã viết tắt mới dựa trên loại thuộc tính
            let newAbbr = "";
            const attributeName = frm.doc.attribute_name;

            if (attributeName === "Color" || attributeName === "Size" || attributeName === "Info") {
                // Mã 3 ký tự cho Color, Size và Info
                if (!lastAbbr || lastAbbr.length !== 3) {
                    newAbbr = "000";
                } else {
                    newAbbr = get_next_code(lastAbbr);
                }
            } else if (attributeName === "Brand" || attributeName === "Season") {
                // Mã 2 ký tự cho Brand và Season
                if (!lastAbbr || lastAbbr.length !== 2) {
                    newAbbr = "00";
                } else {
                    newAbbr = get_next_code(lastAbbr);
                }
            } else {
                // Mặc định 3 ký tự cho các attribute khác
                if (!lastAbbr || lastAbbr.length !== 3) {
                    newAbbr = "000";
                } else {
                    newAbbr = get_next_code(lastAbbr);
                }
            }

            console.log('New abbr:', newAbbr);

            // Đặt mã viết tắt mới
            frappe.model.set_value(cdt, cdn, 'abbr', newAbbr);
            frm.refresh_field('item_attribute_values');

            console.log('Abbreviation updated');
        }
    },

    // Add validation when attribute value or abbreviation is changed
    attribute_value: function (frm, cdt, cdn) {
        // Convert to Proper Case when attribute value changes
        let row = locals[cdt][cdn];
        if (row.attribute_value) {
            const originalValue = row.attribute_value;
            const properCaseValue = toProperCase(row.attribute_value);

            if (properCaseValue !== originalValue) {
                frappe.model.set_value(cdt, cdn, 'attribute_value', properCaseValue);

                // Show conversion notification
                frappe.show_alert({
                    message: __('Converted "{0}" to Proper Case: "{1}"', [originalValue, properCaseValue]),
                    indicator: 'blue'
                }, 3);
            }
        }
        validateAttributeRow(frm, cdt, cdn);
    },

    abbr: function (frm, cdt, cdn) {
        // Validate abbreviation format when it changes
        validateAbbrFormat(frm, cdt, cdn);
        validateAttributeRow(frm, cdt, cdn);
    }
});

/**
 * Validates abbreviation format for a specific row
 */
function validateAbbrFormat(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const attributeName = frm.doc.attribute_name;

    if (!row.abbr) return;

    let isValidFormat = true;
    let requiredFormat = "";

    // Check format based on attribute name
    if (attributeName === "Color" || attributeName === "Size") {
        // Mã 3 ký tự phải chứa số và chữ in hoa
        requiredFormat = "3 ký tự (số và chữ in hoa)";
        isValidFormat = /^[0-9A-Z]{3}$/.test(row.abbr);
    } else if (attributeName === "Brand" || attributeName === "Season") {
        // Mã 2 ký tự phải chứa số và chữ in hoa
        requiredFormat = "2 ký tự (số và chữ in hoa)";
        isValidFormat = /^[0-9A-Z]{2}$/.test(row.abbr);
    } else if (attributeName === "Info") {
        // Mã 3 ký tự phải chứa số và chữ in hoa
        requiredFormat = "3 ký tự (số và chữ in hoa)";
        isValidFormat = /^[0-9A-Z]{3}$/.test(row.abbr);
    }

    // Show warning if format is invalid
    if (!isValidFormat) {
        frappe.show_alert({
            message: __(`Lỗi định dạng: Abbreviation "${row.abbr}" cho "${attributeName}" phải là ${requiredFormat}.`),
            indicator: 'red'
        }, 7);
    }
}

/**
 * Validates a single row when attribute value or abbreviation is changed
 * Provides immediate feedback to the user
 */
function validateAttributeRow(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const currentValues = frm.doc.item_attribute_values || [];

    if (!row.attribute_value || !row.abbr) return;

    let hasDuplicateValue = false;
    let hasDuplicateAbbr = false;

    // Check for duplicates within the current attribute values
    currentValues.forEach(value => {
        // Skip comparing with itself
        if (value.name === row.name) return;

        // Check for duplicate attribute value (case insensitive)
        if (value.attribute_value && row.attribute_value &&
            value.attribute_value.toLowerCase() === row.attribute_value.toLowerCase()) {
            hasDuplicateValue = true;
        }

        // Check for duplicate abbreviation (case insensitive)
        if (value.abbr && row.abbr &&
            value.abbr.toLowerCase() === row.abbr.toLowerCase()) {
            hasDuplicateAbbr = true;
        }
    });

    // Show warnings for duplicates
    if (hasDuplicateValue) {
        frappe.show_alert({
            message: __(`Warning: Duplicate attribute value "${row.attribute_value}" found in this attribute.`),
            indicator: 'orange'
        }, 5);
    }

    if (hasDuplicateAbbr) {
        frappe.show_alert({
            message: __(`Warning: Duplicate abbreviation "${row.abbr}" found in this attribute.`),
            indicator: 'orange'
        }, 5);
    }

    // Get data from other attributes to check for system-wide duplicates
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Item Attribute",
            fields: ["name", "attribute_name", "item_attribute_values"],
        },
        callback: function (response) {
            if (response.message) {
                const existingAttributes = response.message;
                let externalDuplicateValue = null;
                let externalDuplicateAbbr = null;

                // Check each attribute
                existingAttributes.forEach(attr => {
                    // Skip current attribute
                    if (attr.name === frm.doc.name) return;

                    // Check each value in the attribute
                    (attr.item_attribute_values || []).forEach(value => {
                        // Check for duplicate attribute value (case insensitive)
                        if (value.attribute_value && row.attribute_value &&
                            value.attribute_value.toLowerCase() === row.attribute_value.toLowerCase()) {
                            externalDuplicateValue = attr.attribute_name;
                        }

                        // Check for duplicate abbreviation (case insensitive)
                        if (value.abbr && row.abbr &&
                            value.abbr.toLowerCase() === row.abbr.toLowerCase()) {
                            externalDuplicateAbbr = attr.attribute_name;
                        }
                    });
                });

                // Show warnings for external duplicates
                if (externalDuplicateValue) {
                    frappe.show_alert({
                        message: __(`Warning: Attribute value "${row.attribute_value}" already exists in "${externalDuplicateValue}".`),
                        indicator: 'red'
                    }, 7);
                }

                if (externalDuplicateAbbr) {
                    frappe.show_alert({
                        message: __(`Warning: Abbreviation "${row.abbr}" already exists in "${externalDuplicateAbbr}".`),
                        indicator: 'red'
                    }, 7);
                }
            }
        }
    });
}
/**
 * Common utility functions for Item Attribute management
 * These functions can be reused across multiple modules
 */

/**
 * Generates the next sequential code from the current maximum code
 * Supports both 2-character and 3-character codes
 * Uses alphanumeric sequence: 0-9, A-Z
 * @param {String} max_code - The current maximum code
 * @returns {String} The next sequential code
 */
function get_next_code(max_code) {
    try {
        // Determine code length
        const codeLength = max_code ? max_code.length : 3;

        // If max_code is empty or invalid, return default code
        if (!max_code || (codeLength !== 2 && codeLength !== 3)) {
            return codeLength === 2 ? '00' : '000';
        }

        // Define valid characters (0-9 and A-Z)
        const validChars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';

        // Convert current code to character array
        const codeChars = max_code.split('');

        // Start from rightmost character
        let position = codeLength - 1;
        let carry = true;

        // Process each character from right to left
        while (position >= 0 && carry) {
            // Get current character at this position
            const currentChar = codeChars[position];

            // Find its index in the validChars string
            const currentIndex = validChars.indexOf(currentChar);

            if (currentIndex === validChars.length - 1) {
                // If it's the last character (Z), reset to first (0) and carry
                codeChars[position] = '0';
                carry = true;
            } else {
                // Otherwise, increment to next character and stop carry
                codeChars[position] = validChars[currentIndex + 1];
                carry = false;
            }

            // Move to next position on the left
            position--;
        }

        // If there's still a carry after processing all positions,
        // we've exceeded the maximum possible code (ZZ or ZZZ)
        if (carry) {
            console.warn('Warning: Code sequence overflow, returning to ' + '0'.repeat(codeLength));
            return '0'.repeat(codeLength);
        }

        // Join characters back into a string
        return codeChars.join('');
    } catch (error) {
        console.error('Error generating next code:', error);
        // Fallback to default code in case of error
        return max_code && max_code.length === 2 ? '00' : '000';
    }
}

/**
 * Gets the last abbreviation for an attribute, or returns default based on attribute type
 * @param {String} attributeName - The name of the attribute (Color, Size, Brand, etc.)
 * @param {Array} existingValues - Array of existing attribute values with abbreviations
 * @returns {String} The last abbreviation or default code
 */
function getLastAbbreviation(attributeName, existingValues = []) {
    if (existingValues.length > 0) {
        return existingValues[existingValues.length - 1].abbr;
    }

    // Default codes based on attribute type
    if (attributeName === "Color" || attributeName === "Size" || attributeName === "Info") {
        return "000"; // 3-character code
    } else if (attributeName === "Brand" || attributeName === "Season") {
        return "00";  // 2-character code
    } else {
        return "000"; // Default 3-character code
    }
}

/**
 * Converts a string to Proper Case (like Excel PROPER function)
 * Capitalizes first letter of each word, preserves spaces
 * Special handling: If string starts with a number, the first letter after the number is capitalized
 * Examples: "red color" � "Red Color", "25cm" � "25Cm", "dark-blue" � "Dark-Blue"
 * @param {String} str - The string to convert
 * @returns {String} The proper case string
 */
function toProperCase(str) {
    if (!str) return str;

    let result = str.trim().toLowerCase();
    
    // Step 1: Capitalize letters at word boundaries (start of string, after space, hyphen, dot)
    result = result.replace(/(^|[\s\-\.])([a-z])/g, function (_, separator, letter) {
        return separator + letter.toUpperCase();
    });
    
    // Step 2: Special case - capitalize letter immediately after any digit
    // This handles cases like "10cm" → "10Cm", "25cm" → "25Cm"
    result = result.replace(/(\d)([a-z])/g, function (_, digit, letter) {
        return digit + letter.toUpperCase();
    });
    
    return result;
}

/**
 * Validates a new Item Attribute to ensure there are no duplicate Attribute Values or Abbreviations
 * Checks both against existing attributes and within the new attribute itself
 * @param {Object} newAttribute - The new attribute object being created
 * @param {String} newAttribute.name - Name of the attribute
 * @param {String} newAttribute.attribute_name - Display name of the attribute
 * @param {Array} newAttribute.item_attribute_values - Array of attribute values
 * @param {Array} existingAttributes - Array of existing attributes to check against
 * @returns {Object} Validation result with isValid boolean and message string
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

// Export functions to global scope for use in other scripts
(function() {
    'use strict';
    
    // Ensure window object exists
    if (typeof window !== 'undefined') {
        window.get_next_code = get_next_code;
        window.getLastAbbreviation = getLastAbbreviation;
        window.toProperCase = toProperCase;
        window.validateItemAttribute = validateItemAttribute;
        
    }
    
    // For Node.js environments
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            get_next_code,
            getLastAbbreviation,
            toProperCase,
            validateItemAttribute
        };
    }
})();
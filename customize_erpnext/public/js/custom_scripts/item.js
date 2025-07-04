frappe.ui.form.on('Item', {
    onload: async function (frm) {
        // Chỉ áp dụng cho Item mới 
        if (frm.is_new()) {
            try {
                // set valune for item_group =""    
                frm.set_value('item_group', '');
                console.log('Current item_group:', frm.doc.item_group);
                let current_user = frappe.session.user;
                // Lấy role profile và thiết lập filter trước khi tiếp tục
                await frappe.call({
                    method: 'customize_erpnext.api.utilities.get_role_profile',
                    args: {
                        email: current_user
                    },
                    callback: function (r) {
                        if (r.message) {
                            const role_profile = r.message.role_profile;
                            console.log("get_role_profile:", r.role_profile);
                            // Setup filters ngay sau khi có role_profile
                            setup_item_group_filters(frm, role_profile);
                            // Setup validation ngay sau khi có role_profile 
                            setup_item_group_validation(frm, role_profile);
                        }
                    }
                });

            } catch (error) {
                console.error("Error in onload:", error);
                frappe.throw(__('Error loading item form. Please check console for details.'));
            }
        }

    },
    before_save: function (frm) {
        if (!frm.doc.description) {
            frm.set_value('description', frm.doc.item_name);
        }

    },
    refresh: function (frm) {
        // Disable nút Single Variant
        frm.page.remove_inner_button('Single Variant', 'Create');

        // Thêm button để update warehouse manual
        if (frm.doc.docstatus === 0) { // Chỉ hiện khi đang draft
            frm.add_custom_button(__('Update Default Warehouse'), async function () {
                await update_default_warehouse(frm);
            }, __('Actions'));
        }
    },
    item_group: function (frm) {
        console.log('item_group function called');
        console.log('Current item_name:', frm.doc.item_name);
        console.log('Current item_group:', frm.doc.item_group);

        // Check if form is already saved
        if (!frm.is_new()) {
            frappe.throw(__('Not allowed to change group after save.'));
            return;
        }

        // Check if item name exists
        if (!frm.doc.item_name || frm.doc.item_name.trim() === '') {
            if (frm.doc.item_group.length > 0) {
                frappe.throw(__('Please enter Item Name first'));
                return;
            }

        }

        // If we reach here, item name exists and we can proceed
        if (frm.doc.item_group) {
            console.log("Processing item group:", frm.doc.item_group);
            // Check if exits items
            is_exists_item(frm.doc.item_group, frm.doc.item_name).then(async (result) => {
                if (result.exists) {
                    frappe.throw(__('Item already exits in system: <a href="/app/item/{0}" target="_blank">{1}</a>', [result.item_code, result.item_code]));
                    frm.set_value('item_name', '');
                } else {
                    await generate_new_item_code(frm);
                    await set_default_values(frm);
                    // Update warehouse sau khi set default values
                    await update_default_warehouse(frm);
                }
            }).catch(err => {
                console.error("Error in item_group handler:", err);
            });
        }
    },
    customer: async function (frm) {
        // Trigger update warehouse khi customer thay đổi
        console.log('Customer changed, updating default warehouse');
        await update_default_warehouse(frm);
    },
    is_customer_provided_item: async function (frm) {
        // Trigger update warehouse khi is_customer_provided_item thay đổi
        console.log('is_customer_provided_item changed, updating default warehouse');
        await update_default_warehouse(frm);
    },
    has_variants: function (frm) {
        if (frm.doc.has_variants) {
            create_attributes(frm);
        }
    },
    custom_office_factory_sub_group: function (frm) {
        // Check for duplicate items
        is_exists_item(frm.doc.custom_office_factory_sub_group, frm.doc.item_name).then((result) => {
            // Only proceed if no duplicates found 
            if (!result.exists) {
                generate_new_item_code(frm);
            }
            else {
                frappe.throw(__('Item đã tồn tại trong hệ thống'));
                frm.set_value('item_name', '');
            }
        }).catch(err => {
            console.error("Error in custom_office_factory_sub_group handler:", err);
        });
    },
    item_name: function (frm) {
        if (frm.doc.item_name && frm.doc.item_group) {
            // Trim dữ liệu item_name để loại bỏ khoảng trắng đầu và cuối
            let trimmed_item_name = frm.doc.item_name.trim();

            // Cập nhật lại giá trị đã trim vào field (chỉ khi có thay đổi)
            if (frm.doc.item_name !== trimmed_item_name) {
                frm.set_value('item_name', trimmed_item_name);
            }

            // Kiểm tra nếu item_name sau khi trim vẫn có giá trị
            if (trimmed_item_name) {
                is_exists_item(frm.doc.custom_office_factory_sub_group, trimmed_item_name).then((result) => {
                    // Only proceed if no duplicates found 
                    if (!result.exists) {
                        generate_new_item_code(frm);
                    }
                    else {
                        frappe.throw(__('Item already exists in the system : <a href="/app/item/{0}" target="_blank">{1}</a>', [result.item_code, result.item_code]));
                        frm.set_value('item_name', '');
                    }
                }).catch(err => {
                    console.error("Error in item_name handler:", err);
                });
            } else {
                // Nếu sau khi trim item_name trống, clear field
                frm.set_value('item_name', '');
            }
        }
    },
});

function create_attributes(frm) {
    try {
        if (frm.doc.has_variants) {
            const group = frm.doc.item_group || '';
            let attributes = [
                { attribute: 'Color' },
                { attribute: 'Size' },
                { attribute: 'Brand' },
                { attribute: 'Season' }
            ];
            // nếu item không thuộc nhóm có chứa Office, Factory hoặc Tools hoặc Assets
            if (!group.includes("Office-Factory") && !group.includes("Tools") && !group.includes("Assets")) {
                frm.set_value('attributes', attributes);
            }
            else {
                frm.set_value('attributes', []);
            }
            if (group.includes("Packing") || group.includes("Sewing")) {
                frappe.msgprint({
                    title: __('Notification'),
                    indicator: 'green',
                    message: __('Với nhóm Packing và Sewing, có thể có thuộc tính Info')
                });
            }
        }
    } catch (error) {

    }
}
async function generate_new_item_code(frm) {
    try {
        console.log("generate_new_item_code: group: ", frm.doc.item_group);
        // Get the basic prefix
        let prefix = '';
        for (const [key, value] of Object.entries(item_group_prefixes)) {
            if (frm.doc.item_group.includes(key)) {
                prefix = value;
                break;
            }
        }
        console.log("First prefix:", prefix);
        if (frm.doc.item_group.includes('O-Office, Factory')) {
            if (frm.doc.custom_office_factory_sub_group == '') {
                return true;
            }
            else {
                prefix = `${frm.doc.custom_office_factory_sub_group.substring(0, 3)}`;
            }

        }
        console.log("Final prefix:", prefix);
        item_code = await find_next_code(frm.doc.item_group, prefix);
        frm.set_value('item_code', item_code);
        console.log("Generated new item code:", item_code);
    } catch (err) {
        console.error("Error generating item code:", err);
        frappe.throw(__('Error generating item code. Please check the console for details.'));
    }
}
const item_group_prefixes = {
    'B-Finished Goods': 'B-',
    // '02 - Semi-Finished Goods': 'B',
    'C-Fabric': 'C-',
    'D-Interlining': 'D-',
    'E-Padding': 'E-',
    'F-Packing': 'F-',
    'G-Sewing': 'G-',
    'H-Thread': 'H-',
    'O-Office, Factory': 'O-',
    'T-Tools': 'T-',
    'A-Assets': 'A-'
};
const default_item_config = {
    'B-Finished Goods': {
        stock_uom: 'Pcs',
        has_variants: 1,
        is_purchase_item: 0,
        is_customer_provided_item: 0,
        is_sales_item: 1,
        include_item_in_manufacturing: 0
    },
    // '02 - Semi-Finished Goods': {
    //     stock_uom: 'Pcs',
    //     has_variants: 1,
    //     is_purchase_item: 0,
    //     is_customer_provided_item: 0,
    //     is_sales_item: 0,
    //     include_item_in_manufacturing: 1
    // },
    'C-Fabric': {
        stock_uom: 'Meter',
        has_variants: 1,
        is_purchase_item: 0,
        default_material_request_type: 'Customer Provided',
        is_customer_provided_item: 1,
        is_sales_item: 0,
        include_item_in_manufacturing: 1
    },
    'D-Interlining': {
        stock_uom: 'Meter',
        has_variants: 1,
        is_purchase_item: 0,
        default_material_request_type: 'Customer Provided',
        is_customer_provided_item: 1,
        is_sales_item: 0,
        include_item_in_manufacturing: 1
    },
    'E-Padding': {
        stock_uom: 'Meter',
        has_variants: 1,
        is_purchase_item: 0,
        default_material_request_type: 'Customer Provided',
        is_customer_provided_item: 1,
        is_sales_item: 0,
        include_item_in_manufacturing: 1
    },
    'F-Packing': {
        stock_uom: 'Pcs',
        has_variants: 1,
        is_purchase_item: 1,
        default_material_request_type: 'Purchase',
        is_customer_provided_item: 0,
        is_sales_item: 0,
        include_item_in_manufacturing: 1
    },
    'G-Sewing': {
        stock_uom: 'Pcs',
        has_variants: 1,
        is_purchase_item: 0,
        default_material_request_type: 'Customer Provided',
        is_customer_provided_item: 1,
        is_sales_item: 0,
        include_item_in_manufacturing: 1
    },
    'H-Thread': {
        stock_uom: 'Cone',
        has_variants: 1,
        is_purchase_item: 0,
        default_material_request_type: 'Customer Provided',
        is_customer_provided_item: 1,
        is_sales_item: 0,
        include_item_in_manufacturing: 1
    },
    'O-Office, Factory': {
        stock_uom: 'Pcs',
        has_variants: 0,
        is_purchase_item: 1,
        default_material_request_type: 'Purchase',
        is_customer_provided_item: 0,
        is_sales_item: 0,
        include_item_in_manufacturing: 0,
        is_stock_item: 0
    },
    'T-Tools': {
        stock_uom: 'Pcs',
        has_variants: 0,
        is_purchase_item: 1,
        default_material_request_type: 'Purchase',
        is_customer_provided_item: 0,
        is_sales_item: 0,
        include_item_in_manufacturing: 0,
        is_stock_item: 0
    },
    'A-Assets': {
        stock_uom: 'Pcs',
        has_variants: 0,
        is_purchase_item: 1,
        default_material_request_type: 'Purchase',
        is_customer_provided_item: 0,
        is_sales_item: 0,
        include_item_in_manufacturing: 0,
        is_fixed_asset: 1
    }
    // Add other configurations as needed
};

/**
 * Update default warehouse - có thể gọi độc lập
 * Function này có thể được trigger từ:
 * - Event customer thay đổi
 * - Event is_customer_provided_item thay đổi  
 * - Button "Update Default Warehouse" trong form
 * - Manual call từ code khác
 * 
 * @param {object} frm - The form object
 */
async function update_default_warehouse(frm) {
    try {
        // Chỉ update warehouse nếu item là stock item
        if (frm.doc.is_stock_item !== 0) {
            const default_warehouse = await get_default_warehouse(frm);

            // Update item_defaults với warehouse mới
            frm.set_value('item_defaults', [{
                company: frappe.defaults.get_default('company'),
                default_warehouse: default_warehouse
            }]);

            // Show notification
            frappe.show_alert({
                message: __('Default warehouse updated to: {0}', [default_warehouse]),
                indicator: 'green'
            });
        } else {
            frappe.show_alert({
                message: __('Item is not a stock item, skipping warehouse update'),
                indicator: 'orange'
            });
        }
    } catch (error) {
        console.error("Error updating default warehouse:", error);
        frappe.show_alert({
            message: __('Error updating default warehouse'),
            indicator: 'red'
        });
    }
}

/**
 * Determine default warehouse based on customer and item properties
 * @param {object} frm - The form object
 * @returns {Promise<string>} The appropriate warehouse code
 * 
 * Note: Cần có field 'customer' trong Item DocType để function này hoạt động
 * Hoặc có thể lấy customer từ context khác (session, user settings, etc.)
 */
async function get_default_warehouse(frm) {
    // Logic mới cho default warehouse
    if (frm.doc.item_group && frm.doc.item_group.includes('B-Finished Goods')) {
        // Nếu item là B-Finished Goods, trả về warehouse mặc định Finished Goods - TIQN
        return 'Finished Goods - TIQN';
    } else
        if (frm.doc.is_customer_provided_item) {
            // Lấy thông tin customer - có thể từ field customer hoặc từ context khác
            // TODO: Cần xác định customer được lấy từ đâu trong Item form
            const customer = frm.doc.customer || '';
            // if item group is 'B-Finished Goods'

            if (customer) {
                try {
                    // Query Customer doctype để lấy custom_default_warehouse
                    const customer_data = await frappe.db.get_value('Customer', customer, 'custom_default_warehouse');

                    if (customer_data && customer_data.message && customer_data.message.custom_default_warehouse) {
                        console.log("Found custom default warehouse for customer:", customer, "->", customer_data.message.custom_default_warehouse);
                        return customer_data.message.custom_default_warehouse;
                    }
                } catch (error) {
                    console.error("Error getting customer default warehouse:", error);
                }
            }
        }

    // Trường hợp khác - fallback
    return 'Material - Local - TIQN';
}

async function set_default_values(frm) {
    console.log("set_default_values for:", frm.doc.item_group);
    try {
        const group = frm.doc.item_group;

        // Set values based on the configuration 
        Object.entries(default_item_config).forEach(([key, values]) => {
            if (group.includes(key)) {
                Object.entries(values).forEach(([field, value]) => {
                    frm.set_value(field, value);
                    // frappe.show_alert({ message: `Set ${field} to ${value}`, indicator: 'green', duration: 5 });
                });
            }
        });

        // Note: Không set default warehouse ở đây nữa
        // Warehouse sẽ được set riêng thông qua update_default_warehouse()

    } catch (err) {
        console.error("Error setting default values:", err);
    }
}

// Function setup filters
function setup_item_group_filters(frm, role_profile) {
    console.log("Setting up filters - Role Profile:", role_profile);

    if (role_profile === 'Warehouse') {
        console.log("Applying Warehouse filter");
        set_warehouse_filter(frm);
        show_filter_message('Warehouse');
    }
    else if (role_profile === 'Purchase') {
        console.log("Applying Purchase filter");
        set_purchase_filter(frm);
        show_filter_message('Purchase');
        //    set field custom_old_item_code show
        frm.set_df_property('custom_old_item_code', 'hidden', 0);
    } else if (role_profile === 'MD') {
        console.log("Applying MD filter");
        set_md_filter(frm);
        show_filter_message('MD');
    }
}

// Function setup validation
function setup_item_group_validation(frm, role_profile) {
    frm.fields_dict['item_group'].df.onchange = function () {
        if (frm.doc.item_group) {
            frappe.db.get_value('Item Group', frm.doc.item_group, 'custom_pic')
                .then(r => {
                    console.log("Selected Item Group PIC:", r.message.custom_pic);

                    if (roles.includes('Item') && r.message.custom_pic !== 'Warehouse') {
                        frappe.throw(__('Với Role Item, bạn chỉ được phép chọn Item Group có Custom PIC là Warehouse'));
                        frm.set_value('item_group', '');
                    }
                    else if (role_profile === 'Purchase' && r.message.custom_pic !== 'Purchase') {
                        frappe.throw(__('Với Role Profile Purchase, bạn chỉ được phép chọn Item Group có Custom PIC là Purchase'));
                        frm.set_value('item_group', '');
                    }
                });
        }
    };
}
/**
 * Find the next available item code based on a prefix
 * @param {string} prefix - The prefix to search for in item codes
 * @returns {string} The next available item code (prefix + next_code)
 */
async function find_next_code(item_group, prefix) {
    // Get the item with the highest item_code matching the item_group
    let max_code = '000';
    const items = await frappe.db.get_list('Item', {
        filters: {
            'item_group': item_group,
            'has_variants': 1
        },
        fields: ['item_code'],
        order_by: 'item_code desc',
        limit: 1
    });

    if (items && items.length > 0) {
        max_code = items[0].item_code.split("-")[1];
        console.log("max_code:", max_code)
    }

    if (item_group.includes("O-Office, Factory")) {
        const next_code = await get_next_code_number(max_code);
        return prefix + next_code;
    }
    if (item_group.includes("B-Finished Goods") || item_group.includes("C-Fabric") || item_group.includes("D-Interlining") || item_group.includes("E-Padding") || item_group.includes("F-Packing") || item_group.includes("G-Sewing") || item_group.includes("H-Thread")) {
        const next_code = await get_next_code(max_code);
        return prefix + next_code;
    }

}

async function get_next_code_number(max_code) {
    console.error('get_next_code_number:', max_code);
    try {
        // Convert max_code to number and add 1
        let next_number = parseInt(max_code) + 1;

        // Pad with leading zeros to maintain 4 digits
        return next_number.toString().padStart(4, '0');
        console.error('get_next_code_number next_number:', next_number);
    } catch (error) {
        console.error('Error generating next number code:', error);
        // Fallback to '0001' in case of any error
        return '0001';
    }
}

/**
 * Check if a code follows the pattern of digits and uppercase letters
 * @param {string} code - The 3-character code to validate
 * @returns {boolean} Whether the code is valid
 */
function is_valid_code(code) {
    // Check if the code consists of only digits (0-9) and uppercase letters (A-Z)
    return /^[0-9A-Z]{3}$/.test(code);
}
async function get_next_code(max_code) {
    // Define valid characters (0-9 and A-Z)
    const validChars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    // Convert the current code to an array of characters
    const codeChars = max_code.split('');
    let position = max_code.length - 1;
    let carry = true;
    console.log("get_next_code : max_code:", max_code);
    try {
        while (position >= 0 && carry) {
            // Get the current character at this position
            const currentChar = codeChars[position];
            // Find its index in the validChars string
            const currentIndex = validChars.indexOf(currentChar);
            if (currentIndex === validChars.length - 1) {
                // If it's the last valid character (Z), reset to first (0) and carry over
                codeChars[position] = '0';
                carry = true;
            } else {
                // Otherwise, increment to the next character and stop carrying
                codeChars[position] = validChars[currentIndex + 1];
                carry = false;
            }
            // Move to the next position to the left
            position--;
        }
        // Join the characters back into a string
        console.log("get_next_code => return:", codeChars.join(''));
        return codeChars.join('');
    } catch (error) {
        console.error('Error generating next code:', error);
        // Fallback to '000' in case of any error
        return 'error';
    }
}

// Examples of usage:
// get_next_code('000') returns '001'
// get_next_code('009') returns '00A'
// get_next_code('00Z') returns '010'
// get_next_code('0ZZ') returns '100'
// get_next_code('ZZZ') returns '000' (overflow)

/**
 * Utility function để trigger update warehouse từ external code
 * @param {string} item_name - Item name/code
 * Usage: window.update_item_warehouse('ITEM-001');
 */
window.update_item_warehouse = async function (item_name) {
    try {
        const frm = cur_frm;
        if (frm && frm.doc.name === item_name) {
            await update_default_warehouse(frm);
        } else {
            console.error("Current form does not match the item:", item_name);
        }
    } catch (error) {
        console.error("Error in update_item_warehouse:", error);
    }
};

/**
 * Check if an item with the specified name exists within a particular item group
 * @param {string} item_group - The item group to search within
 * @param {string} name - The item name to check for
 * @returns {Promise<boolean>} True if the item exists, false otherwise
 */
async function is_exists_item(item_group, item_name) {
    try {
        const sanitized_name = item_name.trim();
        const sanitized_group = item_group.trim();

        // Tìm item khớp tên và nhóm
        const items = await frappe.db.get_list('Item', {
            filters: {
                'item_group': sanitized_group,
                'item_name': sanitized_name
            },
            fields: ['name', 'variant_of'],
            limit: 1
        });

        if (items.length > 0) {
            const found_item = items[0];
            const item_code = found_item.variant_of || found_item.name;  // nếu là variant thì trả template

            console.log("Item exists:", item_code);
            return {
                exists: true,
                item_code: item_code
            };
        } else {
            return {
                exists: false
            };
        }
    } catch (err) {
        console.error("Error checking item existence:", err);
        throw err;
    }
}
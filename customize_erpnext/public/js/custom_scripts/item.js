frappe.ui.form.on('Item', {
    onload: function (frm) {
        if (frm.is_new()) {
            frm.set_value('item_group', '');
        }
    },
    before_save: function (frm) {
        if (!frm.doc.description) {
            frm.set_value('description', frm.doc.item_name);
        }
    },
    refresh: function (frm) {
        frm.page.remove_inner_button('Single Variant', 'Create');
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Update Default Warehouse'), async function () {
                await update_default_warehouse(frm);
            }, __('Actions'));
        }
    },
    item_group: function (frm) {
        if (frm.doc.item_group === 'U-Uniform') return;
        if (!frm.is_new()) {
            frappe.throw(__('Not allowed to change group after save.'));
            return;
        }
        // Chưa nhập Item Name → chưa sinh code vội (tránh báo lỗi khi tạo item mới /
        // khi group được set tự động từ filter). Code sẽ được sinh ở handler item_name.
        if (!frm.doc.item_name || !frm.doc.item_name.trim()) return;
        if (!frm.doc.item_group) return;

        is_auto_code_group(frm.doc.item_group).then(async (is_supported) => {
            if (!is_supported) return;
            is_exists_item(frm.doc.item_group, frm.doc.item_name).then(async (result) => {
                if (result.exists) {
                    frappe.throw(__('Item already exits in system: <a href="/app/item/{0}" target="_blank">{1}</a>', [result.item_code, result.item_code]));
                    frm.set_value('item_name', '');
                } else {
                    await generate_new_item_code(frm);
                    await set_default_values(frm);
                    await update_default_warehouse(frm);
                }
            }).catch(err => console.error("Error in item_group handler:", err));
        });
    },
    customer: async function (frm) {
        await update_default_warehouse(frm);
    },
    is_customer_provided_item: async function (frm) {
        await update_default_warehouse(frm);
    },
    has_variants: function (frm) {
        if (frm.doc.has_variants) create_attributes(frm);
    },
    custom_office_factory_sub_group: function (frm) {
        is_auto_code_group(frm.doc.item_group).then((is_supported) => {
            if (!is_supported) return;
            is_exists_item(frm.doc.custom_office_factory_sub_group, frm.doc.item_name).then((result) => {
                if (!result.exists) {
                    generate_new_item_code(frm);
                } else {
                    frappe.throw(__('Item đã tồn tại trong hệ thống'));
                    frm.set_value('item_name', '');
                }
            }).catch(err => console.error("Error in custom_office_factory_sub_group handler:", err));
        });
    },
    item_name: function (frm) {
        if (!frm.doc.item_name || !frm.doc.item_group) return;

        const trimmed = frm.doc.item_name.trim();
        if (frm.doc.item_name !== trimmed) frm.set_value('item_name', trimmed);
        if (!trimmed) { frm.set_value('item_name', ''); return; }

        is_auto_code_group(frm.doc.item_group).then((is_supported) => {
            if (!is_supported) return;
            is_exists_item(frm.doc.item_group, trimmed).then((result) => {
                if (!result.exists) {
                    generate_new_item_code(frm);
                } else {
                    frappe.throw(__('Item already exists in the system : <a href="/app/item/{0}" target="_blank">{1}</a>', [result.item_code, result.item_code]));
                    frm.set_value('item_name', '');
                }
            }).catch(err => console.error("Error in item_name handler:", err));
        });
    },
});

// Returns true if item_group should use auto-code + default config:
// - B-Finished Goods (always)
// - Any group whose parent_item_group contains "Material" (= 03 - Materials children)
async function is_auto_code_group(item_group) {
    if (!item_group) return false;
    if (item_group.includes('B-Finished Goods')) return true;
    const result = await frappe.db.get_value('Item Group', item_group, 'parent_item_group');
    const parent = result?.message?.parent_item_group || '';
    return parent.includes('Material');
}

function create_attributes(frm) {
    if (!frm.doc.has_variants) return;
    const group = frm.doc.item_group || '';
    if (group.includes('O-Office') || group.includes('Tools') || group.includes('Assets')) {
        frm.set_value('attributes', []);
        return;
    }
    frm.set_value('attributes', [
        { attribute: 'Color' },
        { attribute: 'Size' },
        { attribute: 'Brand' },
        { attribute: 'Season' }
    ]);
}

async function generate_new_item_code(frm) {
    try {
        let prefix = '';
        for (const [key, value] of Object.entries(item_group_prefixes)) {
            if (frm.doc.item_group.includes(key)) { prefix = value; break; }
        }
        if (frm.doc.item_group.includes('O-Office, Factory')) {
            if (!frm.doc.custom_office_factory_sub_group) return;
            prefix = frm.doc.custom_office_factory_sub_group.substring(0, 3);
        }
        const item_code = await find_next_code(frm.doc.item_group, prefix);
        frm.set_value('item_code', item_code);
    } catch (err) {
        console.error("Error generating item code:", err);
        frappe.throw(__('Error generating item code. Please check the console for details.'));
    }
}

const item_group_prefixes = {
    'B-Finished Goods': 'B-',
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
    'C-Fabric': {
        stock_uom: 'Meter',
        has_variants: 1,
        has_batch_no: 1,
        has_serial_no: 0,
        create_new_batch: 0,
        batch_number_series: '',
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
};

async function update_default_warehouse(frm) {
    try {
        if (frm.doc.is_stock_item !== 0) {
            const default_warehouse = await get_default_warehouse(frm);
            frm.set_value('item_defaults', [{
                company: frappe.defaults.get_default('company'),
                default_warehouse: default_warehouse
            }]);
            frappe.show_alert({ message: __('Default warehouse updated to: {0}', [default_warehouse]), indicator: 'green' });
        } else {
            frappe.show_alert({ message: __('Item is not a stock item, skipping warehouse update'), indicator: 'orange' });
        }
    } catch (error) {
        console.error("Error updating default warehouse:", error);
        frappe.show_alert({ message: __('Error updating default warehouse'), indicator: 'red' });
    }
}

async function get_default_warehouse(frm) {
    if (frm.doc.item_group && frm.doc.item_group.includes('B-Finished Goods')) {
        return 'Finished Goods - TIQN';
    }
    if (frm.doc.is_customer_provided_item) {
        const customer = frm.doc.customer || '';
        if (customer) {
            try {
                const customer_data = await frappe.db.get_value('Customer', customer, 'custom_default_warehouse');
                if (customer_data?.message?.custom_default_warehouse) {
                    return customer_data.message.custom_default_warehouse;
                }
            } catch (error) {
                console.error("Error getting customer default warehouse:", error);
            }
        }
    }
    return 'Material - Local - TIQN';
}

async function set_default_values(frm) {
    try {
        const group = frm.doc.item_group;
        Object.entries(default_item_config).forEach(([key, values]) => {
            if (group.includes(key)) {
                Object.entries(values).forEach(([field, value]) => frm.set_value(field, value));
            }
        });
    } catch (err) {
        console.error("Error setting default values:", err);
    }
}

// Query last item_code in group (has_variants=1 = template items only) and increment base-36
async function find_next_code(item_group, prefix) {
    const items = await frappe.db.get_list('Item', {
        filters: { 'item_group': item_group, 'has_variants': 1 },
        fields: ['item_code'],
        order_by: 'item_code desc',
        limit: 1
    });
    const max_code = items.length > 0 ? (items[0].item_code.split('-')[1] || '000') : '000';
    return prefix + await get_next_code(max_code);
}

async function get_next_code(max_code) {
    const validChars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const codeChars = max_code.split('');
    let position = max_code.length - 1;
    let carry = true;
    try {
        while (position >= 0 && carry) {
            const currentIndex = validChars.indexOf(codeChars[position]);
            if (currentIndex === validChars.length - 1) {
                codeChars[position] = '0';
            } else {
                codeChars[position] = validChars[currentIndex + 1];
                carry = false;
            }
            position--;
        }
        return codeChars.join('');
    } catch (error) {
        console.error('Error generating next code:', error);
        return 'error';
    }
}

async function is_exists_item(item_group, item_name) {
    try {
        const items = await frappe.db.get_list('Item', {
            filters: { 'item_group': item_group.trim(), 'item_name': item_name.trim() },
            fields: ['name', 'variant_of'],
            order_by: 'creation desc',
            limit: 1
        });
        if (items.length > 0) {
            const item_code = items[0].variant_of || items[0].name;
            return { exists: true, item_code };
        }
        return { exists: false };
    } catch (err) {
        console.error("Error checking item existence:", err);
        throw err;
    }
}

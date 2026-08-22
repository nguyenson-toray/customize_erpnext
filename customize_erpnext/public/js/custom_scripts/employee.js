// import apps/customize_erpnext/customize_erpnext/public/js/utilities.js
// import apps/customize_erpnext/customize_erpnext/public/js/shared_fingerprint_sync.js

// Ensure FingerprintScannerDialog is available
function ensureFingerprintModule() {
    return new Promise((resolve) => {
        if (window.FingerprintScannerDialog && window.FingerprintScannerDialog.showForEmployee) {
            resolve(true);
            return;
        }

        // Try to manually load the script if needed
        if (!document.querySelector('script[src*="fingerprint_scanner_dialog.js"]')) {
            const script = document.createElement('script');
            script.src = '/assets/customize_erpnext/js/fingerprint_scanner_dialog.js';
            document.head.appendChild(script);
        }

        // Try to load module if not available
        let attempts = 0;
        const maxAttempts = 15;  // Increased attempts

        const checkModule = () => {
            attempts++;

            if (window.FingerprintScannerDialog && window.FingerprintScannerDialog.showForEmployee) {
                resolve(true);
            } else if (attempts < maxAttempts) {
                setTimeout(checkModule, 200);
            } else {
                resolve(false);
            }
        };

        checkModule();
    });
}

frappe.ui.form.on('Employee', {
    onload: function (frm) {
        // Load province options for both current and permanent address
        load_province_options(frm);
    },

    refresh: function (frm) {
        // Full Name is what people type. Core marks it read-only because it derives
        // the value from first/middle/last; here that runs the other way round —
        // CustomEmployee.set_employee_name() derives the parts on save, and those
        // three fields are hidden.
        frm.set_df_property('employee_name', 'read_only', 0);

        // Check if employee can be modified (name and attendance_device_id)
        if (!frm.is_new() && frm.doc.name) {
            frappe.call({
                method: 'customize_erpnext.api.employee.employee_utils.allow_change_name_attendance_device_id',
                args: {
                    name: frm.doc.name
                },
                callback: function (r) {
                    if (!r.message) {
                        // Employee has checkin records, set fields as read-only
                        frm.set_df_property('employee', 'read_only', 1);
                        frm.set_df_property('attendance_device_id', 'read_only', 1);

                        // Add indicator
                        frm.dashboard.add_indicator(__('Employee ID and Attendance Device ID are locked (has attendance records)'), 'orange');
                    } else {
                        // Allow editing
                        frm.set_df_property('employee', 'read_only', 0);
                        frm.set_df_property('attendance_device_id', 'read_only', 0);
                    }
                }
            });
        }

        // Add custom button for fingerprint scanning if not new record
        if (!frm.is_new() && frm.doc.name) {
            frm.add_custom_button(__('Scan Fingerprints'), async function () {
                // Show fingerprint scanner dialog with fixed employee
                const moduleReady = await ensureFingerprintModule();
                if (moduleReady) {
                    window.FingerprintScannerDialog.showForEmployee(frm.doc.name, frm.doc.employee_name);
                } else {
                    frappe.msgprint({
                        title: __('Module Loading Failed'),
                        message: __('Fingerprint Scanner module could not be loaded. Please refresh the page and try again.'),
                        indicator: 'red'
                    });
                }
            },);
            frm.add_custom_button(__('Sync Fingerprints To Machines'), async function () {
                // Show fingerprint scanner dialog with fixed employee
                // Handle sync fingerprint button click
                if (!frm.is_new() && frm.doc.name) {
                    // Use shared sync dialog for single employee
                    const employee = {
                        employee_id: frm.doc.name,
                        employee_name: frm.doc.employee_name,
                        custom_group: frm.doc.custom_group
                    };
                    window.showSharedSyncDialog([employee]);
                } else {
                    frappe.msgprint({
                        title: __('Save Required'),
                        message: __('Please save the employee record first before syncing fingerprints.'),
                        indicator: 'orange'
                    });
                }
            },);

            // Photo management now lives entirely on /employee-photos
            frm.add_custom_button(__('Photo'), function () {
                window.open('/employee-photos?q=' + encodeURIComponent(frm.doc.name) + '&status=all&prefix=all', '_blank');
            },);
        }
        if (frm.is_new()) {
            // Auto-fill next employee code and attendance device ID
            if (!frm.doc.employee) {
                frappe.call({
                    method: 'customize_erpnext.api.employee.employee_utils.get_next_employee_code',
                    callback: function (r) {
                        if (r.message && !frm.doc.employee) {
                            frm.set_value('employee', r.message);
                        }
                    }
                });
            }
            if (!frm.doc.attendance_device_id) {
                frappe.call({
                    method: 'customize_erpnext.api.employee.employee_utils.get_next_attendance_device_id',
                    callback: function (r) {
                        if (r.message && !frm.doc.attendance_device_id) {
                            frm.set_value('attendance_device_id', String(r.message));
                        }
                    }
                });
            }
        }

        render_sub_status(frm);
        toggle_create_user_button(frm);
    },

    prefered_email: function (frm) {
        // Core chỉ thêm nút lúc refresh. Điền email xong mà không refresh thì nút không xuất
        // hiện lại — refresh để core tự quyết định, rồi hàm dưới lọc lần nữa.
        frm.refresh();
    },

    prefered_contact_email: function (frm) {
        // Core suy `prefered_email` từ field này (employee.js:125), nên đổi nó là đổi điều kiện.
        frm.refresh();
    },

    custom_copy_permanent_address_to_other_adress: function (frm) {
        if (frm.doc.custom_copy_permanent_address_to_other_adress) {
            console.log('Copy permanent address to current and origin address');
            copy_address(frm, 'permanent', 'current');
            translate_address_to_english(frm, 'current');
            // 🚧 TẠM TẮT 21/08/2026 — field quê quán đã bị gỡ khỏi Employee.
            // copy_address(frm, 'permanent', 'place_of_origin');
        }
    },
    // Current Address handlers
    custom_current_address_village: function (frm) {
        build_address_full_for_type(frm, 'current');
        translate_address_to_english(frm, 'current');
    },
    custom_current_address_commune: function (frm) {
        build_address_full_for_type(frm, 'current');
        translate_address_to_english(frm, 'current');
    },
    custom_current_address_province: function (frm) {
        handle_province_change(frm, 'current');
        translate_address_to_english(frm, 'current');
    },

    // Permanent Address handlers
    custom_permanent_address_village: function (frm) {
        build_address_full_for_type(frm, 'permanent');
        translate_address_to_english(frm, 'permanent');
    },
    custom_permanent_address_commune: function (frm) {
        build_address_full_for_type(frm, 'permanent');
        translate_address_to_english(frm, 'permanent');
    },
    custom_permanent_address_province: function (frm) {
        handle_province_change(frm, 'permanent');
        translate_address_to_english(frm, 'permanent');
    },

        // 🚧 TẠM TẮT 21/08/2026 — field custom_place_of_origin_address_* đã bị gỡ khỏi
        //    Employee. Giữ nguyên để khai lại sau; bỏ comment là chạy như cũ.
    // // Place of Origin Address handlers
    // custom_place_of_origin_address_village: function (frm) {
    //     build_address_full_for_type(frm, 'place_of_origin');
    // },
    // custom_place_of_origin_address_commune: function (frm) {
    //     build_address_full_for_type(frm, 'place_of_origin');
    // },
    // custom_place_of_origin_address_province: function (frm) {
    //     handle_province_change(frm, 'place_of_origin');
    // },

    before_save: function (frm) {
        // Ensure employee code follows TIQN-XXXX format
        if (frm.doc.employee && !frm.doc.employee.startsWith('TIQN-') && !frm.doc.employee.startsWith('TT-') ) {
            frappe.msgprint(__('Employee code should follow TIQN-XXXX or TT-XXXX format'));
            frappe.validated = false;
            return;
        }

        // check if employee_name icluding numbers throw error
        if (frm.doc.employee_name && /\d/.test(frm.doc.employee_name)) {
            frappe.msgprint(__('Employee name should not contain numbers'));
            frappe.validated = false;
        }

        // If only province is set (default suggestion, no commune selected) → clear the address
        Object.keys(ADDRESS_TYPES).forEach(address_type => {
            const fields = ADDRESS_TYPES[address_type];
            if (frm.doc[fields.province] && !frm.doc[fields.commune]) {
                frm.doc[fields.province] = '';
                frm.doc[fields.village] = '';
            }
        });

        // Build all address full fields before saving
        build_address_full_for_type(frm, 'permanent');
        build_address_full_for_type(frm, 'current');
        // 🚧 TẠM TẮT 21/08/2026 — quê quán đã gỡ khỏi Employee.
        // build_address_full_for_type(frm, 'place_of_origin');
    },
});

// ============================================================
// CREATE USER — chỉ hiện khi đã có Preferred Email
// ============================================================

/**
 * Gỡ nút "Create User" khi chưa có Preferred Email.
 *
 * Core thêm nút chỉ với điều kiện `!frm.is_new() && !frm.doc.user_id`
 * (erpnext/setup/doctype/employee/employee.js:49) rồi mở hộp thoại với email mặc định là
 * `prefered_email || company_email || personal_email`. Chưa có email nào thì ô đó trống, HR bấm
 * Create User và nhận lỗi "Email is required to create a user" từ server — nút mời gọi một thao
 * tác chắc chắn thất bại.
 *
 * Gỡ nút chứ không disable: doctype_js của app chạy SAU refresh của core nên nút đã được thêm
 * rồi; `remove_custom_button` là đường sạch nhất, không phải vá vào nội bộ hộp thoại của core.
 */
function toggle_create_user_button(frm) {
    if (frm.is_new() || frm.doc.user_id) return;   // core vốn đã không thêm nút
    if (frm.doc.prefered_email) return;            // đủ điều kiện — để nguyên nút của core

    frm.remove_custom_button(__('Create User'));
    frm.dashboard.add_indicator(
        __('Set Preferred Email to create a user account'),
        'orange'
    );
}

// ============================================================
// SUB STATUS
// ============================================================

/**
 * Vẽ `custom_sub_status` — field HTML, KHÔNG có cột trong DB và không lưu gì.
 * Nội dung được suy ra từ Employee Maternity mỗi lần mở form, nên nó luôn khớp
 * với hồ sơ thai sản kể cả khi hồ sơ đó vừa được sửa ở nơi khác.
 */
function render_sub_status(frm) {
    const field = frm.get_field('custom_sub_status');
    if (!field || !field.$wrapper) return;

    if (frm.is_new() || !frm.doc.name) {
        field.$wrapper.empty();
        return;
    }

    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_status_sync.get_employee_sub_status',
        args: { employee: frm.doc.name },
        callback: function (r) {
            const d = r.message;
            if (!d) {
                field.$wrapper.empty();
                return;
            }

            const ref = frappe.utils.escape_html(d.reference || '');
            const link = `/app/employee-maternity/${encodeURIComponent(d.reference || '')}`;

            let period = '';
            if (d.from_date) {
                period = frappe.datetime.str_to_user(d.from_date) +
                    ' → ' + (d.to_date ? frappe.datetime.str_to_user(d.to_date) : '…');
            }

            field.$wrapper.html(`
                <div class="d-flex align-items-center flex-wrap" style="gap:8px;">
                    <span class="indicator-pill ${d.indicator}">${__(d.label)}</span>
                    ${period ? `<span class="text-muted small">${period}</span>` : ''}
                    <a href="${link}" class="small">${ref}</a>
                </div>
            `);
        }
    });
}

// ============================================================
// ADDRESS MANAGEMENT - REUSABLE FUNCTIONS
// ============================================================

/**
 * Address types configuration - centralized mapping for easy maintenance
 */
const ADDRESS_TYPES = {
    permanent: {
        province: 'custom_permanent_address_province',
        commune: 'custom_permanent_address_commune',
        village: 'custom_permanent_address_village',
        full: 'custom_permanent_address_full'
    },
    current: {
        province: 'custom_current_address_province',
        commune: 'custom_current_address_commune',
        village: 'custom_current_address_village',
        full: 'custom_current_address_full'
    },
    // 🚧 TẠM TẮT 21/08/2026 — field quê quán đã bị gỡ khỏi Employee.
    //    🔴 Đây là chỗ BẮT BUỘC phải comment: `load_province_options` và `before_save` duyệt
    //    Object.keys(ADDRESS_TYPES) rồi gọi set_df_property lên từng field. Để lại là gọi lên
    //    field không tồn tại. Bỏ comment cùng lúc với việc khai lại 4 field kia.
    // place_of_origin: {
    //     province: 'custom_place_of_origin_address_province',
    //     commune: 'custom_place_of_origin_address_commune',
    //     village: 'custom_place_of_origin_address_village',
    //     full: 'custom_place_of_origin_address_full'
    // }
};

/**
 * Handle province change - load communes and build address
 * @param {object} frm - Form object
 * @param {string} address_type - 'permanent', 'current', or 'place_of_origin'
 */
function handle_province_change(frm, address_type) {
    const fields = ADDRESS_TYPES[address_type];
    const province_value = frm.doc[fields.province];

    if (province_value) {
        // Clear commune value
        frm.set_value(fields.commune, '');
        // Load new commune options
        load_commune_options_for_type(frm, address_type, province_value);
    } else {
        // If province is cleared, clear commune and its options
        frm.set_value(fields.commune, '');
        frm.set_df_property(fields.commune, 'options', []);
    }

    // Build full address
    build_address_full_for_type(frm, address_type);
}

/**
 * Ô tiếng Anh tương ứng của mỗi loại địa chỉ. Đây là field LÕI của Employee, không phải custom.
 * Không có 'place_of_origin' — quê quán không có ô tiếng Anh nào.
 */
const ENGLISH_ADDRESS_FIELD = {
    permanent: 'permanent_address',
    current: 'current_address'
};

/**
 * Dịch địa chỉ sang tiếng Anh và ghi vào ô lõi tương ứng.
 *
 * Chỉ chạy khi người dùng vừa SỬA một ô địa chỉ tiếng Việt trên form. Không chạy lúc mở hồ sơ:
 * địa chỉ tiếng Anh có thể được nhập thẳng bằng Data Import theo đúng bản dịch tay của HR, dịch
 * đè lên là xoá mất công sức đó. Server cũng chặn ở `sync_english_addresses` với cùng lý do.
 *
 * Bản tiếng Anh này in lên HỢP ĐỒNG LAO ĐỘNG, nên phải thấy kết quả ngay trước khi lưu.
 */
function translate_address_to_english(frm, address_type) {
    const target = ENGLISH_ADDRESS_FIELD[address_type];
    if (!target) return;

    const fields = ADDRESS_TYPES[address_type];
    frappe.call({
        method: 'customize_erpnext.overrides.employee.employee_address.translate_address',
        args: {
            village: frm.doc[fields.village] || '',
            commune: frm.doc[fields.commune] || '',
            province: frm.doc[fields.province] || ''
        },
        callback: function (r) {
            if (r.message !== undefined) frm.set_value(target, r.message);
        }
    });
}

/**
 * Build full address for a specific address type
 * @param {object} frm - Form object
 * @param {string} address_type - 'permanent', 'current', or 'place_of_origin'
 */
function build_address_full_for_type(frm, address_type) {
    const fields = ADDRESS_TYPES[address_type];
    let address_parts = [];

    // Add village if exists
    if (frm.doc[fields.village]) {
        address_parts.push(frm.doc[fields.village]);
    }

    // Add commune if exists
    if (frm.doc[fields.commune]) {
        address_parts.push(frm.doc[fields.commune]);
    }

    // Add province if exists
    if (frm.doc[fields.province]) {
        address_parts.push(frm.doc[fields.province]);
    }

    // Set full address
    frm.set_value(fields.full, address_parts.join(', '));
}

/**
 * Copy address from one type to another
 * @param {object} frm - Form object
 * @param {string} from_type - Source address type
 * @param {string} to_type - Target address type
 */
function copy_address(frm, from_type, to_type) {
    const from_fields = ADDRESS_TYPES[from_type];
    const to_fields = ADDRESS_TYPES[to_type];

    // Copy all address fields
    frm.set_value(to_fields.village, frm.doc[from_fields.village]);
    frm.set_value(to_fields.commune, frm.doc[from_fields.commune]);
    frm.set_value(to_fields.province, frm.doc[from_fields.province]);

    // Load communes for the copied province
    if (frm.doc[from_fields.province]) {
        load_commune_options_for_type(frm, to_type, frm.doc[from_fields.province]);
    }

    // Build full address
    build_address_full_for_type(frm, to_type);
}
// Legacy sync dialog functions removed - now using shared_fingerprint_sync.js
// Maternity Tracking child table events removed - now managed by Employee Maternity doctype

// ============================================================
// ADDRESS SELECTION FUNCTIONS - PROVINCE & COMMUNE
// ============================================================

// Province name → code lookup, populated once on form load
const _province_code_map = {};

/**
 * Load province options using the vn_address DB API (consistent with employee-self-update-info).
 * Stores province name (name) in the field; keeps code in _province_code_map for ward lookup.
 */
function load_province_options(frm) {
    frappe.call({
        method: 'customize_erpnext.api.vn_address.vn_address_api.get_provinces',
        callback: function (r) {
            if (!r.message || !r.message.length) return;

            const province_names = [''].concat(r.message.map(p => {
                _province_code_map[p.name] = p.code;
                return p.name;
            }));

            const DEFAULT_PROVINCE = 'Tỉnh Quảng Ngãi';

            Object.keys(ADDRESS_TYPES).forEach(address_type => {
                const fields = ADDRESS_TYPES[address_type];
                frm.set_df_property(fields.province, 'options', province_names);

                if (frm.doc[fields.province]) {
                    // Existing record — load communes for saved province
                    load_commune_options_for_type(frm, address_type, frm.doc[fields.province]);
                } else if (frm.is_new()) {
                    // New employee — default all address provinces to Quảng Ngãi
                    frm.set_value(fields.province, DEFAULT_PROVINCE);
                    load_commune_options_for_type(frm, address_type, DEFAULT_PROVINCE);
                }
            });
        }
    });
}

/**
 * Load ward (commune/phường-xã) options for the selected province
 * (vn_address DB API: get_wards by province code).
 * Note: the Employee field is named `*_commune`, which maps to a "ward" in the API.
 * @param {object} frm
 * @param {string} address_type - 'permanent' | 'current' | 'place_of_origin'
 * @param {string} province_name - Province display name (name), used to look up code
 */
function load_commune_options_for_type(frm, address_type, province_name) {
    if (!province_name || !ADDRESS_TYPES[address_type]) return;

    const province_code = _province_code_map[province_name];
    if (!province_code) return;

    const fields = ADDRESS_TYPES[address_type];

    frappe.call({
        method: 'customize_erpnext.api.vn_address.vn_address_api.get_wards',
        args: { province_code: province_code },
        callback: function (r) {
            const ward_names = [''].concat((r.message || []).map(d => d.name));
            frm.set_df_property(fields.commune, 'options', ward_names);
        }
    });
}


// ---------------------------------------------------------------------------
// Reason for Leaving — hai Link nối tầng
//
// custom_reason_for_leaving_group    -> Resignation Reason Group
// custom_reason_for_leaving_group_2  -> Resignation Reason Group 2 (lọc theo nhóm)
// reason_for_leaving                 -> Small Text, diễn giải thêm
//
// Trước đây là hai Select có `options` rỗng, danh sách bơm vào lúc chạy từ
// employee_reason_for_leaving.json bằng ~95 dòng JS. HR muốn tự thêm/bớt nên
// danh mục đã chuyển thành DocType — cả file JSON lẫn khối JS đó đã bị xoá.
// Xem patches/add_resignation_reason_catalogue.py.
// ---------------------------------------------------------------------------

frappe.ui.form.on('Employee', {
    setup: function (frm) {
        frm.set_query('custom_reason_for_leaving_group', () => ({
            filters: { is_active: 1 },
        }));

        // Lọc HIỂN THỊ. Cặp nhóm/lý do lệch nhau qua Data Import hay API thì
        // không có gì ở đây chặn được — chốt chặn thật nằm ở
        // ResignationApplication.validate_reason() cho đơn nghỉ việc.
        frm.set_query('custom_reason_for_leaving_group_2', () => ({
            filters: {
                reason_for_leaving_group: frm.doc.custom_reason_for_leaving_group || '',
                is_active: 1,
            },
        }));
    },

    custom_reason_for_leaving_group: function (frm) {
        // Đổi nhóm thì lý do cũ gần như chắc chắn không còn thuộc nhóm mới.
        if (frm.doc.custom_reason_for_leaving_group_2) {
            frm.set_value('custom_reason_for_leaving_group_2', '');
        }
    },
});

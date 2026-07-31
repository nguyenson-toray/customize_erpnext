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
        // employee_name: editable; first/middle/last_name: read-only, auto-split from employee_name
        frm.set_df_property('employee_name', 'read_only', 0);
        frm.set_df_property('first_name', 'read_only', 1);
        frm.set_df_property('last_name', 'read_only', 1);
        frm.set_df_property('middle_name', 'read_only', 1);

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
    },

    employee_name: function (frm) {
        split_employee_name(frm);
    },

    custom_copy_permanent_address_to_other_adress: function (frm) {
        if (frm.doc.custom_copy_permanent_address_to_other_adress) {
            console.log('Copy permanent address to current and origin address');
            copy_address(frm, 'permanent', 'current');
            copy_address(frm, 'permanent', 'place_of_origin');
        }
    },
    // Current Address handlers
    custom_current_address_village: function (frm) {
        build_address_full_for_type(frm, 'current');
    },
    custom_current_address_commune: function (frm) {
        build_address_full_for_type(frm, 'current');
    },
    custom_current_address_province: function (frm) {
        handle_province_change(frm, 'current');
    },

    // Permanent Address handlers
    custom_permanent_address_village: function (frm) {
        build_address_full_for_type(frm, 'permanent');
    },
    custom_permanent_address_commune: function (frm) {
        build_address_full_for_type(frm, 'permanent');
    },
    custom_permanent_address_province: function (frm) {
        handle_province_change(frm, 'permanent');
    },

    // Place of Origin Address handlers
    custom_place_of_origin_address_village: function (frm) {
        build_address_full_for_type(frm, 'place_of_origin');
    },
    custom_place_of_origin_address_commune: function (frm) {
        build_address_full_for_type(frm, 'place_of_origin');
    },
    custom_place_of_origin_address_province: function (frm) {
        handle_province_change(frm, 'place_of_origin');
    },

    before_save: function (frm) {
        // Ensure employee code follows TIQN-XXXX format
        if (frm.doc.employee && !frm.doc.employee.startsWith('TIQN-') && !frm.doc.employee.startsWith('TT-') ) {
            frappe.msgprint(__('Employee code should follow TIQN-XXXX or TT-XXXX format'));
            frappe.validated = false;
            return;
        }

        // Sync first/middle/last_name từ employee_name trước khi lưu
        if (frm.doc.employee_name) {
            const _parts = frm.doc.employee_name.trim().split(/\s+/).filter(Boolean);
            frm.doc.first_name = _parts[0] || '';
            frm.doc.last_name = _parts.length >= 2 ? _parts[_parts.length - 1] : '';
            frm.doc.middle_name = _parts.length >= 3 ? _parts.slice(1, -1).join(' ') : '';
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
        build_address_full_for_type(frm, 'place_of_origin');
    },
});

// ============================================================
// EMPLOYEE NAME SPLITTING FUNCTIONS
// ============================================================

/**
 * Tách employee_name → first_name, middle_name, last_name rồi điền vào form
 * VD: "Nguyễn Văn An" → first="Nguyễn", middle="Văn", last="An"
 */
function split_employee_name(frm) {
    const fullName = (frm.doc.employee_name || '').trim();
    const parts = fullName.split(/\s+/).filter(Boolean);
    let first = '', mid = '', last = '';
    if (parts.length === 1) {
        first = parts[0];
    } else if (parts.length >= 2) {
        first = parts[0];
        last = parts[parts.length - 1];
        mid = parts.slice(1, -1).join(' ');
    }
    frm.set_value('first_name', first);
    frm.set_value('middle_name', mid);
    frm.set_value('last_name', last);
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
    place_of_origin: {
        province: 'custom_place_of_origin_address_province',
        commune: 'custom_place_of_origin_address_commune',
        village: 'custom_place_of_origin_address_village',
        full: 'custom_place_of_origin_address_full'
    }
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

            const province_names = r.message.map(p => {
                _province_code_map[p.name] = p.code;
                return p.name;
            });

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
            const ward_names = (r.message || []).map(d => d.name);
            frm.set_df_property(fields.commune, 'options', ward_names);
        }
    });
}


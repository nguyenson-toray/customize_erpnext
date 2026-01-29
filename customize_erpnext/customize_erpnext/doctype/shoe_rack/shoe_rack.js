// shoe_rack.js
// Client Script for Shoe Rack Form
//  Auto-update status
//  Gender validation (RACK only)
//  Smart filters
//  UI improvements
//  NO manual field formatting - let Frappe handle Link fields

frappe.ui.form.on('Shoe Rack', {
    refresh: function(frm) {
        // Auto-calculate and update status
        if (!frm.is_new()) {
            update_status_display(frm);
        }
        
        // Add custom buttons
        add_custom_buttons(frm);
        
        // Set field properties
        set_field_properties(frm);
        
        // Show rack info
        show_rack_info(frm);
    },
    
    rack_type: function(frm) {
        // Auto-set naming series
        if (frm.is_new() && frm.doc.rack_type) {
            const series_map = {
                'Standard Employee': 'RACK-',
                'Guest': 'G-',
                'Japanese Employee': 'J-',
                'External Personnel': 'A-'
            };
            
            frm.set_value('naming_series', series_map[frm.doc.rack_type]);
            
            // Auto-set user_type
            if (['Standard Employee', 'Japanese Employee'].includes(frm.doc.rack_type)) {
                frm.set_value('user_type', 'Employee');
            } else {
                frm.set_value('user_type', 'External');
            }
            
            // Show info about gender validation
            if (frm.doc.rack_type === 'Standard Employee') {
                frappe.show_alert({
                    message: __('RACK type: Gender validation enabled'),
                    indicator: 'blue'
                }, 3);
            } else {
                frappe.show_alert({
                    message: __('Guest/Japanese/External: Mixed gender allowed'),
                    indicator: 'green'
                }, 3);
            }
        }
        
        // Clear incompatible fields
        clear_incompatible_fields(frm);
    },
    
    user_type: function(frm) {
        // Clear incompatible assignments
        clear_incompatible_fields(frm);
    },
    
    compartments: function(frm) {
        // Clear compartment 2 if changed to 1
        if (frm.doc.compartments === '1') {
            frm.set_value('compartment_2_employee', null);
            frm.set_value('compartment_2_external_personnel', null);
        }
        
        // Update status
        update_status_auto(frm);
    },
    
    gender: function(frm) {
        // Warn if changing gender with assignments
        if (has_assignments(frm)) {
            frappe.msgprint({
                title: __('Warning'),
                indicator: 'orange',
                message: __('This rack has personnel assigned. Changing gender may cause validation errors.')
            });
        }
    },
    
    // Compartment 1 - Employee
    compartment_1_employee: function(frm) {
        update_status_auto(frm);
    },
    
    // Compartment 2 - Employee
    compartment_2_employee: function(frm) {
        update_status_auto(frm);
    },
    
    // Compartment 1 - External
    compartment_1_external_personnel: function(frm) {
        update_status_auto(frm);
    },
    
    // Compartment 2 - External
    compartment_2_external_personnel: function(frm) {
        update_status_auto(frm);
    }
});

// ==================== CUSTOM BUTTONS ====================

function add_custom_buttons(frm) {
    if (frm.is_new()) return;
    
    // Refresh Status button
    frm.add_custom_button(__('Refresh Status'), function() {
        update_status_auto(frm);
        frappe.show_alert({
            message: __('Status refreshed'),
            indicator: 'green'
        }, 2);
    }, __('Actions'));
    
    // Release All button
    if (has_assignments(frm)) {
        frm.add_custom_button(__('Release All'), function() {
            frappe.confirm(
                __('Release all compartments?'),
                function() {
                    frm.set_value('compartment_1_employee', null);
                    frm.set_value('compartment_2_employee', null);
                    frm.set_value('compartment_1_external_personnel', null);
                    frm.set_value('compartment_2_external_personnel', null);
                    frm.save();
                }
            );
        }, __('Actions'));
    }
    
    // Find Personnel button
    frm.add_custom_button(__('Find Personnel'), function() {
        show_personnel_finder(frm);
    }, __('Actions'));
}

// ==================== FIELD PROPERTIES ====================

function set_field_properties(frm) {
    // Make status read-only
    frm.set_df_property('status', 'read_only', 1);
    
    // Show/hide compartment 2 based on compartments
    const show_comp2 = frm.doc.compartments === '2';
    frm.toggle_display('compartment_2_employee', show_comp2 && frm.doc.user_type === 'Employee');
    frm.toggle_display('compartment_2_external_personnel', show_comp2 && frm.doc.user_type === 'External');
    
    // Show appropriate personnel fields based on user_type
    frm.toggle_display('compartment_1_employee', frm.doc.user_type === 'Employee');
    frm.toggle_display('compartment_2_employee', frm.doc.user_type === 'Employee' && show_comp2);
    frm.toggle_display('compartment_1_external_personnel', frm.doc.user_type === 'External');
    frm.toggle_display('compartment_2_external_personnel', frm.doc.user_type === 'External' && show_comp2);
    
    // Set filters
    set_personnel_filters(frm);
}

function set_personnel_filters(frm) {
    if (!frm.doc.gender) return;
    
    // Employee filters
    const employee_filter = {
        'status': 'Active'
    };
    
    // Only RACK validates gender
    if (frm.doc.rack_type === 'Standard Employee' && frm.doc.gender) {
        employee_filter['gender'] = frm.doc.gender;
    }
    
    frm.set_query('compartment_1_employee', function() {
        return { 
            filters: employee_filter,
            page_length: 20
        };
    });
    
    frm.set_query('compartment_2_employee', function() {
        return { 
            filters: employee_filter,
            page_length: 20
        };
    });
    
    // External Personnel filters - check if status field exists
    frappe.model.with_doctype('External Personnel', function() {
        const meta = frappe.get_meta('External Personnel');
        const has_status = meta.fields.find(f => f.fieldname === 'status');
        
        const external_filter = {};
        
        // Only add status filter if field exists
        if (has_status) {
            external_filter['status'] = 'Active';
        }
        
        // Set custom query with formatted display
        frm.set_query('compartment_1_external_personnel', function() {
            return { 
                query: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.external_personnel_query',
                filters: external_filter
            };
        });
        
        frm.set_query('compartment_2_external_personnel', function() {
            return { 
                query: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.external_personnel_query',
                filters: external_filter
            };
        });
    });
}

// ==================== STATUS UPDATE ====================

function update_status_auto(frm) {
    if (frm.is_new()) return;
    
    let has_comp1 = frm.doc.compartment_1_employee || frm.doc.compartment_1_external_personnel;
    let has_comp2 = frm.doc.compartment_2_employee || frm.doc.compartment_2_external_personnel;
    
    let new_status;
    
    if (frm.doc.compartments === '1') {
        new_status = has_comp1 ? '1/1' : '0/1';
    } else {
        let used = (has_comp1 ? 1 : 0) + (has_comp2 ? 1 : 0);
        new_status = used + '/2';
    }
    
    if (frm.doc.status !== new_status) {
        frm.set_value('status', new_status);
    }
}

function update_status_display(frm) {
    // Update visual status indicator
    const status = frm.doc.status;
    let color, message;
    
    if (status === '0/1' || status === '0/2') {
        color = 'green';
        message = 'Empty';
    } else if (status === '1/1' || status === '2/2') {
        color = 'red';
        message = 'Full';
    } else {
        color = 'orange';
        message = 'Partially Occupied';
    }
    
    frm.dashboard.add_indicator(__('Status: {0}', [message]), color);
}

// ==================== HELPERS ====================

function clear_incompatible_fields(frm) {
    if (frm.doc.user_type === 'Employee') {
        frm.set_value('compartment_1_external_personnel', null);
        frm.set_value('compartment_2_external_personnel', null);
    } else if (frm.doc.user_type === 'External') {
        frm.set_value('compartment_1_employee', null);
        frm.set_value('compartment_2_employee', null);
    }
    
    set_field_properties(frm);
}

function has_assignments(frm) {
    return !!(frm.doc.compartment_1_employee || 
              frm.doc.compartment_2_employee ||
              frm.doc.compartment_1_external_personnel ||
              frm.doc.compartment_2_external_personnel);
}

// ==================== RACK INFO ====================

function show_rack_info(frm) {
    if (frm.is_new()) return;
    
    let html = '<div style="padding: 10px; background: #f8f9fa; border-radius: 5px; margin-top: 10px;">';
    html += '<strong>📊 Rack Information</strong><br><br>';
    
    // Display name
    if (frm.doc.rack_display_name) {
        html += `<strong>Rack Name:</strong> ${frm.doc.rack_display_name}<br>`;
    }
    
    // Series info
    const series_map = {
        'RACK-': 'Standard Employee (1, 2, 3...)',
        'J-': 'Japanese Employee (J1, J2, J3...)',
        'G-': 'Guest (G1, G2, G3...)',
        'A-': 'External Personnel (A1, A2, A3...)'
    };
    
    const series_display = series_map[frm.doc.naming_series] || frm.doc.naming_series;
    html += `<strong>Series:</strong> ${series_display}<br>`;
    
    // Rack number
    if (frm.doc.name) {
        const match = frm.doc.name.match(/(\d+)$/);
        if (match) {
            html += `<strong>Number:</strong> ${parseInt(match[1])}<br>`;
        }
    }
    
    // Gender validation info
    if (frm.doc.rack_type === 'Standard Employee') {
        html += '<strong>Validation:</strong> <span style="color: orange;">Gender validated </span><br>';
    } else {
        html += '<strong>Validation:</strong> <span style="color: green;">Mixed gender OK </span><br>';
    }
    
    html += '</div>';
    
    frm.set_df_property('rack_info_html', 'options', html);
}

// ==================== PERSONNEL FINDER ====================

function show_personnel_finder(frm) {
    const d = new frappe.ui.Dialog({
        title: __('Find Personnel'),
        fields: [
            {
                fieldname: 'personnel_type',
                label: __('Personnel Type'),
                fieldtype: 'Select',
                options: 'Employee\nExternal Personnel',
                reqd: 1,
                default: frm.doc.user_type === 'Employee' ? 'Employee' : 'External Personnel'
            },
            {
                fieldname: 'personnel_id',
                label: __('Personnel ID or Name'),
                fieldtype: 'Data',
                reqd: 1
            }
        ],
        primary_action_label: __('Find'),
        primary_action: function(values) {
            find_personnel_rack(values.personnel_type, values.personnel_id, d);
        }
    });
    
    d.show();
}

function find_personnel_rack(personnel_type, personnel_id, dialog) {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.find_rack_for_personnel',
        args: {
            personnel_id: personnel_id,
            personnel_doctype: personnel_type
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                const rack = r.message[0];
                
                frappe.msgprint({
                    title: __('Found Rack'),
                    message: __('Personnel is assigned to rack <a href="/app/shoe-rack/{0}">{0}</a>, Compartment {1}',
                        [rack.rack_name, rack.compartment]),
                    indicator: 'green'
                });
                
                dialog.hide();
            } else {
                frappe.msgprint({
                    title: __('Not Found'),
                    message: __('No rack assignment found for this personnel'),
                    indicator: 'yellow'
                });
            }
        }
    });
}

// ==================== KEYBOARD SHORTCUTS ====================

$(document).on('keydown', function(e) {
    const frm = cur_frm;
    if (!frm || frm.doctype !== 'Shoe Rack') return;
    
    // Ctrl + Shift + R: Refresh status
    if (e.ctrlKey && e.shiftKey && e.keyCode === 82) {
        e.preventDefault();
        update_status_auto(frm);
        frappe.show_alert(__('Status refreshed'), 2);
    }
    
    // Ctrl + Shift + C: Clear all assignments
    if (e.ctrlKey && e.shiftKey && e.keyCode === 67) {
        e.preventDefault();
        if (has_assignments(frm)) {
            frappe.confirm(
                __('Clear all assignments?'),
                function() {
                    frm.set_value('compartment_1_employee', null);
                    frm.set_value('compartment_2_employee', null);
                    frm.set_value('compartment_1_external_personnel', null);
                    frm.set_value('compartment_2_external_personnel', null);
                }
            );
        }
    }
});

// Console log for debugging
console.log('Shoe Rack Client Script Loaded ');
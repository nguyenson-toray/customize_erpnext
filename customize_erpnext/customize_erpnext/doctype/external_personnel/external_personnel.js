// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

// Client Script for External Personnel - Auto-set naming series

frappe.ui.form.on('External Personnel', {
    refresh: function(frm) {
        // Set series on form load
        if (frm.doc.personnel_type && !frm.doc.naming_series) {
            set_naming_series(frm);
        }
    },
    
    personnel_type: function(frm) {
        // Auto-set naming series when personnel type changes
        set_naming_series(frm);
    }
});

function set_naming_series(frm) {
    /**
     * Auto-set naming series based on personnel type
     * 
     * Mapping:
     * Guest → GUEST-.####
     * Visitor → GUEST-.####
     * Vendor → VENDOR-.####
     * Cleaner → VENDOR-.####
     * Contractor → CONTRACTOR-.####
     * Temporary Staff → CONTRACTOR-.####
     */
    
    if (!frm.doc.personnel_type) return;
    
    let series_map = {
        'Guest': 'GUEST-.####',
        'Visitor': 'GUEST-.####',
        'Vendor': 'VENDOR-.####',
        'Cleaner': 'VENDOR-.####',
        'Contractor': 'CONTRACTOR-.####',
        'Temporary Staff': 'CONTRACTOR-.####'
    };
    
    let series = series_map[frm.doc.personnel_type];
    
    if (series && frm.doc.naming_series !== series) {
        frm.set_value('naming_series', series);
        
        // Show helpful message
        let series_display = series.replace('-.####', '');
        frappe.show_alert({
            message: `Series: ${series_display} (${frm.doc.personnel_type})`,
            indicator: 'blue'
        }, 3);
    }
}
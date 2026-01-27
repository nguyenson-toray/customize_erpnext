# Copyright (c) 2025, IT Team - TIQN and contributors
# External Personnel - Auto-set naming series based on type

# external_personnel.py

import frappe
from frappe import _
from frappe.model.document import Document

class ExternalPersonnel(Document):
    pass

def validate(doc, method):
    """Validate External Personnel before save"""
    
    # Auto-set naming series based on personnel type
    if doc.personnel_type and not doc.naming_series:
        series_map = {
            'Guest': 'GUEST-.####',
            'Visitor': 'GUEST-.####',
            'Vendor': 'VENDOR-.####',
            'Cleaner': 'VENDOR-.####',
            'Contractor': 'CONTRACTOR-.####',
            'Temporary Staff': 'CONTRACTOR-.####'
        }
        doc.naming_series = series_map.get(doc.personnel_type, 'GUEST-.####')
    
    # Validate required fields
    if not doc.full_name:
        frappe.throw(_("Full Name is required"))
    
    if not doc.gender:
        frappe.throw(_("Gender is required"))

def before_save(doc, method):
    """Before save hook - ensure naming series is set"""
    
    # Force update naming series if personnel type changes
    if doc.personnel_type:
        series_map = {
            'Guest': 'GUEST-.####',
            'Visitor': 'GUEST-.####',
            'Vendor': 'VENDOR-.####',
            'Cleaner': 'VENDOR-.####',
            'Contractor': 'CONTRACTOR-.####',
            'Temporary Staff': 'CONTRACTOR-.####'
        }
        correct_series = series_map.get(doc.personnel_type, 'GUEST-.####')
        
        # Update if different
        if doc.naming_series != correct_series:
            doc.naming_series = correct_series

@frappe.whitelist()
def get_series_for_type(personnel_type):
    """Get naming series for a personnel type"""
    series_map = {
        'Guest': 'GUEST-.####',
        'Visitor': 'GUEST-.####',
        'Vendor': 'VENDOR-.####',
        'Cleaner': 'VENDOR-.####',
        'Contractor': 'CONTRACTOR-.####',
        'Temporary Staff': 'CONTRACTOR-.####'
    }
    return series_map.get(personnel_type, 'GUEST-.####')
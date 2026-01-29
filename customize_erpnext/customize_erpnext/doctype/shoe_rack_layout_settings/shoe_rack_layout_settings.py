# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class ShoeRackLayoutSettings(Document):
    """
    Single DocType to store shoe rack layout configuration
    Stores layout data as JSON string
    """
    pass

def on_update(doc, method):
    """Hook called after document is updated"""
    # Update metadata
    doc.last_modified_by = frappe.session.user
    doc.last_modified_date = frappe.utils.now()
    doc.save(ignore_permissions=True)
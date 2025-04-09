# custom_work_order.py
import frappe
from frappe.model.document import Document
from frappe.utils import flt

@frappe.whitelist()
def start_wo_without_transfer_material(doc_name):
    doc = frappe.get_doc('Work Order', doc_name)
    if doc.skip_transfer and doc.docstatus == 1 and doc.status == "Not Started":
        doc.db_set('status', 'In Process')
        return True
    return False

 

@frappe.whitelist()
def update_work_order_operation(job_card):
    """Update Work Order Operation's completed quantity from Job Card"""
    if isinstance(job_card, str):
        job_card = frappe.get_doc('Job Card', job_card)
        
    if not job_card.work_order or not job_card.operation:
        return

    # Get current completed qty from Job Card
    completed_qty = job_card.total_completed_qty or 0
    process_loss_qty = job_card.process_loss_qty or 0
    
    # Update Work Order Operation
    frappe.db.sql("""
        UPDATE `tabWork Order Operation`
        SET completed_qty = %s, process_loss_qty = %s
        WHERE parent = %s AND operation = %s
    """, (completed_qty, process_loss_qty, job_card.work_order, job_card.operation))

    # Update modified timestamp on Work Order
    frappe.db.sql("""
        UPDATE `tabWork Order`
        SET modified = NOW()
        WHERE name = %s
    """, job_card.work_order)

    frappe.db.commit()
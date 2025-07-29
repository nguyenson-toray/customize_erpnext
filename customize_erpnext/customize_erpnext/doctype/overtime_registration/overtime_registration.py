# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_time, time_diff_in_hours
from frappe import _

class OvertimeRegistration(Document):
    def validate(self):
        self.validate_duplicate_employees()
        self.validate_conflicting_ot_requests()
        self.calculate_totals_and_apply_reason()
    
    def before_save(self):
        self.validate_duplicate_employees()
        self.validate_conflicting_ot_requests()
    
    def before_insert(self):
        self.validate_duplicate_employees()
        self.validate_conflicting_ot_requests()

    def validate_duplicate_employees(self):
        """Prevent duplicate or overlapping overtime entries within the same form"""
        
        entries = []
        
        for d in self.ot_employees:
            if not all([d.employee, d.date, d.get("from"), d.get("to")]):
                frappe.throw(_("Row #{idx}: Employee, Date, From Time, and To Time are required.").format(idx=d.idx))
            
            entries.append({
                'idx': d.idx,
                'employee': d.employee,
                'employee_name': d.employee_name,
                'date': d.date,
                'from': d.get("from"),
                'to': d.get("to")
            })
        
        # Check for duplicates and overlaps
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                entry1 = entries[i]
                entry2 = entries[j]
                
                # Same employee and date
                if entry1['employee'] == entry2['employee'] and entry1['date'] == entry2['date']:
                    # Check for exact match or time overlap
                    if times_overlap(entry1['from'], entry1['to'], entry2['from'], entry2['to']):
                        frappe.throw(_("Row #{idx1} and Row #{idx2}: Overlapping overtime entries for employee {employee_name} on {date}. Entry 1: {from1}-{to1}, Entry 2: {from2}-{to2}").format(
                            idx1=entry1['idx'],
                            idx2=entry2['idx'],
                            employee_name=frappe.bold(entry1['employee_name']),
                            date=frappe.bold(entry1['date']),
                            from1=entry1['from'],
                            to1=entry1['to'],
                            from2=entry2['from'],
                            to2=entry2['to']
                        ))

    def validate_conflicting_ot_requests(self):
        """Prevent conflicts with existing submitted overtime registrations"""
        if not self.ot_employees:
            return

        for d in self.ot_employees:
            from_time = d.get("from")
            to_time = d.get("to")

            existing_entries = frappe.db.sql("""
                SELECT child.parent, child.from, child.to
                FROM `tabOvertime Registration Detail` as child
                JOIN `tabOvertime Registration` as parent ON child.parent = parent.name
                WHERE child.employee = %(employee)s
                AND child.date = %(date)s
                AND parent.name != %(current_doc_name)s
                AND parent.docstatus = 1
            """, {
                "employee": d.employee,
                "date": d.date,
                "current_doc_name": self.name or "new"
            }, as_dict=1)

            for existing in existing_entries:
                if times_overlap(from_time, to_time, existing.get("from"), existing.get("to")):
                    conflicting_doc = existing.get("parent")
                    doc_link = frappe.get_desk_link("Overtime Registration", conflicting_doc)
                    frappe.throw(_("Row #{idx}: Overlapping overtime entry for {employee_name} on {date}. Current: {from_time}-{to_time}, Existing: {existing_from}-{existing_to} in {doc_link}.").format(
                        idx=d.idx,
                        employee_name=frappe.bold(d.employee_name),
                        date=frappe.bold(d.date),
                        from_time=from_time,
                        to_time=to_time,
                        existing_from=existing.get("from"),
                        existing_to=existing.get("to"),
                        doc_link=doc_link
                    ))

    def calculate_totals_and_apply_reason(self):
        """Manage general reason field and calculate totals"""
        if not self.ot_employees:
            self.total_employees = 0
            self.total_hours = 0
            return

        distinct_employees = set()
        total_hours = 0.0
        child_reasons = set()

        # First pass: calculate totals and gather unique, non-empty child reasons
        for d in self.ot_employees:
            if d.employee:
                distinct_employees.add(d.employee)

            if d.get("from") and d.get("to"):
                total_hours += time_diff_in_hours(d.to, d.get("from"))
            
            if d.reason:
                child_reasons.add(d.reason.strip())

        # Update totals
        self.total_employees = len(distinct_employees)
        self.total_hours = total_hours

        # If general reason is empty, populate it from unique child reasons
        if not self.reason_general and child_reasons:
            self.reason_general = ", ".join(sorted(list(child_reasons)))

        # If a general reason now exists (either provided by user or generated),
        # apply it to any child rows that have an empty reason.
        if self.reason_general:
            for d in self.ot_employees:
                if not d.reason:
                    d.reason = self.reason_general

@frappe.whitelist()
def check_overtime_conflicts(entries, current_doc_name="new"):
    """
    Server method to check conflicts with submitted overtime registrations
    Called from JavaScript validation
    """
    import json
    if isinstance(entries, str):
        entries = json.loads(entries)
    
    conflicts = []
    
    for entry in entries:
        # Query for existing overtime registrations for same employee and date
        existing_entries = frappe.db.sql("""
            SELECT child.parent, child.from, child.to, child.employee_name
            FROM `tabOvertime Registration Detail` as child
            JOIN `tabOvertime Registration` as parent ON child.parent = parent.name
            WHERE child.employee = %(employee)s
            AND child.date = %(date)s
            AND parent.name != %(current_doc_name)s
            AND parent.docstatus = 1
        """, {
            "employee": entry["employee"],
            "date": entry["date"],
            "current_doc_name": current_doc_name
        }, as_dict=1)
        
        # Check for overlaps
        for existing in existing_entries:
            if times_overlap(entry["from"], entry["to"], existing["from"], existing["to"]):
                conflicts.append({
                    "idx": entry["idx"],
                    "employee_name": entry["employee_name"],
                    "date": entry["date"],
                    "current_from": entry["from"],
                    "current_to": entry["to"],
                    "existing_from": existing["from"],
                    "existing_to": existing["to"],
                    "existing_doc": existing["parent"]
                })
    
    return conflicts

def times_overlap(from1, to1, from2, to2):
    """
    Check if two time ranges overlap
    Adjacent periods (where one ends exactly when another begins) are NOT overlapping
    """
    try:
        # Convert time strings to time objects for comparison
        time1_start = get_time(from1)
        time1_end = get_time(to1)
        time2_start = get_time(from2)
        time2_end = get_time(to2)
        
        # Check for overlap: start1 < end2 && start2 < end1
        condition1 = time1_start < time2_end
        condition2 = time2_start < time1_end
        overlap = condition1 and condition2
        
        return overlap
    except Exception:
        # If there's any error in time conversion, assume no overlap
        return False
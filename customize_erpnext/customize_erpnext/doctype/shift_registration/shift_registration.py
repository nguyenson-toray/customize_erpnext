# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time, getdate


class ShiftRegistration(Document):
    def validate(self):
        self.validate_required_fields()
        self.validate_duplicate_entries()
        self.validate_conflicting_shift_requests()
        self.calculate_totals()
    
    def before_save(self):
        self.validate_duplicate_entries()
        self.validate_conflicting_shift_requests()
    
    def before_insert(self):
        self.validate_duplicate_entries()
        self.validate_conflicting_shift_requests()

    def validate_required_fields(self):
        """Validate required fields in child table"""
        for d in self.employees_list:
            missing_fields = []
            if not d.employee:
                missing_fields.append("Employee")
            if not d.begin_date:
                missing_fields.append("Begin Date") 
            if not d.end_date:
                missing_fields.append("End Date")
            if not d.begin_time:
                missing_fields.append("Begin Time")
            if not d.end_time:
                missing_fields.append("End Time")
                
            if missing_fields:
                frappe.throw(_("Row #{idx}: {fields} are required.").format(
                    idx=d.idx, 
                    fields=", ".join(missing_fields)
                ))

    def validate_duplicate_entries(self):
        """Prevent duplicate or overlapping shift entries within the same form"""
        entries = []
        
        for d in self.employees_list:
            # Skip validation if required fields are missing
            if not d.employee or not d.begin_date or not d.end_date or not d.begin_time or not d.end_time:
                continue
            
            entries.append({
                'idx': d.idx,
                'employee': d.employee,
                'employee_name': d.employee_name,
                'begin_date': d.begin_date,
                'end_date': d.end_date,
                'begin_time': d.begin_time,
                'end_time': d.end_time
            })
        
        # Check for duplicates and overlaps
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                entry1 = entries[i]
                entry2 = entries[j]
                
                # Same employee
                if entry1['employee'] == entry2['employee']:
                    # Check for date range overlap and time overlap
                    if dates_overlap(entry1['begin_date'], entry1['end_date'], entry2['begin_date'], entry2['end_date']):
                        if times_overlap(entry1['begin_time'], entry1['end_time'], entry2['begin_time'], entry2['end_time']):
                            frappe.throw(_("Row #{idx1} and Row #{idx2}: Overlapping shift entries for employee {employee_name}. Entry 1: {date1_from}-{date1_to} {time1_from}-{time1_to}, Entry 2: {date2_from}-{date2_to} {time2_from}-{time2_to}").format(
                                idx1=entry1['idx'],
                                idx2=entry2['idx'],
                                employee_name=frappe.bold(entry1['employee_name']),
                                date1_from=entry1['begin_date'],
                                date1_to=entry1['end_date'],
                                time1_from=entry1['begin_time'],
                                time1_to=entry1['end_time'],
                                date2_from=entry2['begin_date'],
                                date2_to=entry2['end_date'],
                                time2_from=entry2['begin_time'],
                                time2_to=entry2['end_time']
                            ))

    def validate_conflicting_shift_requests(self):
        """Prevent conflicts with existing submitted shift registrations"""
        if not self.employees_list:
            return

        for d in self.employees_list:
            if not d.employee or not d.begin_date or not d.end_date or not d.begin_time or not d.end_time:
                continue

            existing_entries = frappe.db.sql("""
                SELECT child.parent, child.begin_date, child.end_date, child.begin_time, child.end_time
                FROM `tabShift Registration Detail` as child
                JOIN `tabShift Registration` as parent ON child.parent = parent.name
                WHERE child.employee = %(employee)s
                AND parent.name != %(current_doc_name)s
                AND parent.docstatus = 1
                AND (
                    (child.begin_date <= %(end_date)s AND child.end_date >= %(begin_date)s)
                )
            """, {
                "employee": d.employee,
                "begin_date": d.begin_date,
                "end_date": d.end_date,
                "current_doc_name": self.name or "new"
            }, as_dict=1)

            for existing in existing_entries:
                # Check if date ranges overlap
                if dates_overlap(d.begin_date, d.end_date, existing.begin_date, existing.end_date):
                    # Check if time ranges overlap
                    if times_overlap(d.begin_time, d.end_time, existing.begin_time, existing.end_time):
                        conflicting_doc = existing.parent
                        doc_link = frappe.get_desk_link("Shift Registration", conflicting_doc)
                        frappe.throw(_("Row #{idx}: Overlapping shift entry for {employee_name} from {begin_date} to {end_date} ({begin_time}-{end_time}). Existing: {existing_begin_date} to {existing_end_date} ({existing_begin_time}-{existing_end_time}) in {doc_link}.").format(
                            idx=d.idx,
                            employee_name=frappe.bold(d.employee_name),
                            begin_date=d.begin_date,
                            end_date=d.end_date,
                            begin_time=d.begin_time,
                            end_time=d.end_time,
                            existing_begin_date=existing.begin_date,
                            existing_end_date=existing.end_date,
                            existing_begin_time=existing.begin_time,
                            existing_end_time=existing.end_time,
                            doc_link=doc_link
                        ))

    def calculate_totals(self):
        """Calculate total employees"""
        if not self.employees_list:
            self.total_employees = 0
            return

        distinct_employees = set()
        for d in self.employees_list:
            if d.employee:
                distinct_employees.add(d.employee)

        self.total_employees = len(distinct_employees)


@frappe.whitelist()
def check_shift_conflicts(entries, current_doc_name="new"):
    """
    Server method to check conflicts with submitted shift registrations
    Called from JavaScript validation
    """
    import json
    if isinstance(entries, str):
        entries = json.loads(entries)
    
    conflicts = []
    
    for entry in entries:
        # Query for existing shift registrations for same employee with overlapping dates
        existing_entries = frappe.db.sql("""
            SELECT child.parent, child.begin_date, child.end_date, child.begin_time, child.end_time, child.employee_name
            FROM `tabShift Registration Detail` as child
            JOIN `tabShift Registration` as parent ON child.parent = parent.name
            WHERE child.employee = %(employee)s
            AND parent.name != %(current_doc_name)s
            AND parent.docstatus = 1
            AND (
                (child.begin_date <= %(end_date)s AND child.end_date >= %(begin_date)s)
            )
        """, {
            "employee": entry["employee"],
            "begin_date": entry["begin_date"],
            "end_date": entry["end_date"],
            "current_doc_name": current_doc_name
        }, as_dict=1)
        
        # Check for overlaps
        for existing in existing_entries:
            # Check if date ranges overlap and time ranges overlap
            if dates_overlap(entry["begin_date"], entry["end_date"], existing.begin_date, existing.end_date):
                if times_overlap(entry["begin_time"], entry["end_time"], existing.begin_time, existing.end_time):
                    conflicts.append({
                        "idx": entry["idx"],
                        "employee_name": entry["employee_name"],
                        "begin_date": entry["begin_date"],
                        "end_date": entry["end_date"],
                        "begin_time": entry["begin_time"],
                        "end_time": entry["end_time"],
                        "existing_begin_date": existing.begin_date,
                        "existing_end_date": existing.end_date,
                        "existing_begin_time": existing.begin_time,
                        "existing_end_time": existing.end_time,
                        "existing_doc": existing.parent
                    })
    
    return conflicts


def dates_overlap(start1, end1, start2, end2):
    """
    Check if two date ranges overlap
    """
    try:
        date1_start = getdate(start1)
        date1_end = getdate(end1)
        date2_start = getdate(start2)
        date2_end = getdate(end2)
        
        # Check for overlap: start1 <= end2 && start2 <= end1
        return date1_start <= date2_end and date2_start <= date1_end
    except Exception:
        return False


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


def validate_duplicate_employees(doc, method):
    """Legacy function - kept for backward compatibility"""
    pass
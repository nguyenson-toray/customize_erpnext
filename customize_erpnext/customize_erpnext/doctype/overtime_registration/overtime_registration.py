# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_time, time_diff_in_hours, getdate, flt
from frappe import _
from datetime import time, datetime, timedelta

from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
    get_attendance_settings,
)
from hrms.hr.doctype.leave_application.leave_application import get_employee_leave_approver


def get_hour_reduction_hours():
    """Hours the shift end is reduced for maternity benefit (from settings)."""
    return flt(get_attendance_settings().hour_reduction_hours)


def maternity_adjusted_end(shift_end):
    """Shift end time reduced by maternity benefit hours."""
    shift_end_dt = datetime.combine(datetime.today(), shift_end)
    return (shift_end_dt - timedelta(hours=get_hour_reduction_hours())).time()


class OvertimeRegistration(Document):
    def validate(self):
        """Validation khi lưu (Save) - theo thứ tự"""
        self.set_requester_and_approver()
        self.validate_approver_for_workflow()

        # Pre-load shift and maternity data for all employees to avoid N+1 queries
        self._preload_employee_data()

        # 0. begin_time < end_time (server-side — JS check can be bypassed
        #    by Data Import / API; inverted times would pass zone checks and
        #    add negative hours to total_hours)
        self.validate_time_order()

        # 1. Kiểm tra giờ OT phải nằm ngoài giờ làm việc (bỏ qua ngày chủ nhật)
        self.validate_ot_outside_working_hours()

        # 2. Kiểm tra các trường hợp thai sản (handled by JS maternity dialog)

        # 3. Duplicate trong form
        self.validate_duplicate_employees()

        # 4. Overlap với OT đã submit
        self.validate_conflicting_ot_requests()

        # 5. Liên tục với OT cùng ngày
        self.validate_ot_continuity_same_day()

        # Calculate totals
        self.calculate_totals_and_apply_reason()

    def get_requester_employee(self):
        """Employee of the user who created the registration (the requester)."""
        user = self.owner or frappe.session.user
        return frappe.db.get_value("Employee", {"user_id": user}, ["name", "employee_name", "custom_group"], as_dict=True)

    def get_requester_name(self):
        emp = self.get_requester_employee()
        return (emp and emp.employee_name) or frappe.utils.get_fullname(self.owner or frappe.session.user)

    def set_requester_and_approver(self):
        """Requester = Employee of the creating user; approver = Leave Approver.

        Approver follows the HRMS Leave Application rule (Employee.leave_approver,
        else the department's first Leave Approver) and is refreshed while the
        doc is still a draft so the approval workflow always targets the
        current approver.
        """
        emp = self.get_requester_employee()
        if not emp:
            return
        if not self.request_by_group:
            self.request_by_group = emp.custom_group

        if self.docstatus == 0:
            approver = get_employee_leave_approver(emp.name)
            if approver:
                self.approver = approver
        if self.approver:
            self.approver_full_name = frappe.db.get_value(
                "Employee", {"user_id": self.approver}, "employee_name"
            ) or frappe.utils.get_fullname(self.approver)

    def validate_approver_for_workflow(self):
        """Workflow has ONE approval level: the requester's Leave Approver.

        Sending to "Pending" without an approver would park the registration
        where nobody can act on it.
        """
        if self.get("workflow_state") == "Pending" and not self.approver:
            frappe.throw(
                _("No approver found for {0}. Ask HR to set a Leave Approver for the employee's department.").format(
                    self.get_requester_name()
                ),
                title=_("Missing Approver"),
            )

    def on_update(self):
        self.share_with_approver()

    def share_with_approver(self):
        """Give the approver read/write/submit on this registration.

        Approvers may hold only the Employee role (if_owner), which would hide
        other people's registrations and block the Approve/Reject transition.
        """
        if self.get("workflow_state") != "Pending" or not self.approver:
            return
        if self.approver in ("Administrator", self.owner):
            return
        from frappe.share import add_docshare

        add_docshare(
            self.doctype, self.name, self.approver,
            read=1, write=1, submit=1,
            flags={"ignore_share_permission": True},
        )

    def _validate_links(self):
        """Skip rows whose Employee does not exist instead of rejecting the doc.

        Frappe validates links before `validate()` runs on insert, so a couple of
        stale/placeholder codes coming from the MongoDB OT sync (e.g. "TIQN-")
        used to fail the whole registration. Drop those rows first, then let the
        core check the remaining links.
        """
        self.drop_unknown_employees()
        super()._validate_links()

    def drop_unknown_employees(self):
        """Remove OT rows pointing at an Employee that no longer exists."""
        rows = self.ot_employees or []
        if not rows:
            return

        codes = {d.employee for d in rows if d.employee}
        existing = set()
        if codes:
            existing = {
                r.name
                for r in frappe.get_all(
                    "Employee", filters={"name": ["in", list(codes)]}, fields=["name"]
                )
            }

        kept = [d for d in rows if d.employee in existing]
        skipped = [d for d in rows if d.employee not in existing]
        if not skipped:
            return

        skipped_codes = sorted({(d.employee or "").strip() or "(empty)" for d in skipped})

        if not kept:
            frappe.throw(
                _("No valid employee in this registration. Unknown employee: {0}").format(
                    ", ".join(skipped_codes)
                )
            )

        for idx, d in enumerate(kept, start=1):
            d.idx = idx
        self.set("ot_employees", kept)

        message = _("Skipped {0} row(s) with unknown Employee: {1}").format(
            len(skipped), ", ".join(skipped_codes)
        )
        frappe.msgprint(message, title=_("Employee Not Found"), indicator="orange")
        frappe.logger("overtime_registration").warning(
            f"{self.name or 'new'}: {message}"
        )

    def validate_time_order(self):
        """Begin time must be before end time on every row."""
        for d in self.ot_employees or []:
            if d.get("begin_time") and d.get("end_time"):
                if get_time(d.get("begin_time")) >= get_time(d.get("end_time")):
                    frappe.throw(_("Row #{0}: Begin Time ({1}) must be before End Time ({2})").format(
                        d.idx, d.get("begin_time"), d.get("end_time")
                    ))

    def _preload_employee_data(self):
        """Pre-load shift and maternity data for all employees to avoid N+1 queries."""
        if not self.ot_employees:
            self._shift_cache = {}
            self._maternity_cache = {}
            return

        # Collect unique employee-date pairs
        employee_dates = set()
        employees = set()
        dates = set()
        for d in self.ot_employees:
            if d.employee and d.date:
                employee_dates.add((d.employee, str(d.date)))
                employees.add(d.employee)
                dates.add(str(d.date))

        if not employees:
            self._shift_cache = {}
            self._maternity_cache = {}
            return

        # Batch load Shift Assignments (Shift Registration is deprecated/removed)
        self._shift_assign_cache = {}
        if dates:
            min_date = min(dates)
            max_date = max(dates)
            # No status filter — HRMS auto-marks expired assignments "Inactive";
            # they remain valid for their historical date range
            shift_assigns = frappe.db.sql("""
                SELECT employee, shift_type AS shift, start_date, end_date
                FROM `tabShift Assignment`
                WHERE employee IN %(employees)s
                  AND docstatus = 1
                  AND start_date <= %(max_date)s
                  AND (end_date IS NULL OR end_date >= %(min_date)s)
                ORDER BY start_date DESC, creation DESC
            """, {"employees": list(employees), "min_date": min_date, "max_date": max_date}, as_dict=1)

            # Group by employee to avoid O(n×m) nested loop
            emp_shift_index = {}
            for a in shift_assigns:
                emp_shift_index.setdefault(a.employee, []).append(a)

            for emp, dt in employee_dates:
                for a in emp_shift_index.get(emp, []):
                    if str(a.start_date) <= dt and (a.end_date is None or dt <= str(a.end_date)):
                        self._shift_assign_cache[(emp, dt)] = a.shift
                        break  # newest assignment first (ORDER BY start_date DESC)

        # Batch load employee default shifts (fallback after Shift Assignment)
        self._emp_default_shift_cache = {}
        emp_rows = frappe.get_all(
            "Employee",
            filters={"name": ["in", list(employees)]},
            fields=["name", "default_shift"]
        )
        for er in emp_rows:
            self._emp_default_shift_cache[er.name] = er.default_shift

        # Batch load maternity records — one query for all employees, then the
        # SAME phase rule as get_employee_maternity_phase (pick_maternity_phase),
        # so server validate agrees with the pre-save dialog and the attendance
        # engine. Same ORDER BY as get_employee_maternity_phase: the rule needs it.
        self._maternity_cache = {}
        if dates:
            from customize_erpnext.api.employee.employee_utils import pick_maternity_phase

            records_by_emp = _load_maternity_records(employees)
            for emp, dt in employee_dates:
                records = records_by_emp.get(emp)
                if not records:
                    continue
                status, has_benefit, em = pick_maternity_phase(records, dt)
                if has_benefit:
                    self._maternity_cache[(emp, dt)] = (True, status) + _maternity_phase_range(status, em)

    def _get_shift_type_cached(self, employee, date):
        """Get shift type using pre-loaded cache.
        Priority: Sunday -> Day, Shift Assignment, Employee default_shift, then Day."""
        date_str = str(date)
        date_obj = getdate(date) if isinstance(date, str) else date

        if date_obj.weekday() == 6:
            return get_attendance_settings().default_shift, "Default Shift For Sunday"

        # Shift Assignment (priority 1)
        cached = self._shift_assign_cache.get((employee, date_str))
        if cached:
            return cached, "Shift Assignment"

        # Employee default shift (priority 2)
        default_shift = self._emp_default_shift_cache.get(employee)
        if default_shift:
            return default_shift, "Default Shift"

        return get_attendance_settings().default_shift, "Default"

    def _check_maternity_cached(self, employee, date):
        """Check maternity benefit using pre-loaded cache."""
        date_str = str(date)
        cached = self._maternity_cache.get((employee, date_str))
        if cached:
            return cached
        return False, None, None, None

    def validate_ot_outside_working_hours(self):
        """Validate OT must be outside working hours"""
        if not self.ot_employees:
            return

        for d in self.ot_employees:
            if not d.employee or not d.date or not d.get("begin_time") or not d.get("end_time"):
                continue

            # Skip validation for Sundays
            date_obj = getdate(d.date)
            if date_obj.weekday() == 6:  # Sunday
                continue

            # Get shift for employee (using batch-loaded cache)
            shift_type, _source = self._get_shift_type_cached(d.employee, d.date)
            shift_config = get_shift_config(shift_type)

            if not shift_config:
                continue

            # Check if shift allows OT
            if not shift_config.get("allows_ot", True):
                frappe.throw(_("Row #{0}: Shift {1} does not allow overtime").format(d.idx, shift_type))

            # Check if employee has maternity benefit (using batch-loaded cache)
            has_benefit, _type, _from, _to = self._check_maternity_cached(d.employee, d.date)

            # Validate OT is outside working hours (relaxed mode)
            is_valid, error_msg = validate_ot_continuity_with_shift(
                d.get("begin_time"), d.get("end_time"), shift_config, has_benefit, None, strict_mode=False
            )

            if not is_valid:
                frappe.throw(_("Row #{0}: {1}").format(d.idx, error_msg))

    def validate_ot_continuity_same_day(self):
        """Validate OT entries are continuous with each other on the same day (zone-aware).

        Cho phép 1 nhóm OT trước ca và 1 nhóm OT sau ca trong cùng ngày.
        Mỗi nhóm phải liên tục nội bộ, nhưng 2 nhóm không cần liên tục với nhau.
        """
        if not self.ot_employees:
            return

        # Group entries by employee and date
        employee_date_entries = {}
        for d in self.ot_employees:
            if not d.employee or not d.date or not d.get("begin_time") or not d.get("end_time"):
                continue

            key = f"{d.employee}_{d.date}"
            if key not in employee_date_entries:
                employee_date_entries[key] = []
            employee_date_entries[key].append(d)

        # Check continuity for each employee-date group with multiple entries
        for key, entries in employee_date_entries.items():
            if len(entries) <= 1:
                continue

            # Sort entries by begin_time
            sorted_entries = sorted(entries, key=lambda x: get_time(x.get("begin_time")))

            # Get shift info (using batch-loaded cache)
            employee = sorted_entries[0].employee
            date = sorted_entries[0].date
            shift_type, _source = self._get_shift_type_cached(employee, date)
            shift_config = get_shift_config(shift_type)

            if not shift_config:
                continue

            has_benefit, _type, _from, _to = self._check_maternity_cached(employee, date)

            if has_benefit:
                effective_shift_end = maternity_adjusted_end(shift_config["end"])
            else:
                effective_shift_end = shift_config["end"]

            shift_start = shift_config["start"]

            # Split entries into pre-shift and post-shift zones
            pre_shift = [e for e in sorted_entries if get_time(e.get("end_time")) <= shift_start]
            post_shift = [e for e in sorted_entries if get_time(e.get("begin_time")) >= effective_shift_end]

            # Check internal continuity within pre-shift zone
            for i in range(1, len(pre_shift)):
                prev_entry = pre_shift[i - 1]
                curr_entry = pre_shift[i]
                prev_end = get_time(prev_entry.get("end_time"))
                curr_begin = get_time(curr_entry.get("begin_time"))
                if curr_begin != prev_end:
                    frappe.throw(_("Row #{0}: Pre-shift overtime must continue from the previous entry (row #{1} ends at {2})").format(
                        curr_entry.idx, prev_entry.idx, prev_end.strftime("%H:%M")
                    ))

            # Check internal continuity within post-shift zone
            for i in range(1, len(post_shift)):
                prev_entry = post_shift[i - 1]
                curr_entry = post_shift[i]
                prev_end = get_time(prev_entry.get("end_time"))
                curr_begin = get_time(curr_entry.get("begin_time"))
                if curr_begin != prev_end:
                    frappe.throw(_("Row #{0}: Post-shift overtime must continue from the previous entry (row #{1} ends at {2})").format(
                        curr_entry.idx, prev_entry.idx, prev_end.strftime("%H:%M")
                    ))

    def validate_duplicate_employees(self):
        """Prevent duplicate or overlapping overtime entries within the same form"""
        
        entries = []
        
        for d in self.ot_employees:
            # Debug what fields are actually available
            missing_fields = []
            if not d.employee:
                missing_fields.append(_("Employee"))
            if not d.date:
                missing_fields.append(_("Date"))
            if not d.get("begin_time"):
                missing_fields.append(_("Begin Time"))
            if not d.get("end_time"):
                missing_fields.append(_("End Time"))
                
            if missing_fields:
                frappe.throw(_("Row #{idx}: {fields} are required.").format(idx=d.idx, fields=", ".join(missing_fields)))
            
            entries.append({
                'idx': d.idx,
                'employee': d.employee,
                'employee_name': d.employee_name,
                'date': d.date,
                'from': d.get("begin_time"),
                'to': d.get("end_time")
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
                        frappe.throw(_("Row {0} and {1}: Duplicate overtime for employee {2} on {3}").format(
                            entry1['idx'],
                            entry2['idx'],
                            entry1['employee_name'],
                            entry1['date']
                        ))

    def validate_conflicting_ot_requests(self):
        """Prevent conflicts and check continuity with existing submitted overtime registrations"""
        if not self.ot_employees:
            return

        # Single batched query for ALL rows (was 1 query per child row),
        # indexed by (employee, date) in Python
        employees = list({d.employee for d in self.ot_employees if d.employee})
        dates = list({str(d.date) for d in self.ot_employees if d.date})
        existing_index = {}
        if employees and dates:
            rows = frappe.db.sql("""
                SELECT child.employee, child.date, child.parent, child.idx,
                       child.begin_time as `from`, child.end_time as `to`
                FROM `tabOvertime Registration Detail` as child
                JOIN `tabOvertime Registration` as parent ON child.parent = parent.name
                WHERE child.employee IN %(employees)s
                AND child.date IN %(dates)s
                AND parent.name != %(current_doc_name)s
                AND parent.docstatus = 1
                AND IFNULL(parent.workflow_state, '') != 'Rejected'
                ORDER BY child.begin_time
            """, {
                "employees": employees,
                "dates": dates,
                "current_doc_name": self.name or "new"
            }, as_dict=1)
            for r in rows:
                existing_index.setdefault((r.employee, str(r.date)), []).append(r)

        for d in self.ot_employees:
            from_time = d.get("begin_time")
            to_time = d.get("end_time")

            existing_entries = existing_index.get((d.employee, str(d.date)), [])

            # Check for overlaps
            for existing in existing_entries:
                if times_overlap(from_time, to_time, existing.get("from"), existing.get("to")):
                    conflicting_doc = existing.get("parent")
                    doc_link = f'<a href="/app/overtime-registration/{conflicting_doc}" target="_blank">{conflicting_doc}</a>'
                    frappe.throw(_("Row {0}: Employee {1} already has overtime on {2} ({3}-{4}). Conflicts with {5}, Row {6}: {7}-{8}").format(
                        d.idx,
                        d.employee_name,
                        d.date,
                        from_time,
                        to_time,
                        doc_link,
                        existing.get("idx"),
                        existing.get("from"),
                        existing.get("to")
                    ))

            # Check continuity with existing submitted OT (zone-aware)
            # OT trước ca và OT sau ca không cần liên tục với nhau,
            # chỉ cần liên tục với các OT cùng zone (trước ca hoặc sau ca).
            if existing_entries:
                from_time_obj = get_time(from_time)
                to_time_obj = get_time(to_time)

                shift_type, _source = self._get_shift_type_cached(d.employee, d.date)
                shift_config = get_shift_config(shift_type)

                if shift_config:
                    has_benefit, _type, _from, _to = self._check_maternity_cached(d.employee, d.date)

                    if has_benefit:
                        effective_shift_end = maternity_adjusted_end(shift_config["end"])
                    else:
                        effective_shift_end = shift_config["end"]

                    shift_start = shift_config["start"]

                    # Classify new entry
                    is_pre_shift = to_time_obj <= shift_start
                    is_post_shift = from_time_obj >= effective_shift_end

                    # Filter existing entries to same zone only
                    same_zone_entries = []
                    for existing in existing_entries:
                        existing_from = get_time(existing.get("from"))
                        existing_to = get_time(existing.get("to"))
                        existing_is_pre = existing_to <= shift_start
                        existing_is_post = existing_from >= effective_shift_end
                        if (is_pre_shift and existing_is_pre) or (is_post_shift and existing_is_post):
                            same_zone_entries.append(existing)

                    # Only check continuity against same-zone entries
                    if same_zone_entries:
                        is_continuous = any(
                            from_time_obj == get_time(e.get("to")) or to_time_obj == get_time(e.get("from"))
                            for e in same_zone_entries
                        )

                        if not is_continuous:
                            existing_times = ", ".join([f"{e.get('from')}-{e.get('to')}" for e in same_zone_entries])
                            existing_docs = ", ".join([f'<a href="/app/overtime-registration/{e.get("parent")}" target="_blank">{e.get("parent")}</a>' for e in same_zone_entries])

                            frappe.throw(_("Row {0}: Overtime {1}-{2} is not continuous with registered overtime ({3}). See: {4}").format(
                                d.idx,
                                from_time,
                                to_time,
                                existing_times,
                                existing_docs
                            ))

    def calculate_totals_and_apply_reason(self):
        """Doc-level totals (hidden fields, used by the approval e-mail)."""
        distinct_employees = set()
        total_hours = 0.0
        for d in self.ot_employees or []:
            if d.employee:
                distinct_employees.add(d.employee)
            if d.get("begin_time") and d.get("end_time"):
                total_hours = flt(total_hours + time_diff_in_hours(d.end_time, d.get("begin_time")), 2)

        self.total_employees = len(distinct_employees)
        self.total_hours = flt(total_hours, 2)

@frappe.whitelist()
def check_overtime_conflicts(entries, current_doc_name="new"):
    """Rows of this form whose time overlaps the same employee/date in ANOTHER registration.

    Feeds the "overlap with another form" part of the pre-save check dialog (soft check:
    the dialog offers to remove the rows, the server never blocks — user chốt 12/11/2026,
    option A). Compares with every registration that is not cancelled (docstatus < 2):
    since 07/11/2026 the DocType is not submittable, so the former `docstatus = 1` filter
    never matched and two Draft forms with the same employee/date saved silently
    (TIQN-0057 16/11/2026, OTR-261112-0001 / -0002).
    Deliberately NOT applied in validate(): the 18:00 MongoDB sync inserts through
    validate and existing data already has overlaps between forms.
    """
    frappe.has_permission("Overtime Registration", "read", throw=True)
    if isinstance(entries, str):
        entries = frappe.parse_json(entries)
    entries = [e for e in (entries or []) if e.get("employee") and e.get("date")]
    if not entries:
        return []

    existing_rows = frappe.db.sql("""
        SELECT child.parent, child.idx, child.employee, child.date,
               child.begin_time AS `from`, child.end_time AS `to`
        FROM `tabOvertime Registration Detail` AS child
        JOIN `tabOvertime Registration` AS parent ON child.parent = parent.name
        WHERE child.employee IN %(employees)s
          AND child.date IN %(dates)s
          AND parent.name != %(current_doc_name)s
          AND parent.docstatus < 2
          AND IFNULL(parent.workflow_state, '') != 'Rejected'
        ORDER BY child.begin_time
    """, {
        "employees": list({e["employee"] for e in entries}),
        "dates": list({str(e["date"]) for e in entries}),
        "current_doc_name": current_doc_name or "new",
    }, as_dict=1)

    by_key = {}
    for r in existing_rows:
        by_key.setdefault((r.employee, str(r.date)), []).append(r)

    conflicts = []
    for entry in entries:
        for existing in by_key.get((entry["employee"], str(entry["date"])), []):
            if times_overlap(entry["begin_time"], entry["end_time"], existing["from"], existing["to"]):
                conflicts.append({
                    "idx": entry.get("idx"),
                    "employee": entry["employee"],
                    "employee_name": entry.get("employee_name"),
                    "date": entry["date"],
                    "current_from": entry["begin_time"],
                    "current_to": entry["end_time"],
                    "existing_from": str(existing["from"]),
                    "existing_to": str(existing["to"]),
                    "existing_doc": existing["parent"],
                    "existing_idx": existing["idx"],
                })
    return conflicts

@frappe.whitelist()
def get_ot_registered_elsewhere(employees, dates, current_doc_name="new"):
    """OT rows already registered in OTHER registrations for these employees/dates.

    Feeds the "Select Employees for Overtime Registration" dialog (user chốt 13/11/2026,
    option a): an employee already registered on every selected day (overlapping the
    chosen time) cannot be ticked; one registered on some days is ticked normally and
    those days are skipped when adding. Same scope as check_overtime_conflicts
    (docstatus < 2, not Rejected, Draft and MongoDB-synced forms included). Only IDs,
    dates, times and form names are returned.
    """
    frappe.has_permission("Overtime Registration", "read", throw=True)
    employees = frappe.parse_json(employees) if isinstance(employees, str) else employees
    dates = frappe.parse_json(dates) if isinstance(dates, str) else dates
    if not employees or not dates:
        return []

    rows = frappe.db.sql("""
        SELECT child.employee, child.date, child.begin_time, child.end_time, child.parent
        FROM `tabOvertime Registration Detail` AS child
        JOIN `tabOvertime Registration` AS parent ON child.parent = parent.name
        WHERE child.employee IN %(employees)s
          AND child.date IN %(dates)s
          AND parent.name != %(current_doc_name)s
          AND parent.docstatus < 2
          AND IFNULL(parent.workflow_state, '') != 'Rejected'
        ORDER BY child.date, child.begin_time
    """, {
        "employees": list(employees),
        "dates": [str(d) for d in dates],
        "current_doc_name": current_doc_name or "new",
    }, as_dict=1)
    return [{
        "employee": r.employee,
        "date": str(r.date),
        "from": str(r.begin_time),
        "to": str(r.end_time),
        "doc": r.parent,
    } for r in rows]

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
    except Exception as e:
        frappe.log_error(f"times_overlap error: {e}", "OT Time Overlap Check")
        return False

def _maternity_phase_range(status, em):
    """(from_date, to_date) of the phase `status` on Employee Maternity record `em`."""
    if status == "Maternity Leave":
        return em.maternity_from_date, em.maternity_to_date
    if status == "Young Child":
        return em.youg_child_from_date, em.youg_child_to_date
    return em.pregnant_from_date, em.pregnant_to_date or em.estimated_due_date


def _load_maternity_records(employees):
    """{employee: [Employee Maternity rows]} in the order pick_maternity_phase() needs
    (same columns / ORDER BY as get_employee_maternity_phase)."""
    rows = frappe.db.sql("""
        SELECT name, employee,
               pregnant_from_date, pregnant_to_date, estimated_due_date,
               maternity_from_date, maternity_to_date,
               youg_child_from_date, youg_child_to_date,
               apply_hour_reduction
        FROM `tabEmployee Maternity`
        WHERE employee IN %(employees)s
        ORDER BY pregnant_from_date DESC, creation DESC
    """, {"employees": list(employees)}, as_dict=1)
    by_emp = {}
    for rec in rows:
        by_emp.setdefault(rec.employee, []).append(rec)
    return by_emp


def check_maternity_benefit(employee, date):
    """Check if employee has maternity benefit on given date.
    Returns: (has_benefit, status, from_date, to_date) — status is the English
    phase key ("Pregnant" / "Young Child" / "Maternity Leave"); the client
    translates it.
    Delegates benefit logic to get_employee_maternity_phase (employee_utils).
    """
    from customize_erpnext.api.employee.employee_utils import get_employee_maternity_phase

    # Lấy khoảng ngày từ ĐÚNG hồ sơ đang phủ `date` — trước 07/10/2026 là
    # get_value({"employee": ...}) lấy đại 1 hồ sơ, NV có 2 chu kỳ hiện sai ngày.
    status, has_benefit, em = get_employee_maternity_phase(employee, date)
    if not has_benefit:
        return False, None, None, None

    return (True, status) + _maternity_phase_range(status, em)

def get_shift_type(employee, date):
    """Get shift type for employee on date.
    Priority: Sunday -> Day, Shift Assignment, Employee default_shift, then Day.
    """
    # Check if it's Sunday
    if isinstance(date, str):
        date_obj = getdate(date)
    else:
        date_obj = date

    if date_obj.weekday() == 6:  # Sunday
        return get_attendance_settings().default_shift, "Default Shift For Sunday"

    # Priority 1: Shift Assignment (no status filter — "Inactive" = expired
    # by HRMS's nightly job, still valid for its historical date range)
    shift_assign = frappe.db.sql("""
        SELECT shift_type
        FROM `tabShift Assignment`
        WHERE employee = %(employee)s
          AND docstatus = 1
          AND start_date <= %(date)s
          AND (end_date IS NULL OR end_date >= %(date)s)
        ORDER BY start_date DESC, creation DESC
        LIMIT 1
    """, {"employee": employee, "date": date}, as_dict=1)

    if shift_assign:
        return shift_assign[0].shift_type, "Shift Assignment"

    # Priority 2: Employee default shift
    default_shift = frappe.db.get_value("Employee", employee, "default_shift")
    if default_shift:
        return default_shift, "Default Shift"

    # Default: configured default shift
    return get_attendance_settings().default_shift, "Default"

def get_shift_config(shift_type):
    """Get shift configuration from Shift Type DocType with caching.

    Reads from DB and caches for 5 minutes to avoid repeated queries.
    Falls back to hardcoded defaults if the Shift Type is not found.
    """
    if not shift_type:
        return None

    cache_key = f"ot_shift_config:{shift_type}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    try:
        shift_doc = frappe.db.get_value(
            "Shift Type",
            shift_type,
            ["start_time", "end_time", "custom_begin_break_time", "custom_end_break_time", "allow_overtime"],
            as_dict=True
        )
    except Exception:
        shift_doc = None

    if not shift_doc:
        return None

    def _to_time(val):
        """Convert timedelta or time string to time object."""
        if isinstance(val, timedelta):
            total_seconds = int(val.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return time(hours, minutes)
        return get_time(val) if val else None

    start = _to_time(shift_doc.start_time)
    end = _to_time(shift_doc.end_time)
    break_start = _to_time(shift_doc.custom_begin_break_time)
    break_end = _to_time(shift_doc.custom_end_break_time)

    if not start or not end:
        return None

    config = {
        "start": start,
        "end": end,
        "break_start": break_start or start,
        "break_end": break_end or start,
        "allows_ot": bool(shift_doc.allow_overtime) if shift_doc.allow_overtime is not None else True
    }

    frappe.cache().set_value(cache_key, config, expires_in_sec=300)
    return config

def validate_ot_continuity_with_shift(begin_time, end_time, shift_config, has_maternity=False, other_ot_entries=None, strict_mode=False):
    """Validate that OT time is continuous with shift or other OT entries

    When strict_mode=False (save):
    - Pre-shift: ends at or before shift start
    - Lunch break: during break_start to break_end
    - Post-shift: starts at or after shift end (or shift_end - 1h for maternity)

    When strict_mode=True (submit):
    - Pre-shift: ends exactly at shift start
    - Lunch break: during break_start to break_end
    - Post-shift: starts exactly at shift end, OR continuous with another OT entry

    Returns: (is_valid, error_message)
    """
    begin_time_obj = get_time(begin_time)
    end_time_obj = get_time(end_time)

    shift_start = shift_config["start"]
    shift_end = shift_config["end"]
    break_start = shift_config["break_start"]
    break_end = shift_config["break_end"]

    # For maternity, shift ends earlier by hour_reduction_hours (setting)
    if has_maternity:
        maternity_shift_end = maternity_adjusted_end(shift_end)
    else:
        maternity_shift_end = shift_end

    if strict_mode:
        # STRICT MODE (Submit): require exact continuity

        # Check pre-shift OT (must end exactly at shift start)
        if end_time_obj == shift_start and begin_time_obj < shift_start:
            return True, None

        # Check lunch break OT (during break)
        if break_start != break_end:
            if begin_time_obj >= break_start and end_time_obj <= break_end:
                return True, None

        # Check post-shift OT (must start exactly at shift end)
        if begin_time_obj == maternity_shift_end:
            return True, None

        # Check if this OT is continuous with another OT entry
        if other_ot_entries:
            for other_entry in other_ot_entries:
                other_begin = get_time(other_entry.get("begin_time"))
                other_end = get_time(other_entry.get("end_time"))

                # This OT starts where another ends
                if begin_time_obj == other_end:
                    return True, None

                # This OT ends where another starts
                if end_time_obj == other_begin:
                    return True, None

        # Invalid in strict mode
        if has_maternity:
            return False, _("Overtime must start right after the shift ({0}), fall within the lunch break ({1}-{2}), end exactly when the shift starts ({3}), or continue another overtime entry").format(
                maternity_shift_end.strftime("%H:%M"),
                break_start.strftime("%H:%M"),
                break_end.strftime("%H:%M"),
                shift_start.strftime("%H:%M")
            )
        else:
            return False, _("Overtime must start right after the shift ({0}), fall within the lunch break ({1}-{2}), end exactly when the shift starts ({3}), or continue another overtime entry").format(
                shift_end.strftime("%H:%M"),
                break_start.strftime("%H:%M"),
                break_end.strftime("%H:%M"),
                shift_start.strftime("%H:%M")
            )
    else:
        # NORMAL MODE (Save): allow any time after shift end

        # Check pre-shift OT (ends at or before shift start)
        if end_time_obj <= shift_start and begin_time_obj < shift_start:
            return True, None

        # Check lunch break OT (during break)
        if break_start != break_end:
            if begin_time_obj >= break_start and end_time_obj <= break_end:
                return True, None

        # Check post-shift OT (starts at or after shift end)
        if begin_time_obj >= maternity_shift_end:
            return True, None

        # Invalid: OT overlaps with working hours
        # if has_maternity:
        #     return False, _("Giờ tăng ca phải nằm ngoài giờ làm việc (trước {0}, trong giờ nghỉ trưa {1}-{2}, hoặc sau {3})").format(
        #         shift_start.strftime("%H:%M"),
        #         break_start.strftime("%H:%M"),
        #         break_end.strftime("%H:%M"),
        #         maternity_shift_end.strftime("%H:%M")
        #     )
        # else:
        #     return False, _("Giờ tăng ca phải nằm ngoài giờ làm việc (trước {0}, trong giờ nghỉ trưa {1}-{2}, hoặc sau {3})").format(
        #         shift_start.strftime("%H:%M"),
        #         break_start.strftime("%H:%M"),
        #         break_end.strftime("%H:%M"),
        #         shift_end.strftime("%H:%M")
        #     )
        # The rejection above is intentionally disabled for save (relaxed mode) —
        # but the function must still return a tuple, otherwise the caller's
        # `is_valid, error_msg = ...` crashes with "cannot unpack NoneType"
        return True, None

@frappe.whitelist()
def check_employees_with_maternity_benefits(entries):
    """
    Check if any employees in the entries have active maternity benefits
    and their begin_time starts at their shift end time
    Returns list of employees who need time adjustment (-1h)
    """
    frappe.has_permission("Overtime Registration", "read", throw=True)
    import json

    if isinstance(entries, str):
        entries = json.loads(entries)

    employees_needing_adjustment = []

    for entry in entries:
        employee = entry.get("employee")
        date = entry.get("date")
        begin_time = entry.get("begin_time")

        if not employee or not date or not begin_time:
            continue

        # Get shift type and config for this employee
        shift_type, _source = get_shift_type(employee, date)
        shift_config = get_shift_config(shift_type)

        if not shift_config:
            continue

        # Check if begin_time equals shift end (normal shift end, not maternity adjusted)
        begin_time_obj = get_time(begin_time)
        shift_end = shift_config["end"]

        if begin_time_obj != shift_end:
            continue

        # Check for maternity benefit
        has_benefit, benefit_status, from_date, to_date = check_maternity_benefit(employee, date)

        if has_benefit:
            # Get employee name
            employee_name = frappe.db.get_value("Employee", employee, "employee_name")

            # Format dates for display
            from_date_str = from_date.strftime("%d/%m/%Y") if from_date else ""
            to_date_str = to_date.strftime("%d/%m/%Y") if to_date else ""

            # Calculate adjusted times (shift end - maternity benefit hours)
            adjusted_shift_end = maternity_adjusted_end(shift_end)

            employees_needing_adjustment.append({
                "adjust_hours": get_hour_reduction_hours(),  # JS uses this to shift begin/end times
                "idx": entry.get("idx"),
                "employee": employee,
                "employee_name": employee_name,
                "date": date,
                "begin_time": entry.get("begin_time"),
                "end_time": entry.get("end_time"),
                "benefit_status": benefit_status,  # English key; JS translates
                "from_date": from_date_str,
                "to_date": to_date_str,
                "shift_type": shift_type,
                "shift_end": shift_end.strftime("%H:%M"),
                "adjusted_shift_end": adjusted_shift_end.strftime("%H:%M")
            })

    return employees_needing_adjustment

@frappe.whitelist()
def validate_ot_entries_continuity(entries, strict_mode=False):
    """
    Validate that all OT entries have times continuous with their shifts
    or continuous with other OT entries for same employee on same day

    strict_mode=False (save): allow any time after shift end
    strict_mode=True (submit): require exact continuity with shift or other OT
    Returns list of errors for invalid entries
    """
    frappe.has_permission("Overtime Registration", "read", throw=True)
    import json

    if isinstance(entries, str):
        entries = json.loads(entries)

    if isinstance(strict_mode, str):
        strict_mode = strict_mode.lower() == 'true'

    errors = []

    # Group entries by employee and date for checking continuity between OT entries
    employee_date_entries = {}
    for entry in entries:
        employee = entry.get("employee")
        date = entry.get("date")
        if employee and date:
            key = f"{employee}_{date}"
            if key not in employee_date_entries:
                employee_date_entries[key] = []
            employee_date_entries[key].append(entry)

    for entry in entries:
        employee = entry.get("employee")
        date = entry.get("date")
        begin_time = entry.get("begin_time")
        end_time = entry.get("end_time")

        if not employee or not date or not begin_time or not end_time:
            continue

        # Get shift type for this employee on this date
        shift_type, _source = get_shift_type(employee, date)
        shift_config = get_shift_config(shift_type)

        if not shift_config:
            continue

        # Check if shift allows OT (Shift 1 and Shift 2 do not allow OT)
        if not shift_config.get("allows_ot", True):
            employee_name = frappe.db.get_value("Employee", employee, "employee_name")
            errors.append({
                "idx": entry.get("idx"),
                "employee": employee,
                "employee_name": employee_name,
                "date": date,
                "begin_time": begin_time,
                "end_time": end_time,
                "shift_type": shift_type,
                "error": _("Shift {0} does not allow overtime").format(shift_type)
            })
            continue

        # Check if employee has maternity benefit
        has_benefit, _type, _from, _to = check_maternity_benefit(employee, date)

        # Get other OT entries for same employee on same day
        key = f"{employee}_{date}"
        other_entries = [e for e in employee_date_entries.get(key, []) if e.get("idx") != entry.get("idx")]

        # Validate OT continuity
        is_valid, error_msg = validate_ot_continuity_with_shift(
            begin_time, end_time, shift_config, has_benefit, other_entries, strict_mode
        )

        if not is_valid:
            employee_name = frappe.db.get_value("Employee", employee, "employee_name")
            errors.append({
                "idx": entry.get("idx"),
                "employee": employee,
                "employee_name": employee_name,
                "date": date,
                "begin_time": begin_time,
                "end_time": end_time,
                "shift_type": shift_type,
                "error": error_msg
            })

    return errors

@frappe.whitelist()
def get_ot_maternity_benefits(employees, dates):
	"""Note column of the OT summary table: who finishes the shift early on the OT dates.

	Same rule as the pre-save check (pick_maternity_phase): a phase is listed only when
	the employee actually gets the hour reduction on at least one of `dates` — e.g. a
	pregnant employee without "apply hour reduction" gets no icon. Replaces
	get_maternity_flags (12/11/2026), which flagged the whole pregnancy date range.
	Like get_ot_blocked_employees: no read permission on Employee Maternity needed —
	only employee IDs and phase names are returned.

	Returns {"hours": <hour reduction>, "employees": {employee: [phase, ...]}}.
	"""
	from customize_erpnext.api.employee.employee_utils import pick_maternity_phase

	employees = frappe.parse_json(employees) if isinstance(employees, str) else employees
	dates = frappe.parse_json(dates) if isinstance(dates, str) else dates
	result = {"hours": get_hour_reduction_hours(), "employees": {}}
	if not employees or not dates:
		return result

	for emp, records in _load_maternity_records(employees).items():
		phases = []
		for dt in dates:
			status, has_benefit, _rec = pick_maternity_phase(records, dt)
			if has_benefit and status not in phases:
				phases.append(status)
		if phases:
			result["employees"][emp] = phases
	return result


@frappe.whitelist()
def get_ot_blocked_employees(employees):
	"""{employee: reason} — NV KHÔNG được chọn trong dialog "Select Employees for Overtime
	Registration" (user chốt 02/11/2026). Đọc ĐÚNG giá trị đang lưu trên hồ sơ Employee
	Maternity (job 00:10 + mỗi lần lưu giữ chúng cập nhật theo hôm nay), không tính theo ngày:
	  - status = "Maternity Leave"                          → "Maternity Leave"
	  - status = "Pregnant" và overtime_status = "Not Allowed" → "Pregnant"
	Như `get_ot_maternity_benefits`: không cần quyền đọc Employee Maternity, chỉ trả mã NV + lý do.
	"""
	if isinstance(employees, str):
		employees = frappe.parse_json(employees)
	if not employees:
		return {}

	result = {}
	for rec in frappe.get_all(
		"Employee Maternity",
		filters={"employee": ["in", employees], "status": ["in", ["Maternity Leave", "Pregnant"]]},
		fields=["employee", "status", "overtime_status"],
	):
		if rec.status == "Maternity Leave":
			result[rec.employee] = "Maternity Leave"
		elif rec.overtime_status == "Not Allowed":
			result.setdefault(rec.employee, "Pregnant")
	return result


def get_owner_only_condition(alias="parent", user=None):
    """SQL condition limiting raw-SQL reads to what the user may open.

    Users whose only read access comes from an "Only If Creator" permission
    (e.g. TIQN Staff / Employee) see the registrations they created plus the
    ones shared with them (the approver share). Any role with unrestricted
    read (HR Manager, TIQN Manager, ...) wins -> no condition.
    """
    user = user or frappe.session.user
    perms = frappe.permissions.get_role_permissions(frappe.get_meta("Overtime Registration"), user=user)
    if not perms.get("read") or "read" not in (perms.get("if_owner") or {}):
        return ""
    u = frappe.db.escape(user)
    return (
        f"({alias}.owner = {u} OR {alias}.name IN ("
        f"SELECT share_name FROM `tabDocShare` WHERE share_doctype = 'Overtime Registration'"
        f" AND `read` = 1 AND (user = {u} OR everyone = 1)))"
    )

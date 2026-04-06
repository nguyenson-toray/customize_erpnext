# -*- coding: utf-8 -*-
# customize_erpnext/health_check_up/doctype/health_check_up/health_check_up.py
#
# Doctype Controller for Health Check
# Handles validation, auto-fetch employee data, pregnant status check

import frappe
from frappe.model.document import Document
from frappe.utils import nowtime, today, getdate


class HealthCheckUp(Document):
    def validate(self):
        self.fetch_employee_info()
        self.check_pregnant_status()
        self.validate_hospital_code_unique()
        self.compute_status()
        # self.validate_times()

    def compute_status(self):
        """Auto-compute status based on actual times."""
        if self.end_time_actual:
            self.status = "Hoàn thành"
        elif self.start_time_actual:
            self.status = "Đang khám"
        else:
            self.status = "Chưa khám"

    def fetch_employee_info(self):
        """
        Auto-fetch employee master data if not already populated.
        This covers both manual entry and bulk import scenarios.
        Fields fetched: employee_name, gender, department, custom_section,
                       custom_group, designation
        """
        if not self.employee:
            return

        emp = frappe.get_cached_doc("Employee", self.employee)

        field_map = {
            "employee_name": "employee_name",
            "gender": "gender",
            "department": "department",
            "custom_section": "custom_section",
            "custom_group": "custom_group",
            "designation": "designation",
        }

        for local_field, emp_field in field_map.items():
            if not self.get(local_field):
                self.set(local_field, emp.get(emp_field))

    def check_pregnant_status(self):
        """
        Auto-check pregnant status for female employees.
        Cấu trúc mới: kiểm tra pregnant_from_date có giá trị trên EM record của employee.
        """
        if self.gender not in ("Female", "Nữ"):
            self.pregnant = 0
            return

        is_pregnant = frappe.db.get_value(
            "Employee Maternity",
            {"employee": self.employee},
            "pregnant_from_date",
        )
        self.pregnant = 1 if is_pregnant else 0

    def validate_hospital_code_unique(self):
        """
        Ensure hospital_code is unique within the same date.
        One hospital_code maps to exactly one employee per examination day.
        """
        if not (self.hospital_code and self.date):
            return

        existing = frappe.db.exists(
            "Health Check-Up",
            {
                "hospital_code": self.hospital_code,
                "date": self.date,
                "name": ("!=", self.name),
            },
        )

        if existing:
            frappe.throw(
                frappe._(
                    "Hospital Code <b>{0}</b> đã tồn tại cho ngày <b>{1}</b> "
                    "(Record: {2})"
                ).format(self.hospital_code, self.date, existing)
            )

    def validate_times(self):
        """Validate that end_time is after start_time"""
        if self.start_time and self.end_time:
            if str(self.start_time) >= str(self.end_time):
                frappe.throw(frappe._("End Time phải sau Start Time"))

        if self.start_time_actual and self.end_time_actual:
            if str(self.start_time_actual) > str(self.end_time_actual):
                frappe.throw(
                    frappe._("End Time Actual phải sau Start Time Actual")
                )

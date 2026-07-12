# -*- coding: utf-8 -*-
# customize_erpnext/health_check_up/doctype/health_check_up/health_check_up.py
#
# Doctype Controller for Health Check
# Handles validation, auto-fetch employee data, pregnant status check

import frappe
from frappe.model.document import Document
from frappe.utils import nowtime, today, getdate, get_time


class HealthCheckUp(Document):
    def validate(self):
        self.fetch_employee_info()
        self.check_pregnant_status()
        self.validate_hospital_code_unique()
        self.validate_employee_unique()
        self.compute_status()
        self.validate_times()

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
        Đang mang thai = ngày khám nằm trong khoảng [pregnant_from_date, pregnant_to_date]
        trên Employee Maternity (pregnant_to_date trống = chưa sinh → vẫn đang mang thai).
        """
        if self.gender not in ("Female", "Nữ"):
            self.pregnant = 0
            return

        check_date = getdate(self.date) if self.date else getdate(today())

        rows = frappe.get_all(
            "Employee Maternity",
            filters={"employee": self.employee, "pregnant_from_date": ("is", "set")},
            fields=["pregnant_from_date", "pregnant_to_date"],
            order_by="pregnant_from_date desc",
        )

        self.pregnant = 0
        for row in rows:
            if getdate(row.pregnant_from_date) <= check_date and (
                not row.pregnant_to_date or check_date <= getdate(row.pregnant_to_date)
            ):
                self.pregnant = 1
                break

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

    def validate_employee_unique(self):
        """
        Ensure one employee has only one record per examination day.
        Without this, scan APIs may silently write to the wrong record.
        """
        if not (self.employee and self.date):
            return

        existing = frappe.db.exists(
            "Health Check-Up",
            {
                "employee": self.employee,
                "date": self.date,
                "name": ("!=", self.name),
            },
        )

        if existing:
            frappe.throw(
                frappe._(
                    "Nhân viên <b>{0}</b> đã có hồ sơ khám cho ngày <b>{1}</b> "
                    "(Record: {2})"
                ).format(self.employee, self.date, existing)
            )

    def validate_times(self):
        """Validate that end_time is after start_time.
        Compare via get_time() — plain string compare fails on '9:00' vs '10:00'."""
        if self.start_time and self.end_time:
            if get_time(str(self.start_time)) >= get_time(str(self.end_time)):
                frappe.throw(frappe._("End Time phải sau Start Time"))

        if self.start_time_actual and self.end_time_actual:
            if get_time(str(self.start_time_actual)) > get_time(str(self.end_time_actual)):
                frappe.throw(
                    frappe._("Giờ Thu HS thực tế ({0}) không được sớm hơn giờ Phát HS thực tế ({1})").format(
                        self.end_time_actual, self.start_time_actual
                    )
                )

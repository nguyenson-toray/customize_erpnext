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

    def on_update(self):
        self._organize_result_file()

    def _organize_result_file(self):
        """Chuyển file File Result vào thư mục vật lý private/files/health_check_results/<ngày khám>/.
        Áp dụng cho mọi cách gán file (đính kèm thủ công trên form hoặc nút Upload Results)."""
        if not self.file_result or not self.date:
            return
        from customize_erpnext.health_check_up.api.health_check_api import _relocate_result_file

        new_url = _relocate_result_file(self.file_result, self.name, self.date)
        if new_url and new_url != self.file_result:
            self.db_set("file_result", new_url, update_modified=False)

    def compute_status(self):
        """Auto-compute status.
        - not_check_up (Check) được tích → "Không khám" (ưu tiên cao nhất; lý do ghi ở Note).
        - còn lại: theo giờ thực tế phát/thu.
        """
        if self.get("not_check_up"):
            self.status = "Không khám"
        elif self.end_time_actual:
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
        Xác định trạng thái mang thai.
        - Không phải nữ → luôn 0.
        - Nếu đã có giá trị TƯỜNG MINH (nhập tay trên form / import có cột 'pregnant') → GIỮ NGUYÊN,
          để loại trừ trường hợp Employee Maternity bị sai.
        - Nếu KHÔNG nhập (giá trị None) → lấy theo field 'status' của Employee Maternity
          (status = "Pregnant"). Status này đã được scheduler tự tính lại hàng ngày, không tính lại nữa.
        """
        if self.gender not in ("Female", "Nữ"):
            self.pregnant = 0
            return

        # Đã nhập tay / import có giá trị → tôn trọng, không tự ghi đè.
        if self.get("pregnant") is not None:
            return

        self.pregnant = (
            1
            if frappe.db.exists(
                "Employee Maternity", {"employee": self.employee, "status": "Pregnant"}
            )
            else 0
        )

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

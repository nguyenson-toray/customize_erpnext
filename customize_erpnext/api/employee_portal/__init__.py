# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Zalo Mini App "Cổng nhân viên" API.

Every endpoint is reachable as
`/api/method/customize_erpnext.api.employee_portal.<name>` - the contract is
`customize_erpnext/employee_portal/API_CONTRACT.md`. Read core.py before adding one:
all of them must go through `portal_api`.
"""

from customize_erpnext.api.employee_portal.attendance import (
	get_attendance_calendar,
	get_attendance_day,
	get_attendance_request,
	get_attendance_requests,
	get_attendance_summary,
	get_overtime,
)
from customize_erpnext.api.employee_portal.auth import dev_login, get_config, login, logout, me, set_oa_follow
from customize_erpnext.api.employee_portal.home import get_home
from customize_erpnext.api.employee_portal.leave import (
	download_document,
	get_leave_application,
	get_leave_applications,
	get_leave_balances,
)
from customize_erpnext.api.employee_portal.notifications import get_notifications, mark_notifications_read
from customize_erpnext.api.employee_portal.payslip import get_payslip, get_payslip_periods

__all__ = [
	"get_config",
	"login",
	"dev_login",
	"logout",
	"me",
	"set_oa_follow",
	"get_notifications",
	"mark_notifications_read",
	"get_payslip",
	"get_payslip_periods",
	"get_home",
	"get_leave_balances",
	"get_leave_applications",
	"get_leave_application",
	"download_document",
	"get_attendance_calendar",
	"get_attendance_day",
	"get_attendance_summary",
	"get_overtime",
	"get_attendance_requests",
	"get_attendance_request",
]

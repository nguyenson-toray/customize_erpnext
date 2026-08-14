# Thin adapter: all logic lives in api/daily_attendance_metrics.py so the charts
# and the daily email can never disagree about a number.

import frappe

from customize_erpnext.api.daily_attendance_metrics import chart_trend


@frappe.whitelist()
def get_data(
	chart_name=None,
	chart=None,
	no_cache=None,
	filters=None,
	from_date=None,
	to_date=None,
	timespan=None,
	time_interval=None,
	heatmap_year=None,
):
	return chart_trend(filters)

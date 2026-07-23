# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


from dateutil.relativedelta import relativedelta

import frappe
from frappe import _
from frappe.utils import getdate
from frappe.utils.dashboard import cache_source

def custom_get_ranges() -> list[tuple[int, int]]:
	ranges = []

	for i in range(18, 45, 5):
		ranges.append((i, i + 4))

	ranges.append(48)

	return ranges

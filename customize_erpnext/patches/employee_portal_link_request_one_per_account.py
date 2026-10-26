# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""pre_model_sync: TIQN Portal Link Request becomes one record per Zalo account
(26/10/2026) - `account` turns unique in the model sync, which fails while two
requests of the same account exist. Keep the newest one per account; the older ones
were superseded anyway. Idempotent.
"""

import frappe

LINK_REQUEST = "TIQN Portal Link Request"


def execute():
	if not frappe.db.table_exists(LINK_REQUEST):
		return
	duplicates = frappe.db.sql(
		f"SELECT account FROM `tab{LINK_REQUEST}` WHERE IFNULL(account, '') != '' GROUP BY account HAVING COUNT(*) > 1",
		pluck=True,
	)
	for account in duplicates:
		names = frappe.get_all(LINK_REQUEST, filters={"account": account}, pluck="name", order_by="creation desc")
		for name in names[1:]:
			frappe.delete_doc(LINK_REQUEST, name, force=True, ignore_permissions=True)

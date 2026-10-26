# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""post_model_sync: unique index on TIQN Portal Link Request.account (26/10/2026).

The model sync adds it as `ADD UNIQUE INDEX IF NOT EXISTS account`, which is silently
skipped while the old non-unique search index - also named `account` - exists. The
field no longer has search_index; replace that index by the unique one. Idempotent.
"""

import frappe

LINK_REQUEST = "TIQN Portal Link Request"


def execute():
	table = f"tab{LINK_REQUEST}"
	if not frappe.db.table_exists(LINK_REQUEST) or frappe.db.get_column_index(table, "account", unique=True):
		return
	if index := frappe.db.get_column_index(table, "account", unique=False):
		frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP INDEX `{index.Key_name}`")
	frappe.db.sql_ddl(f"ALTER TABLE `{table}` ADD UNIQUE INDEX `account` (`account`)")

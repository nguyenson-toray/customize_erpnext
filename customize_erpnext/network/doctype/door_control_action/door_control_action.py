# -*- coding: utf-8 -*-
# Audit trail of /door_control: one row per open / close command, written by
# customize_erpnext.api.door_control only. ZKTeco devices do not log a
# software unlock, so without this nobody could tell who opened a door.

from frappe.model.document import Document


class DoorControlAction(Document):
	pass

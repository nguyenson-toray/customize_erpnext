# -*- coding: utf-8 -*-
# Door access log of the IT room (ZKTeco F21Lite controller).
# Kept separate from Employee Checkin on purpose: these punches are room
# access, not attendance, and must never reach the attendance engine.

import frappe
from frappe.model.document import Document


class DoorAccessLog(Document):
    pass


def on_doctype_update():
    # One punch = one (user_id, timestamp). The device keeps every log it ever
    # recorded, so "Get logs" is pressed over the same range again and again;
    # the unique key is what makes re-fetching idempotent at the DB level.
    frappe.db.add_unique("Door Access Log", ["user_id", "timestamp"], constraint_name="unique_user_timestamp")

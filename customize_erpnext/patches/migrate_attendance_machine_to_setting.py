# -*- coding: utf-8 -*-
"""Migrate standalone Attendance Machine records into the Single DocType
Attendance Machine Setting (child table), then drop the old DocType.

Connection settings (port/timeout/force_udp/ommit_ping) move to parent level,
taken from the first old record (all machines shared the same values).
"""
import frappe


def execute():
    if not frappe.db.table_exists("Attendance Machine"):
        return

    old_machines = frappe.db.sql(
        """
        SELECT device_name, ip_address, port, timeout, force_udp, ommit_ping,
               enable, master_device, location, model
        FROM `tabAttendance Machine`
        ORDER BY name
        """,
        as_dict=True,
    )

    settings = frappe.get_single("Attendance Machine Setting")

    # Idempotent: only fill if the child table is still empty
    if not settings.machines and old_machines:
        first = old_machines[0]
        settings.default_port = first.port or 4370
        settings.timeout = first.timeout or 10
        settings.force_udp = 1 if first.force_udp else 0
        settings.ommit_ping = 1 if first.ommit_ping else 0

        seen_names = set()
        for m in old_machines:
            if m.device_name in seen_names:
                continue
            seen_names.add(m.device_name)
            settings.append("machines", {
                "device_name": m.device_name,
                "ip_address": m.ip_address,
                "enable": 1 if m.enable else 0,
                "master_device": 1 if m.master_device else 0,
                "location": m.location or "",
                "model": m.model or "",
            })

        settings.save(ignore_permissions=True)
        print(f"Migrated {len(settings.machines)} machines into Attendance Machine Setting")

    # Drop the old DocType (also drops its table). Records were requested to
    # be removed permanently — data now lives in the Single doc above.
    frappe.delete_doc("DocType", "Attendance Machine", force=1, ignore_missing=True, delete_permanently=True)
    frappe.db.commit()
    print("Deleted old DocType: Attendance Machine")

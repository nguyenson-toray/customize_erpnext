# -*- coding: utf-8 -*-
"""
Central access layer for attendance machine configuration.

Machines are stored in the Single DocType "Attendance Machine Setting":
- parent-level connection settings shared by all machines
  (default_port, timeout, force_udp, ommit_ping)
- child table `machines` (Attendance Machine Detail):
  device_name (unique identifier), ip_address, enable, master_device,
  location, model

All consumers (utilities.py, biometric_sync.py, web UIs) must go through
get_machines() / get_machine() so the storage model stays in one place.
The public machine identifier is `device_name` (exposed as `name` for
backward compatibility with JS that treats `name` as an opaque id).
"""

import frappe
from frappe import _


def _get_settings():
    return frappe.get_cached_doc("Attendance Machine Setting")


def _row_to_dict(row, settings):
    return {
        # `name` kept for backward compatibility — JS passes it back as machine_name
        "name": row.device_name,
        "device_name": row.device_name,
        "ip_address": row.ip_address,
        "port": settings.default_port or 4370,
        "timeout": settings.timeout or 10,
        # bool(...) — do NOT use `or True`, that would force the value on
        "force_udp": bool(settings.force_udp),
        "ommit_ping": bool(settings.ommit_ping),
        "enable": bool(row.enable),
        "master_device": bool(row.master_device),
        "location": row.location or "",
        "model": row.model or "",
    }


def get_machines(enabled_only=False):
    """Return all machines as list of dicts (parent connection settings merged in)."""
    settings = _get_settings()
    machines = []
    for row in settings.machines or []:
        if enabled_only and not row.enable:
            continue
        machines.append(_row_to_dict(row, settings))
    return machines


def get_machine(machine_name):
    """Resolve one machine by device_name. Raises if not found."""
    settings = _get_settings()
    for row in settings.machines or []:
        if row.device_name == machine_name:
            return _row_to_dict(row, settings)
    frappe.throw(_("Attendance machine not found: {0}").format(machine_name))

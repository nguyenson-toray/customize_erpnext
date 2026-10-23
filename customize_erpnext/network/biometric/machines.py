# -*- coding: utf-8 -*-
"""
Central access layer for attendance machine configuration.

Machines are stored in the Single DocType "Attendance Machine Setting":
- parent-level connection settings shared by all machines
  (default_port, timeout, force_udp, ommit_ping)
- child table `machines` (Attendance Machine Detail):
  device_name (unique identifier), ip_address, comm_password, enable,
  location, model, and the door-controller block
  (is_door_control, unlock_seconds, sensor_installed, sensor_type, allow_hold_close)

All consumers (utilities.py, biometric_sync.py, web UIs) must go through
get_machines() / get_machine() so the storage model stays in one place.
The public machine identifier is `device_name` (exposed as `name` for
backward compatibility with JS that treats `name` as an opaque id).

Door controllers (`is_door_control`) share the table but are kept apart from
attendance: get_machines() leaves them out and get_machine() refuses them
unless the caller opts in. Only /door_control (network/door/control.py) and the
"Sync Fingerprint From ERP To Attendance Machines" dialog opt in.
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
        # ZKTeco comm key -> zk_device.build_zk_cfg; strip it (public_machine) before a
        # machine dict goes back to the browser
        "password": row.get("comm_password") or None,
        "port": settings.default_port or 4370,
        "timeout": settings.timeout or 10,
        # bool(...) — do NOT use `or True`, that would force the value on.
        # Door controllers (F21Lite) ALWAYS use UDP: over TCP a reconnect right after a
        # disconnect fails (BrokenPipe) — see network/door/control.py. The Setting's
        # Force UDP is for the attendance machines only (unticked 23/10/2026).
        "force_udp": True if row.is_door_control else bool(settings.force_udp),
        "ommit_ping": bool(settings.ommit_ping),
        "enable": bool(row.enable),
        "location": row.location or "",
        "model": row.model or "",
        "is_door_control": bool(row.is_door_control),
        "unlock_seconds": int(row.unlock_seconds or 5),
        "sensor_installed": bool(row.get("sensor_installed")),
        "sensor_type": row.sensor_type or "None",
        # a sensor counts only on doors where one is really wired (Sensor Installed)
        "has_door_sensor": bool(row.get("sensor_installed")) and (row.sensor_type or "None") in ("NO", "NC"),
        "allow_hold_close": bool(row.allow_hold_close),
        # Door Alert Setting watches this door (default on)
        "send_door_alerts": bool(row.send_door_alerts) if row.get("send_door_alerts") is not None else True,
    }


def public_machine(machine):
    """Machine dict without secrets, for API responses."""
    return {k: v for k, v in machine.items() if k != "password"}


def get_machines(enabled_only=False, include_door=False, door_only=False):
    """Return machines as list of dicts (parent connection settings merged in).

    Door controllers are left out unless `include_door` (attendance + doors)
    or `door_only` (doors alone) is passed.
    """
    settings = _get_settings()
    machines = []
    for row in settings.machines or []:
        if enabled_only and not row.enable:
            continue
        if door_only and not row.is_door_control:
            continue
        if row.is_door_control and not (include_door or door_only):
            continue
        machines.append(_row_to_dict(row, settings))
    return machines


def get_machine(machine_name, allow_door=False):
    """Resolve one machine by device_name. Raises if not found.

    A door controller is refused unless `allow_door` — every attendance
    function (re-sync into Employee Checkin, reboot, clock sync…) resolves its
    machine here, so this one check keeps door devices out of all of them.
    """
    settings = _get_settings()
    for row in settings.machines or []:
        if row.device_name == machine_name:
            if row.is_door_control and not allow_door:
                frappe.throw(
                    _("{0} is a door controller and cannot be used by attendance functions").format(machine_name)
                )
            return _row_to_dict(row, settings)
    frappe.throw(_("Attendance machine not found: {0}").format(machine_name))


def check_door_machine_access(machine):
    """Pushing fingerprints to a door controller grants physical access:
    only the Door Control role may do it."""
    if machine.get("is_door_control"):
        frappe.only_for("Door Control")

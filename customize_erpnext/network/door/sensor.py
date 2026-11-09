# -*- coding: utf-8 -*-
"""
ESP32 door sensors: doors that are only watched (open / closed), no lock, no F21.

Each board (ESP32-C6 Super Mini + magnetic sensor) posts its state over Wi-Fi to
`report` below: at once when the door changes (retried every 5 s, always the
latest state), a heartbeat every 60 s, and once at boot. ERPNext never calls the
board. Documentation: network/door/README.md, section "Door sensors (ESP32)".

Contract (the firmware is written against it)

    POST /api/method/customize_erpnext.network.door.sensor.report
    Authorization: token <api_key>:<api_secret>        (user with the Door Sensor role)
    {"door_id": "KHO-01", "state": "open|closed|fault", "event": "boot|change|heartbeat",
     "age_ms": 120, "rssi": -61, "ip": "10.0.1.80", "fw": "1.0.0"}
    -> 200 {"message": {"ok": true, "changed": <bool>}}

The board treats anything but HTTP 200 as a failure and sends again, so every
report that was handled -- duplicates, a disabled sensor, an unknown door_id --
answers 200. Errors only for: not authenticated, not permitted, invalid data.

Unknown door_id (decision 02/11/2026): the sensor is added as a Door Sensor with
enabled = 0 and logged once (Error Log "Door Sensor"); the board gets 200 with
ok = false. An admin only ticks Enabled (and types the Location) to accept it.
Throwing instead would make the board resend every 5 s forever and fill the
Error Log. At most MAX_PENDING disabled sensors are created this way; above that
the report is refused (protects against a leaked key inventing door_ids).

Alerts are NOT sent from here (the request must stay fast): alerts.tick reads
Door Sensor Event + Door Sensor (see alerts.py). This module imports nothing
from control.py / alerts.py, both import it.
"""

import hashlib
import re
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime
from frappe.utils.synchronization import filelock

ROLE = "Door Sensor"
STATES = ("open", "closed", "fault")
EVENTS = ("boot", "change", "heartbeat")
MAX_AGE_MS = 24 * 3600 * 1000        # a larger age_ms is treated as 0 (clock / firmware bug)
SENSOR_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
MAX_PENDING = 20                     # disabled Door Sensors before unknown door_ids are refused
LOCK_TIMEOUT_S = 10
DEFAULT_OFFLINE_MINUTES = 5


# ---------------------------------------------------------------------------
# endpoint
# ---------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def report(door_id=None, state=None, event=None, age_ms=0, rssi=None, ip=None, fw=None, **kwargs):
    """State report of one ESP32 door sensor. See the module docstring for the contract."""
    frappe.only_for(ROLE)

    door_id = str(door_id or "").strip()
    state = str(state or "").strip().lower()
    event = str(event or "").strip().lower()
    if not SENSOR_ID_RE.match(door_id):
        frappe.throw(_("Invalid door_id: letters, digits, '.', '_' and '-' only, at most 32"))
    if state not in STATES:
        frappe.throw(_("Invalid state {0}: expected open, closed or fault").format(repr(state)[:40]))
    if event not in EVENTS:
        frappe.throw(_("Invalid event {0}: expected boot, change or heartbeat").format(repr(event)[:40]))
    age = _age_ms(age_ms)

    now = now_datetime()
    diag = {
        "last_seen": now,
        "sensor_ip": str(ip or "").strip()[:45] or None,
        "sensor_rssi": cint(rssi) if rssi not in (None, "") else None,
        "sensor_fw": str(fw or "").strip()[:32] or None,
    }

    # two reports of one board may overlap (a retry while the next change goes out)
    with filelock(_lock_name(door_id), timeout=LOCK_TIMEOUT_S):
        row = frappe.db.get_value("Door Sensor", door_id, ["name", "enabled", "last_state"], as_dict=True)
        if not row:
            _add_unknown(door_id, state, diag)
            return {"ok": False, "changed": False, "reason": "unknown door_id, added disabled for approval"}
        if not row.enabled:
            frappe.db.set_value("Door Sensor", row.name, diag, update_modified=False)
            return {"ok": False, "changed": False, "reason": "disabled"}

        previous = row.last_state or "unknown"
        changed = state != previous
        if changed:
            at = now - timedelta(milliseconds=age)
            diag.update(last_state=state, last_state_change=at)
            frappe.get_doc({
                "doctype": "Door Sensor Event",
                "door_sensor": row.name,
                "state": state,
                "previous_state": previous,
                "event_time": at,
                "event": event,
                "received_at": now,
            }).insert(ignore_permissions=True)
        frappe.db.set_value("Door Sensor", row.name, diag, update_modified=False)

    return {"ok": True, "changed": changed}


def _age_ms(value):
    try:
        age = int(float(value or 0))
    except (TypeError, ValueError):
        frappe.throw(_("Invalid age_ms: expected a whole number of milliseconds"))
    return age if 0 <= age <= MAX_AGE_MS else 0


def _lock_name(door_id):
    return "door_sensor_" + hashlib.md5(door_id.lower().encode()).hexdigest()[:12]


def _add_unknown(door_id, state, diag):
    if frappe.db.count("Door Sensor", {"enabled": 0}) >= MAX_PENDING:
        frappe.log_error(title="Door Sensor", message=f"Report from unknown door_id {door_id!r} refused: "
                         f"{MAX_PENDING} disabled Door Sensors already wait for approval")
        frappe.throw(_("Unknown door_id {0}: too many sensors are waiting for approval").format(door_id))
    doc = frappe.get_doc({
        "doctype": "Door Sensor",
        "sensor_id": door_id,
        "enabled": 0,
        "send_door_alerts": 1,
        "note": _("Added automatically on {0}: a board reported with this Sensor ID. Tick Enabled to accept it.").format(
            frappe.utils.format_datetime(diag["last_seen"])),
    })
    try:
        doc.insert(ignore_permissions=True)
    except frappe.ValidationError as e:
        # e.g. the id is the Device Name of an F21 door: refuse, the board config is wrong
        frappe.log_error(title="Door Sensor", message=f"Report from door_id {door_id!r} refused: {e}")
        raise
    frappe.db.set_value("Door Sensor", doc.name, diag, update_modified=False)
    frappe.log_error(title="Door Sensor", message=f"Unknown door_id {door_id!r} (state {state}, IP {diag['sensor_ip']}, "
                     f"fw {diag['sensor_fw']}): added as a disabled Door Sensor. Tick Enabled to accept it.")


# ---------------------------------------------------------------------------
# reading (shared by control.py and alerts.py; no permission check here)
# ---------------------------------------------------------------------------

def offline_after_minutes():
    """A sensor is offline once nothing was received for this long (Door Alert Setting)."""
    value = cint(frappe.db.get_single_value("Door Alert Setting", "offline_after_minutes"))
    return value if value > 0 else DEFAULT_OFFLINE_MINUTES


def get_sensors(enabled_only=True):
    filters = {"enabled": 1} if enabled_only else {}
    return frappe.get_all(
        "Door Sensor",
        filters=filters,
        fields=["name", "location", "enabled", "send_door_alerts", "last_state", "last_state_change",
                "last_seen", "sensor_ip", "sensor_rssi", "sensor_fw"],
        order_by="location asc, name asc",
    )


def is_online(sensor, now=None, minutes=None):
    if not sensor.last_seen:
        return False
    now = now or now_datetime()
    minutes = minutes or offline_after_minutes()
    return now - get_datetime(sensor.last_seen) <= timedelta(minutes=minutes)


def label(sensor):
    return sensor.location or sensor.name


def mark_unknown(name, last_seen):
    """Offline: the last state is no longer known. Conditional on last_seen so a report
    that arrived meanwhile is never overwritten."""
    frappe.db.sql(
        """update `tabDoor Sensor` set last_state = 'unknown'
        where name = %s and last_state != 'unknown' and (last_seen <=> %s)""",
        (name, last_seen),
    )


def page_cards(show_ip=False):
    """Enabled sensors as /door_control cards (kind "sensor"), shaped like the door payload."""
    now = now_datetime()
    minutes = offline_after_minutes()
    cards = []
    for s in get_sensors():
        online = is_online(s, now, minutes)
        state = s.last_state if online else None
        cards.append({
            "kind": "sensor",
            "device_name": s.name,
            "location": s.location or "",
            "ip_address": (s.sensor_ip or "") if show_ip else "",
            "online": online,
            "sensor": state if state in ("open", "closed") else None,
            "fault": state == "fault",
            "has_door_sensor": True,
            "last_seen": str(s.last_seen) if s.last_seen else None,
            "last_state_change": str(s.last_state_change) if s.last_state_change else None,
            "rssi": s.sensor_rssi,
            "can_unlock": False,
            "allow_hold_close": False,
            "unlock_seconds": 0,
            "open_remaining": 0,
            "hold": False,
            "last": None,
        })
    return cards


def timeline_events(names, limit):
    if not names:
        return []
    rows = frappe.db.sql(
        """select door_sensor, state, previous_state, event_time
        from `tabDoor Sensor Event` where door_sensor in %(names)s
        order by event_time desc limit %(limit)s""",
        {"names": list(names), "limit": limit},
        as_dict=True,
    )
    return [
        {
            "kind": "sensor",
            "timestamp": r.event_time,
            "device_name": r.door_sensor,
            "state": r.state,
            "previous_state": r.previous_state,
            "who": r.state,
        }
        for r in rows
    ]

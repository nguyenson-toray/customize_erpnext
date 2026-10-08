# -*- coding: utf-8 -*-
"""
/door_control — open / close doors driven by ZKTeco F21Lite controllers.
Full documentation (config, measured device facts, traps, tests): api/door_control.md

Door controllers are rows of Attendance Machine Setting with `is_door_control`
ticked. They are kept apart from attendance (see api/attendance_machines.py):
this module is the only place that talks to them besides the fingerprint push
dialog. Every endpoint requires the `Door Control` role.

Facts measured on a real F21Lite (fw 6.60, ZMM220_TFT) on 2026-10-08:
- pyzk only has `unlock(seconds)`: it pulses the lock relay for N seconds.
  The device ACKs `unlock(0)` too, but whether that locks early is NOT
  verified — "Hold open" / "Close" are therefore behind `allow_hold_close`.
- CMD_DOORSTATE_RRQ returns one byte from the device's sensor input, not
  the relay (it does not change while unlocked). The lock in use, ZKTeco
  LB-35 (fail-safe bolt, re-lock delay 0/3/6 s set on the lock), has a bolt
  status sensor (NO/COM): wired to that input with the device's Door Sensor
  Mode = NO, the byte is the REAL lock state, fingerprint opens included.
  Read only when the row's Sensor Type is NO/NC, and trusted only when
  the device's Door Sensor Mode (option DSM) matches it.
- A software unlock writes NO log on the device, hence Door Control Action.
- Over TCP a reconnect right after a disconnect fails (BrokenPipe); UDP
  (the Setting's force_udp) reconnects fine. Retries cover both.

Without the sensor, the lock state shown is the one ERP knows: "open for N
more seconds" after a command sent from here (the real window is N + the
lock's re-lock delay). With the sensor, the page shows the bolt state.
"""

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor

import frappe
from frappe import _
from frappe.utils import add_days, get_fullname, getdate, now_datetime
from frappe.utils.synchronization import filelock

from customize_erpnext.api.attendance_machines import get_machine, get_machines
from customize_erpnext.api.biometric_sync import _build_zk_device, _connect_zk
from customize_erpnext.api.door_access import store_door_punches

ROLE = "Door Control"

PROBE_TIMEOUT_S = 3          # status check: fail fast, an offline door must not stall the page
COMMAND_TIMEOUT_S = 5        # unlock / close
FETCH_TIMEOUT_S = 15         # reading the whole log takes longer
CONNECT_ATTEMPTS = 2
RETRY_DELAY_S = 1.5
STATUS_CACHE_S = 8           # many open browsers -> one probe per door every 8 s
HOLD_OPEN_SECONDS = 15 * 60  # "Hold open" = one long unlock; firmware maximum not verified
# 08/10/2026: "Hold open" / "Close" switched off for everyone until verified on a real
# lock (max unlock time and whether unlock(0) re-locks early are both unknown). The
# buttons stay visible but disabled; flip to True once verified.
HOLD_CLOSE_ENABLED = False
FETCH_RANGE_DAYS = 30
TIMELINE_LIMIT = 150

# Raw CMD_DOORSTATE_RRQ byte -> bolt state from the LB-35 status sensor.
# UNVERIFIED: no sensor is wired yet. Both devices answer 0x01 with no sensor
# configured (DSM=2) and with NO + nothing wired, i.e. 0x01 is the device's
# "normal / closed" reading, hence 1 = locked. Calibrate once a sensor is wired
# (swap the values if reversed); the page also shows the raw byte in a tooltip.
SENSOR_STATES = {1: "locked", 0: "unlocked"}
SENSOR_SETTLE_S = 0.8        # let the bolt move before reading the sensor after a command
# Device option `DSM` (Door Sensor Mode, set on the device menu) -> Sensor Type of the Setting.
# Measured on F21Lite fw 6.60, 08/10/2026: both untouched devices read DSM=2 (factory
# default = no sensor) and both read DSM=0 after "NO" was chosen on the device menu.
DEVICE_SENSOR_MODES = {"0": "NO", "1": "NC", "2": "None"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _check_access():
    frappe.only_for(ROLE)


def _doors():
    return get_machines(enabled_only=True, door_only=True)


def _door(device_name):
    door = get_machine(device_name, allow_door=True)
    if not door["is_door_control"]:
        frappe.throw(_("{0} is not a door controller").format(device_name))
    if not door["enable"]:
        frappe.throw(_("{0} is disabled in Attendance Machine Setting").format(device_name))
    return door


def _cfg(door, timeout):
    cfg = _build_zk_device(frappe._dict(door))
    cfg["timeout"] = timeout
    return cfg


def _key(kind, device_name):
    # device names carry spaces / Vietnamese letters: hash them for cache keys and lock files
    return f"door_control:{kind}:{hashlib.md5(device_name.encode()).hexdigest()[:12]}"


def _connect(cfg):
    """Pure pyzk (no frappe calls) so it can run in worker threads."""
    last_err = None
    for attempt in range(CONNECT_ATTEMPTS):
        try:
            return _connect_zk(cfg)
        except Exception as e:
            last_err = e
            if attempt + 1 < CONNECT_ATTEMPTS:
                time.sleep(RETRY_DELAY_S)
    raise ConnectionError(f"{cfg['ip']}: {last_err}")


def _read_sensor(conn):
    from zk import const

    resp = conn._ZK__send_command(const.CMD_DOORSTATE_RRQ, b"", 1024)
    data = conn._ZK__data
    if resp.get("status") and data:
        return data[0]
    return None


def _read_option(conn, key):
    """Read one device option ("DSM=2" -> "2"); None when the device has no such key."""
    from zk import const

    resp = conn._ZK__send_command(const.CMD_OPTIONS_RRQ, (key + "\x00").encode(), 1024)
    if not resp.get("status"):
        return None
    raw = conn._ZK__data.split(b"\x00")[0].decode(errors="replace")
    return raw.split("=", 1)[1].strip() if "=" in raw else None


def _read_sensor_and_mode(conn):
    return _read_sensor(conn), DEVICE_SENSOR_MODES.get(_read_option(conn, "DSM"))


def _run(cfg, action):
    """Connect, run `action(conn)`, always disconnect. Thread-safe (no frappe)."""
    conn = _connect(cfg)
    try:
        return action(conn)
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass


def _probe(door):
    """Online check (+ sensor byte when wired). Runs in a worker thread."""
    started = time.time()
    try:
        raw, mode = _run(
            _cfg(door, PROBE_TIMEOUT_S),
            lambda conn: _read_sensor_and_mode(conn) if door["has_door_sensor"] else (None, None),
        )
        return {"online": True, "sensor_raw": raw, "device_sensor_mode": mode,
                "response_ms": int((time.time() - started) * 1000)}
    except Exception as e:
        return {"online": False, "error": str(e)}


def _probe_all(doors, force=False):
    """Probe results per device_name, served from cache when fresh."""
    results, todo = {}, []
    for door in doors:
        cached = None if force else frappe.cache.get_value(_key("probe", door["device_name"]))
        if cached:
            results[door["device_name"]] = cached
        else:
            todo.append(door)

    if todo:
        with ThreadPoolExecutor(max_workers=min(len(todo), 8)) as pool:
            for door, res in zip(todo, pool.map(_probe, todo)):
                res["checked_at"] = str(now_datetime())
                results[door["device_name"]] = res
                frappe.cache.set_value(_key("probe", door["device_name"]), res, expires_in_sec=STATUS_CACHE_S)
    return results


def _set_open(door, seconds, hold=False):
    until = time.time() + seconds
    frappe.cache.set_value(
        _key("open", door["device_name"]), {"until": until, "hold": hold}, expires_in_sec=int(seconds) + 2
    )


def _clear_open(door):
    frappe.cache.delete_value(_key("open", door["device_name"]))


def _open_state(door):
    state = frappe.cache.get_value(_key("open", door["device_name"])) or {}
    remaining = max(0, int(round((state.get("until") or 0) - time.time())))
    return remaining, bool(state.get("hold")) and remaining > 0


def _last_activity(door):
    """Newest of: a command sent from ERP, a punch read from the device."""
    action = frappe.db.sql(
        """select timestamp, action, result, user_full_name, user
        from `tabDoor Control Action` where device_name=%s order by timestamp desc limit 1""",
        door["device_name"],
        as_dict=True,
    )
    punch = frappe.db.sql(
        """select timestamp, user_id, employee_name
        from `tabDoor Access Log` where device_ip=%s order by timestamp desc limit 1""",
        door["ip_address"],
        as_dict=True,
    )
    candidates = []
    if action:
        a = action[0]
        candidates.append({"timestamp": a.timestamp, "kind": "erp", "action": a.action,
            "result": a.result, "who": a.user_full_name or a.user})
    if punch:
        p = punch[0]
        candidates.append({"timestamp": p.timestamp, "kind": "fingerprint",
            "who": p.employee_name or p.user_id, "matched": bool(p.employee_name)})
    if not candidates:
        return None
    last = max(candidates, key=lambda c: c["timestamp"])
    last["timestamp"] = str(last["timestamp"])
    return last


def _door_payload(door, probe):
    remaining, hold = _open_state(door)
    sensor_raw = probe.get("sensor_raw")
    device_mode = probe.get("device_sensor_mode")
    # the byte only means "locked/unlocked" when the device reads the input the way
    # the lock is wired: a mode mismatch makes the sensor value meaningless
    mismatch = bool(door["has_door_sensor"] and device_mode and device_mode != door["sensor_type"])
    return {
        "device_name": door["device_name"],
        "location": door["location"],
        "ip_address": door["ip_address"],
        "model": door["model"],
        "unlock_seconds": door["unlock_seconds"],
        "has_door_sensor": door["has_door_sensor"],
        "sensor_type": door["sensor_type"],
        "device_sensor_mode": device_mode,
        "sensor_mode_mismatch": mismatch,
        "allow_hold_close": door["allow_hold_close"],
        "hold_close_enabled": HOLD_CLOSE_ENABLED,
        "online": bool(probe.get("online")),
        "error": probe.get("error"),
        "response_ms": probe.get("response_ms"),
        "checked_at": probe.get("checked_at"),
        "sensor": SENSOR_STATES.get(sensor_raw) if (sensor_raw is not None and not mismatch) else None,
        "sensor_raw": sensor_raw,
        "open_remaining": remaining,
        "hold": hold,
        "last": _last_activity(door),
    }


def _log_action(door, action, seconds, ok, error=None):
    frappe.get_doc({
        "doctype": "Door Control Action",
        "timestamp": now_datetime(),
        "action": action,
        "result": "Success" if ok else "Failed",
        "device_name": door["device_name"],
        "device_ip": door["ip_address"],
        "seconds": seconds,
        "user": frappe.session.user,
        "user_full_name": get_fullname(frappe.session.user),
        "error": (str(error)[:1000] if error else None),
    }).insert(ignore_permissions=True)


def _command(door, action_label, seconds, zk_action, open_for=None, hold=False):
    """Send one lock command under a per-door lock, log it, update the ERP lock state.

    Returns a result dict instead of throwing, so the failed attempt is still
    logged (a throw would roll the Door Control Action row back).
    """
    ok, error = True, None
    try:
        with filelock(_key("lock", door["device_name"]).replace(":", "_"), timeout=COMMAND_TIMEOUT_S * 3):
            _run(_cfg(door, COMMAND_TIMEOUT_S), zk_action)
    except Exception as e:
        ok, error = False, e
        frappe.log_error(f"{action_label} {door['device_name']} ({door['ip_address']}): {e}", "Door Control")

    _log_action(door, action_label, seconds, ok, error)
    if ok:
        if open_for:
            _set_open(door, open_for, hold=hold)
        else:
            _clear_open(door)
        frappe.cache.delete_value(_key("probe", door["device_name"]))

    if ok and door["has_door_sensor"]:
        # read the bolt back so the page shows the real state right away
        time.sleep(SENSOR_SETTLE_S)
        probe = _probe(door)
        probe["checked_at"] = str(now_datetime())
    else:
        probe = {"online": ok, "error": str(error) if error else None, "checked_at": str(now_datetime())}
    return {"success": ok, "message": str(error) if error else None, "door": _door_payload(door, probe)}


def _require_hold_close(door):
    if not HOLD_CLOSE_ENABLED:
        frappe.throw(_("Hold open / Close is temporarily unavailable"))
    if not door["allow_hold_close"]:
        frappe.throw(_("Hold open / Close is not enabled for {0}").format(door["device_name"]))


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_doors(force=0):
    """Every enabled door controller with its live status."""
    _check_access()
    doors = _doors()
    probes = _probe_all(doors, force=frappe.utils.cint(force))
    return {
        "doors": [_door_payload(d, probes.get(d["device_name"], {})) for d in doors],
        "server_time": str(now_datetime()),
    }


@frappe.whitelist(methods=["POST"])
def unlock_door(device_name):
    """Open the lock for the door's `unlock_seconds`, then the device locks it again."""
    _check_access()
    door = _door(device_name)
    secs = door["unlock_seconds"]
    return _command(door, "Unlock", secs, lambda conn: conn.unlock(secs), open_for=secs)


@frappe.whitelist(methods=["POST"])
def hold_open(device_name):
    """Keep the lock open for HOLD_OPEN_SECONDS (until Close is pressed)."""
    _check_access()
    door = _door(device_name)
    _require_hold_close(door)
    return _command(
        door, "Hold Open", HOLD_OPEN_SECONDS,
        lambda conn: conn.unlock(HOLD_OPEN_SECONDS), open_for=HOLD_OPEN_SECONDS, hold=True,
    )


@frappe.whitelist(methods=["POST"])
def close_door(device_name):
    """Lock now: unlock(0). Only offered where verified (allow_hold_close)."""
    _check_access()
    door = _door(device_name)
    _require_hold_close(door)
    return _command(door, "Close", 0, lambda conn: conn.unlock(0))


@frappe.whitelist(methods=["POST"])
def unlock_all():
    """Emergency: open every enabled door at once (2-step confirmation is on the page)."""
    _check_access()
    doors = _doors()
    if not doors:
        frappe.throw(_("No door controller is enabled"))

    def send(door):
        secs = door["unlock_seconds"]
        try:
            _run(_cfg(door, COMMAND_TIMEOUT_S), lambda conn: conn.unlock(secs))
            return None
        except Exception as e:
            return e

    # parallel: an offline door must not delay the others by its connect timeout
    with ThreadPoolExecutor(max_workers=min(len(doors), 8)) as pool:
        errors = list(pool.map(send, doors))

    results = []
    for door, error in zip(doors, errors):
        ok = error is None
        _log_action(door, "Unlock All", door["unlock_seconds"], ok, error)
        if ok:
            _set_open(door, door["unlock_seconds"])
            frappe.cache.delete_value(_key("probe", door["device_name"]))
        else:
            frappe.log_error(f"Unlock All {door['device_name']} ({door['ip_address']}): {error}", "Door Control")
        results.append({"device_name": door["device_name"], "success": ok, "message": str(error) if error else None})

    return {
        "results": results,
        "opened": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
    }


@frappe.whitelist(methods=["POST"])
def fetch_logs(device_name=None, force=0):
    """Read new punches from the door controllers into Door Access Log.

    Cheap when nothing happened: the device's record count is compared with the
    last fetch and the log is only downloaded when it changed. Logs on the
    device are never cleared.
    """
    _check_access()
    doors = [_door(device_name)] if device_name else _doors()
    force = frappe.utils.cint(force)
    to_d = getdate(now_datetime())
    from_d = getdate(add_days(to_d, -(FETCH_RANGE_DAYS - 1)))

    def read(conn, known):
        conn.read_sizes()
        count = conn.records
        if count == known:
            return count, None
        conn.disable_device()
        try:
            return count, conn.get_attendance() or []
        finally:
            conn.enable_device()

    results = []
    for door in doors:
        res = {"device_name": door["device_name"], "inserted": 0}
        count_key = _key("records", door["device_name"])
        known = None if force else frappe.cache.get_value(count_key)
        try:
            with filelock(_key("lock", door["device_name"]).replace(":", "_"), timeout=FETCH_TIMEOUT_S * 2):
                count, punches = _run(_cfg(door, FETCH_TIMEOUT_S), lambda conn: read(conn, known))
            if punches is not None:
                counts = store_door_punches(punches, door["ip_address"], from_d, to_d)
                res["inserted"] = counts["inserted"]
                res["no_employee"] = counts["no_employee"]
            res["success"] = True
            res["unchanged"] = punches is None
            frappe.cache.set_value(count_key, count)
        except Exception as e:
            res["success"] = False
            res["message"] = str(e)
            frappe.log_error(f"fetch_logs {door['device_name']} ({door['ip_address']}): {e}", "Door Control")
        results.append(res)

    return {
        "results": results,
        "inserted": sum(r["inserted"] for r in results),
        "failed": sum(1 for r in results if not r["success"]),
    }


@frappe.whitelist()
def get_timeline(device_name=None, limit=TIMELINE_LIMIT):
    """Fingerprint punches + ERP commands of the door controllers, newest first."""
    _check_access()
    doors = _doors()
    if device_name:
        doors = [d for d in doors if d["device_name"] == device_name]
    if not doors:
        return {"events": []}
    limit = min(frappe.utils.cint(limit) or TIMELINE_LIMIT, 500)

    ip_to_door = {d["ip_address"]: d["device_name"] for d in doors}
    names = [d["device_name"] for d in doors]

    punches = frappe.db.sql(
        """select user_id, employee, employee_name, timestamp, device_ip
        from `tabDoor Access Log` where device_ip in %(ips)s
        order by timestamp desc limit %(limit)s""",
        {"ips": list(ip_to_door), "limit": limit},
        as_dict=True,
    )
    actions = frappe.db.sql(
        """select timestamp, action, result, device_name, seconds, user, user_full_name, error
        from `tabDoor Control Action` where device_name in %(names)s
        order by timestamp desc limit %(limit)s""",
        {"names": names, "limit": limit},
        as_dict=True,
    )

    events = [
        {
            "kind": "fingerprint",
            "timestamp": p.timestamp,
            "device_name": ip_to_door.get(p.device_ip),
            "who": p.employee_name or p.user_id,
            "employee": p.employee,
            "user_id": p.user_id,
            "matched": bool(p.employee),
        }
        for p in punches
    ] + [
        {
            "kind": "erp" if a.result == "Success" else "failed",
            "timestamp": a.timestamp,
            "device_name": a.device_name,
            "who": a.user_full_name or a.user,
            "action": a.action,
            "seconds": a.seconds,
            "error": a.error,
        }
        for a in actions
    ]
    events.sort(key=lambda e: e["timestamp"], reverse=True)
    events = events[:limit]
    for e in events:
        e["timestamp"] = str(e["timestamp"])
    return {"events": events}

"""Shared pyzk helpers for attendance machines and door controllers.

One copy of: device config, connect, read attendance, push users + templates,
name shortening and finger names — previously duplicated across
api/biometric_sync.py, api/utilities.py and api/biometric_resync.py.

🔴 Functions marked "pure pyzk" make no frappe.* call that touches
frappe.local (db, cache, session, log_error…) so they are safe in worker threads.
"""

import base64
import socket
import time

import frappe

CONNECT_RETRIES = 3          # a device may be briefly busy with another job
CONNECT_RETRY_DELAY_S = 5

FINGER_NAMES = {
    0: "Left Little", 1: "Left Ring", 2: "Left Middle", 3: "Left Index", 4: "Left Thumb",
    5: "Right Thumb", 6: "Right Index", 7: "Right Middle", 8: "Right Ring", 9: "Right Little",
}


def finger_name(finger_index):
    """Map finger index (0-9) to human-readable name."""
    return FINGER_NAMES.get(int(finger_index), f"Finger {finger_index}")


def shorten_name(full_name, max_length=24):
    """Vietnamese name -> ASCII, initials + last word when longer than the device allows."""
    try:
        from unidecode import unidecode
        text = unidecode(full_name or "")
    except ImportError:
        text = (full_name or "").encode("ascii", "ignore").decode()
    text = " ".join(text.split()).strip()
    if len(text) > max_length:
        parts = text.split()
        if len(parts) > 1:
            initials = "".join(p[0].upper() for p in parts[:-1])
            return f"{initials} {parts[-1]}"
        return text[:max_length]
    return text


def build_zk_cfg(doc):
    """ZK device config dict from a machine row (Attendance Machine Setting shape).

    `password` is the numeric comm key (the ZK protocol has no username);
    attendance machines leave it unset, the IT door controller may use one.
    """
    return {
        "ip": doc.ip_address,
        "port": int(doc.port or 4370),
        "timeout": int(doc.timeout or 10),
        "force_udp": bool(doc.force_udp),
        "ommit_ping": bool(doc.ommit_ping),
        "password": int(doc.password or 0),
    }


def bulk_read_cfg(machine):
    """Config for reading the whole attendance log of an attendance machine.

    TCP, not the Setting's force_udp: measured 23/10/2026 on Machine 1 (32,939 logs)
    UDP took 142 s, TCP ~9 s (what the old sync tool used: pyzk defaults, timeout 30).
    """
    cfg = build_zk_cfg(machine)
    cfg.update(force_udp=False, ommit_ping=False, timeout=30)
    return cfg


def connect_zk(device_cfg):
    """Connect to a ZK device. Returns conn or raises. Pure pyzk."""
    from zk import ZK
    zk = ZK(
        device_cfg["ip"],
        port=device_cfg["port"],
        timeout=device_cfg["timeout"],
        password=int(device_cfg.get("password") or 0),
        force_udp=device_cfg["force_udp"],
        ommit_ping=device_cfg["ommit_ping"],
    )
    conn = zk.connect()
    if not conn:
        raise ConnectionError(f"Cannot connect to {device_cfg['ip']}")
    return conn


NEAR_FULL_RATIO = 0.95       # log count this close to capacity: a ring-buffer device may overwrite
                             # old punches and keep the count flat -> never trust "unchanged" there


def near_full(count, capacity):
    """Unknown capacity counts as full (safe side: read everything)."""
    return not capacity or count >= capacity * NEAR_FULL_RATIO


def _connect_with_retry(cfg, label):
    """connect_zk with CONNECT_RETRIES: the automatic log pull, a page action or a door
    probe may hold the device for a few seconds. Pure pyzk."""
    last_err = None
    for _attempt in range(CONNECT_RETRIES):
        try:
            return connect_zk(cfg)
        except Exception as e:
            last_err = e
            time.sleep(CONNECT_RETRY_DELAY_S)
    raise ConnectionError(f"Cannot connect to {label} after {CONNECT_RETRIES} attempts: {last_err}")


def _parse_attendance(conn, data, record_size, users):
    """Decode a CMD_ATTLOG_RRQ buffer (without its 4-byte size header) into zk Attendance.

    Same unpacking and uid/user_id fallbacks as pyzk 0.9 ZK.get_attendance (base.py),
    with dict lookups instead of a filter() over the user list per record.
    `users` is only needed (and only read) for 8/16-byte records; the 40-byte format
    of all 7 TIQN machines carries the user_id itself (measured 09/11/2026).
    🔴 Copied from pyzk 0.9 and uses its private _ZK__decode_time: after upgrading
    pyzk, re-run test_device_log_sync.py (it compares this parser with pyzk's).
    """
    from struct import unpack

    from zk.attendance import Attendance

    decode_time = conn._ZK__decode_time
    out = []
    if record_size == 8:
        by_uid = {}
        for u in users or []:
            by_uid.setdefault(u.uid, u)
        while len(data) >= 8:
            uid, status, timestamp, punch = unpack("HB4sB", data.ljust(8, b"\x00")[:8])
            data = data[8:]
            user = by_uid.get(uid)
            out.append(Attendance(user.user_id if user else str(uid), decode_time(timestamp), status, punch, uid))
    elif record_size == 16:
        by_uid, by_user_id = {}, {}
        for u in users or []:
            by_uid.setdefault(u.uid, u)
            by_user_id.setdefault(u.user_id, u)
        while len(data) >= 16:
            user_id, timestamp, status, punch, _reserved, _workcode = unpack(
                "<I4sBB2sI", data.ljust(16, b"\x00")[:16])
            data = data[16:]
            user_id = str(user_id)
            user = by_user_id.get(user_id)
            if user:
                uid = user.uid
            else:
                # pyzk compares the str user_id with the int uid here, so this never matches
                # there either; kept identical on purpose
                user = by_uid.get(user_id)
                uid, user_id = (user.uid, user.user_id) if user else (str(user_id), user_id)
            out.append(Attendance(user_id, decode_time(timestamp), status, punch, uid))
    else:
        while len(data) >= 40:
            uid, user_id, status, timestamp, punch, _space = unpack(
                "<H24sB4sB8s", data.ljust(40, b"\x00")[:40])
            data = data[40:]
            user_id = (user_id.split(b"\x00")[0]).decode(errors="ignore")
            out.append(Attendance(user_id, decode_time(timestamp), status, punch, uid))
    return out


def _read_logs(conn, label, clear_after=False):
    """Locked read of the whole attendance log over an open connection. Pure pyzk.

    disable_device -> read_sizes -> raw buffer (-> users only for 8/16-byte records)
    [-> clear] -> enable_device -> decode. Decoding after re-enabling keeps the machine
    locked 0.2–1.2 s less than pyzk's get_attendance (which also always downloads the
    user list: 0.75–2.2 s, unused for 40-byte records).
    Returns (attendances, warning, count); `count` is the log count read while the
    device was locked (no punch can slip in between), 0 after a clear.
    """
    from struct import unpack

    from zk import const

    warning = None
    attendances = []
    raw = None
    try:
        conn.disable_device()
        conn.read_sizes()
        count = conn.records
        if count:
            data, size = conn.read_with_buffer(const.CMD_ATTLOG_RRQ)
            if size >= 4:
                record_size = unpack("I", data[:4])[0] / count
                users = conn.get_users() if record_size in (8, 16) else None
                raw = (data[4:], record_size, users)
        if clear_after and raw:
            # decode BEFORE clearing: the punches must exist somewhere if decoding fails
            attendances = _parse_attendance(conn, *raw)
            raw = None
            conn.clear_attendance()
            count = 0
    finally:
        try:
            conn.enable_device()
        except Exception as e:
            warning = f"Failed to re-enable device {label}: {e}"
    if raw:
        attendances = _parse_attendance(conn, *raw)
    return attendances, warning, count


def read_attendance(cfg, label, clear_after=False):
    """Read all attendance logs from a device. Pure pyzk — safe in worker threads.

    Returns (attendances, warning). `warning` is set when the device could not be
    re-enabled afterwards (it would stay locked = no punches): the caller, in the
    main thread, must log it.
    `clear_after` deletes the logs on the device once read (Attendance Machine
    Setting.clear_from_device_on_fetch, kept 0: TIQN keeps the logs on the machines).
    """
    conn = _connect_with_retry(cfg, label)
    try:
        attendances, warning, _count = _read_logs(conn, label, clear_after=clear_after)
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass
    return attendances, warning


def read_attendance_if_changed(cfg, label, known_count=None, clear_after=False):
    """Automatic pull: read the log only when the device's log count moved. Pure pyzk.

    read_sizes() (one packet, 0.03–0.3 s, device NOT locked) gives the count. When it
    equals `known_count` (the count of the last clean full read, kept by the caller)
    and the device is not near capacity, the machine is left alone: records = None.
    Otherwise a full locked read. `known_count=None` always reads.
    Returns (records | None, warning, info) — info: pre_count (unlocked), rec_cap,
    count (after the read; = pre_count when skipped).
    """
    conn = _connect_with_retry(cfg, label)
    try:
        conn.read_sizes()
        info = {"pre_count": conn.records, "rec_cap": getattr(conn, "rec_cap", 0)}
        if (known_count is not None and info["pre_count"] == known_count
                and not near_full(info["pre_count"], info["rec_cap"])):
            info["count"] = info["pre_count"]
            return None, None, info
        attendances, warning, info["count"] = _read_logs(conn, label, clear_after=clear_after)
        return attendances, warning, info
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass


def fetch_attendance(cfg, label, clear_after=False):
    """read_attendance for main-thread callers (Tab 6 re-sync, door logs): logs the warning."""
    attendances, warning = read_attendance(cfg, label, clear_after=clear_after)
    if warning:
        frappe.log_error(warning)
    return attendances


def check_connection_fast(machine, timeout=2):
    """TCP reachability of a machine dict, cached 30 s. Safe in threads
    (cache errors are swallowed)."""
    ip_address = machine.get("ip_address")
    port = machine.get("port") or 4370
    cache_key = f"machine_conn_{ip_address}_{port}"
    try:
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return cached
    except Exception:
        pass

    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip_address, port))
        sock.close()
        response_time = round((time.time() - start) * 1000, 2)
        if result == 0:
            status = {"status": "online", "message": f"Connected ({response_time}ms)",
                      "response_time": response_time}
        else:
            status = {"status": "offline", "message": f"Connection failed (Error: {result})",
                      "response_time": 0}
    except Exception as e:
        return {"status": "error", "message": f"Connection error: {e}", "response_time": 0}

    try:
        frappe.cache().set_value(cache_key, status, expires_in_sec=30)
    except Exception:
        pass
    return status


def upsert_users(conn, users, on_result, retries=1):
    """Create or replace users (+ fingerprint templates) over ONE open connection.

    `conn` must already be connected and disabled. `users`: dicts with
    user_id, name, privilege, password, group_id and
    fingerprints=[{finger_index, template_data (base64)}].
    One get_users() for the whole list; existing users keep their uid
    (delete + set_user), new users get the next free uid.
    `on_result(user, success, fingerprints_sent, error)` is called once per user.
    """
    from zk.base import Finger, User

    existing_users = conn.get_users()
    users_by_id = {u.user_id: u for u in existing_users}
    next_uid = max((u.uid for u in existing_users), default=0) + 1

    for user in users:
        device_id = str(user["user_id"])
        last_error = None
        for _attempt in range(retries + 1):
            try:
                existing = users_by_id.get(device_id)
                if existing:
                    uid = existing.uid
                    # pass uid: user_id alone makes pyzk re-download the whole user list
                    conn.delete_user(uid=existing.uid, user_id=device_id)
                    time.sleep(0.1)
                else:
                    uid = next_uid
                    next_uid += 1

                short_name = shorten_name(user.get("name"), 24)
                privilege = user.get("privilege") or 0
                password = user.get("password") or ""
                group_id = user.get("group_id") or ""
                conn.set_user(uid=uid, name=short_name, privilege=privilege,
                              password=password, group_id=group_id, user_id=device_id)
                # save_user_template needs a real zk User (it repacks the user record);
                # building it locally avoids another get_users() round-trip
                zk_user = User(uid, short_name, privilege, password, group_id, device_id)
                # keep the map current so a duplicate device_id later in the
                # list (or a retry) reuses this uid instead of allocating
                users_by_id[device_id] = zk_user

                templates = {}
                for fp in user.get("fingerprints") or []:
                    if not fp.get("template_data"):
                        continue
                    try:
                        templates[int(fp["finger_index"])] = base64.b64decode(fp["template_data"])
                    except Exception:
                        continue
                fingers = [Finger(uid=uid, fid=fid, valid=True, template=tpl) for fid, tpl in templates.items()]
                if fingers:
                    conn.save_user_template(zk_user, fingers)

                on_result(user, True, len(fingers), None)
                last_error = None
                break
            except Exception as e:
                last_error = str(e)
                time.sleep(0.3)

        if last_error is not None:
            on_result(user, False, 0, last_error)

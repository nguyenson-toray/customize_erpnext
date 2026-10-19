# -*- coding: utf-8 -*-
"""
Telegram alerts for the door controllers of /door_control.

Settings: Single DocType "Door Alert Setting" (created OFF, no recipients).
Plan + decisions: see api/door_control.md (section "Telegram alerts").

How it runs
- `tick()` is a cron job every minute (hooks.py). With the setting off it reads
  one Single and returns — no device is contacted.
- Every `check_interval_minutes` it: probes the doors (offline / back online),
  reads new punches WITHOUT pausing the device (a door must never ignore a
  fingerprint because of this job), then turns the Door Control Action and
  Door Access Log rows created since the previous check into events, and sends
  them as ONE message per recipient.
- Once a day, at/after `daily_summary_time`, a summary of the day is sent.

Operations context (09/10/2026): during working hours the lock is switched OFF
by hand (bolt always released, ~1000 workers pass freely; only senior managers
may open doors). `erp_open_alert` / `fingerprint_alert` = Off / After Hours /
Always; one open still gives one line ("after hours" wins when it applies).
Only doors with "Send Door Alerts" ticked are watched; `mute_until` drops
messages (not queued) until that time.

Runtime state lives in the Setting's read-only fields (written with
update_modified=False, so an admin editing the form never hits a timestamp
conflict) and in cache keys (offline tracking only).
"""

import html
from datetime import datetime, time as dtime, timedelta

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime
from frappe.utils.file_lock import LockTimeoutError
from frappe.utils.synchronization import filelock

from customize_erpnext.api import door_control as dc

SETTING = "Door Alert Setting"
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"
SEND_TIMEOUT_S = 8
MAX_MESSAGE_CHARS = 3800      # Telegram hard limit is 4096
MAX_EVENT_LINES = 40          # beyond this: "... and N more"
# a punch older than this (by its own timestamp) is backlog — e.g. the first read
# of a device that was never fetched — and is not alerted, only stored
PUNCH_MAX_AGE_MIN = 30
# after hours a fingerprint / ERP open lets someone through in 5-15 s (+ the lock's
# 0/3/6 s re-lock delay): only a door seen open this long is "left open"
NOT_LOCKED_CONFIRM_MIN = 2


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _settings():
    return frappe.get_single(SETTING)


def _set_status(**values):
    frappe.db.set_value(SETTING, SETTING, values, update_modified=False)


def _to_time(value):
    """Time field values come back as timedelta from the DB, str from a form."""
    if isinstance(value, dtime):
        return value
    if isinstance(value, timedelta):
        secs = int(value.total_seconds()) % 86400
        return dtime(secs // 3600, (secs % 3600) // 60, secs % 60)
    return datetime.strptime(str(value or "00:00:00").split(".")[0], "%H:%M:%S").time()


def in_work_hours(dt, start, end):
    """True when `dt` falls in the working period; end < start = past midnight."""
    t, start, end = get_datetime(dt).time(), _to_time(start), _to_time(end)
    if start == end:
        return True
    if start < end:
        return start <= t < end
    return t >= start or t < end


def _esc(value):
    return html.escape(str(value if value is not None else ""))


def _fmt_time(dt, with_seconds=False):
    return get_datetime(dt).strftime("%H:%M:%S" if with_seconds else "%H:%M")


def _who(employee, employee_name, user_id):
    if employee:
        return f"{employee} {employee_name or ''}".strip()
    return _("ID {0}").format(user_id)


def _use_site_language():
    frappe.local.lang = frappe.db.get_single_value("System Settings", "language") or "vi"


def _label(door):
    """Short display name: the row's Location (e.g. "Main Hall"), else the device name."""
    return door.get("location") or door["device_name"]


def _watched_doors():
    """Enabled door controllers whose row has "Send Door Alerts" ticked."""
    return [d for d in dc._doors() if d.get("send_door_alerts", True)]


def _muted(settings, now):
    return bool(settings.mute_until and get_datetime(settings.mute_until) > get_datetime(now))


def _count_sent(settings, now, n=1):
    today = getdate(now)
    count = (settings.sent_count or 0) if str(settings.sent_count_date or "") == str(today) else 0
    _set_status(sent_count=count + n, sent_count_date=today, last_sent_at=now)


def _check_role():
    frappe.only_for(("System Manager", "Door Control"))


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _split(text):
    """Split on line breaks into chunks Telegram accepts."""
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > MAX_MESSAGE_CHARS and cur:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def send_telegram(settings, text, only_enabled=True):
    """Send `text` (HTML) to every enabled recipient. Returns one result per chat.
    Never raises: a Telegram outage must not break the job or the page."""
    import requests

    token = settings.get_password("bot_token", raise_exception=False)
    chats = [r for r in settings.recipients or [] if r.chat_id and (r.enabled or not only_enabled)]
    results = []
    for r in chats:
        res = {"label": r.label, "chat_id": r.chat_id, "ok": True, "error": None}
        if not token:
            res.update(ok=False, error=_("Bot Token is empty"))
            results.append(res)
            continue
        try:
            for chunk in _split(text):
                resp = requests.post(
                    TELEGRAM_URL.format(token=token),
                    json={"chat_id": r.chat_id, "text": chunk, "parse_mode": "HTML",
                          "disable_web_page_preview": True},
                    timeout=SEND_TIMEOUT_S,
                )
                data = resp.json() if resp.content else {}
                if not data.get("ok"):
                    raise RuntimeError(data.get("description") or f"HTTP {resp.status_code}")
        except Exception as e:
            # the token is part of the URL: never let it reach a log or the UI
            msg = str(e).replace(token, "<token>")
            res.update(ok=False, error=msg[:300])
        results.append(res)
    return results


def _record_send_errors(results):
    errors = [f"{r['label'] or r['chat_id']}: {r['error']}" for r in results if not r["ok"]]
    if errors:
        text = f"{now_datetime():%Y-%m-%d %H:%M} " + "; ".join(errors)
        _set_status(last_error=text[:1000])
        frappe.log_error(title="Door Alerts: Telegram", message=text)
    return not errors


@frappe.whitelist(methods=["POST"])
def send_test_message():
    """Button on Door Alert Setting. Works even while alerts are switched off."""
    _check_role()
    _use_site_language()
    settings = _settings()
    text = "✅ <b>{0}</b>\n{1}".format(
        _esc(_("Door alerts: test message")),
        _esc(_("Sent from ERP at {0} by {1}").format(
            f"{now_datetime():%d/%m/%Y %H:%M}", frappe.utils.get_fullname(frappe.session.user))),
    )
    results = send_telegram(settings, text)
    _record_send_errors(results)
    return {"results": results}


# ---------------------------------------------------------------------------
# event detection
# ---------------------------------------------------------------------------

def _offline_events(settings, doors, probes, now):
    """Offline for >= offline_after_minutes -> one event; back online -> one event."""
    events = []
    threshold = timedelta(minutes=settings.offline_after_minutes or 5)
    for door in doors:
        key = f"door_alerts:offline:{door['device_name']}"
        state = frappe.cache.get_value(key) or {}
        online = probes.get(door["device_name"], {}).get("online")
        if not online:
            since = get_datetime(state["since"]) if state.get("since") else now
            if not state:
                state = {"since": str(now), "alerted": False}
            if not state["alerted"] and now - since >= threshold:
                minutes = int((now - since).total_seconds() // 60)
                detail = f"{_esc(_label(door))} ({_esc(door['ip_address'])})"
                last = dc.last_sensor(door)
                if last:
                    at = get_datetime(last["at"])
                    detail += " · " + _("last reading: {0} at {1}").format(
                        _("<b>DOOR OPEN</b>") if last["state"] == "open" else _("door closed"),
                        at.strftime("%H:%M" if at.date() == now.date() else "%d/%m %H:%M"))
                events.append(("🔴", _("Door device offline for {0} minutes").format(minutes), detail))
                state["alerted"] = True
            frappe.cache.set_value(key, state)
        elif state:
            if state.get("alerted"):
                minutes = int((now - get_datetime(state["since"])).total_seconds() // 60)
                events.append(("🟢", _("Door device back online"),
                               _("{0} — offline for {1} minutes").format(_esc(_label(door)), minutes)))
            frappe.cache.delete_value(key)
    return events


def _not_locked_events(settings, doors, probes, now):
    """Door left open outside working hours (Door Sensor).

    Returns (events, keys_to_mark): the caller stamps `last_sent` on those keys
    only once the message went out (or alerts are muted), so a failed send is
    retried on the next run. Inside working hours every state is dropped
    silently (doors stand open by day on purpose).
    """
    events, to_mark = [], []
    repeat = timedelta(minutes=settings.not_locked_repeat_minutes or 30)
    confirm = timedelta(minutes=NOT_LOCKED_CONFIRM_MIN)
    working = in_work_hours(now, settings.work_start_time, settings.work_end_time)
    for door in doors:
        key = f"door_alerts:not_locked:{door['device_name']}"
        st = frappe.cache.get_value(key) or {}
        if working:
            if st:
                frappe.cache.delete_value(key)
            continue
        probe = probes.get(door["device_name"]) or {}
        state = dc.sensor_reading(door, probe)[0] if probe.get("online") else None
        if state is None:
            continue  # offline / no reading / Door Sensor Mode mismatch: keep the state
        label = _esc(_label(door))
        if state == "open":
            st = st or {"first_seen": str(now), "last_sent": None}
            first = get_datetime(st["first_seen"])
            if now - first >= confirm:
                if not st.get("last_sent"):
                    events.append(("🔴", _("Door left open after hours"),
                                   _("{0} (since {1})").format(label, _fmt_time(first))))
                    to_mark.append(key)
                elif now - get_datetime(st["last_sent"]) >= repeat:
                    minutes = int((now - first).total_seconds() // 60)
                    events.append(("🔴", _("Door still open"),
                                   _("{0} — for {1} minutes").format(label, minutes)))
                    to_mark.append(key)
            frappe.cache.set_value(key, st)
        else:
            if st.get("last_sent"):
                minutes = int((now - get_datetime(st["first_seen"])).total_seconds() // 60)
                events.append(("🟢", _("Door closed"), _("{0} (after {1} minutes)").format(label, minutes)))
            frappe.cache.delete_value(key)
    return events, to_mark


def _mark_not_locked_sent(keys, now):
    for key in keys:
        st = frappe.cache.get_value(key)
        if st:
            st["last_sent"] = str(now)
            frappe.cache.set_value(key, st)


def _action_events(settings, doors, since, until):
    if not doors:
        return []
    # only the doors currently enabled in the Setting
    rows = frappe.db.sql(
        """select timestamp, action, result, device_name, seconds, user_full_name, user, error
        from `tabDoor Control Action`
        where creation > %(since)s and creation <= %(until)s and device_name in %(names)s
        order by timestamp""",
        {"since": since, "until": until, "names": [d["device_name"] for d in doors]}, as_dict=True,
    )
    labels = {d["device_name"]: _esc(_label(d)) for d in doors}
    events = []
    all_groups = []   # one "open all" press = one event, never one line per door
    for r in rows:
        who = _esc(r.user_full_name or r.user)
        if r.action == "Unlock All":
            if settings.alert_unlock_all or settings.erp_open_alert == "Always":
                # rows of one press share the user and are milliseconds apart; a gap
                # (not the clock minute) separates presses, so 19:27:59/19:28:00 stay one
                g = all_groups[-1] if all_groups else None
                if not g or g["user"] != r.user or (get_datetime(r.timestamp) - g["last"]).total_seconds() > 10:
                    g = {"t": r.timestamp, "last": get_datetime(r.timestamp), "user": r.user, "who": who, "ok": 0, "bad": []}
                    all_groups.append(g)
                g["last"] = get_datetime(r.timestamp)
                if r.result == "Success":
                    g["ok"] += 1
                else:
                    g["bad"].append(labels.get(r.device_name) or _esc(r.device_name))
            continue
        if r.result == "Failed":
            if settings.alert_command_failed:
                events.append(("⚠️", _("Open command failed"),
                               f"{labels.get(r.device_name) or _esc(r.device_name)} — {_fmt_time(r.timestamp)} · {who}: {_esc((r.error or '')[:120])}"))
            continue
        detail = f"{labels.get(r.device_name) or _esc(r.device_name)} — {_fmt_time(r.timestamp)} · {who}"
        after = not in_work_hours(r.timestamp, settings.work_start_time, settings.work_end_time)
        if after and settings.erp_open_alert in ("After Hours", "Always"):
            events.append(("🟠", _("Opened from ERP after hours"), detail))
        elif settings.erp_open_alert == "Always":
            events.append(("🔓", _("Opened from ERP"), detail))
    for g in all_groups:
        total = g["ok"] + len(g["bad"])
        detail = f"{_fmt_time(g['t'])} · {g['who']} — " + _("{0}/{1} doors opened").format(g["ok"], total)
        if g["bad"]:
            detail += " · " + _("failed: {0}").format(", ".join(g["bad"]))
        events.append(("🔴", _("Open all doors used"), detail))
    return events


def _punch_events(settings, doors, since, until):
    if not _wants_punches(settings) or not doors:
        return []
    ip_to_door = {d["ip_address"]: _label(d) for d in doors}
    oldest = add_to_date(until, minutes=-PUNCH_MAX_AGE_MIN)
    rows = frappe.db.sql(
        """select user_id, employee, employee_name, timestamp, device_ip
        from `tabDoor Access Log`
        where creation > %(since)s and creation <= %(until)s
          and device_ip in %(ips)s and timestamp >= %(oldest)s
        order by timestamp""",
        {"since": since, "until": until, "ips": list(ip_to_door), "oldest": oldest}, as_dict=True,
    )
    events = []
    for p in rows:
        if _is_partner_id(settings, p.user_id):
            continue
        door = _esc(ip_to_door.get(p.device_ip, p.device_ip))
        line = f"{door} — {_fmt_time(p.timestamp, True)} · {_esc(_who(p.employee, p.employee_name, p.user_id))}"
        after = not in_work_hours(p.timestamp, settings.work_start_time, settings.work_end_time)
        if not p.employee and (settings.alert_unknown_user or settings.fingerprint_alert == "Always"):
            events.append(("🟠", _("Fingerprint ID matches no employee"), line))
        elif after and settings.fingerprint_alert in ("After Hours", "Always"):
            events.append(("🟠", _("Fingerprint after hours"), line))
        elif settings.fingerprint_alert == "Always":
            events.append(("👆", _("Fingerprint"), line))
    return events


def _is_partner_id(settings, user_id):
    """Fingerprint ID của đối tác (từ `staff_user_id_limit` trở lên) — bỏ qua khi bật
    `only_staff_user_ids`. ID không phải số không coi là đối tác (vẫn báo như cũ)."""
    if not settings.only_staff_user_ids:
        return False
    try:
        return int(str(user_id).strip()) >= int(settings.staff_user_id_limit or 6000)
    except (TypeError, ValueError):
        return False


def _wants_punches(settings):
    return bool(settings.alert_unknown_user or (settings.fingerprint_alert or "Off") != "Off")


def _format_events(events, now):
    head = f"🚪 <b>{_esc(_('Door alert'))}</b> — {now:%d/%m %H:%M}"
    lines = [f"{icon} <b>{_esc(title)}</b>\n    {detail}" for icon, title, detail in events[:MAX_EVENT_LINES]]
    if len(events) > MAX_EVENT_LINES:
        lines.append(_esc(_("... and {0} more events").format(len(events) - MAX_EVENT_LINES)))
    return head + "\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# daily summary
# ---------------------------------------------------------------------------

def build_daily_summary(settings, doors, day):
    start, end = f"{day} 00:00:00", f"{day} 23:59:59"
    names = [d["device_name"] for d in doors]
    lines = [f"📋 <b>{_esc(_('Door summary'))}</b> — {getdate(day):%d/%m/%Y}"]
    if not doors:
        return lines[0] + "\n" + _esc(_("No door controller is enabled"))
    for d in doors:
        punches = frappe.db.sql(
            """select timestamp, employee, user_id from `tabDoor Access Log`
            where device_ip=%s and timestamp between %s and %s""",
            (d["ip_address"], start, end), as_dict=True,
        )
        punches = [p for p in punches if not _is_partner_id(settings, p.user_id)]
        after = sum(1 for p in punches if not in_work_hours(p.timestamp, settings.work_start_time, settings.work_end_time))
        unknown = sum(1 for p in punches if not p.employee)
        acts = frappe.db.sql(
            """select result, count(*) n from `tabDoor Control Action`
            where device_name=%s and timestamp between %s and %s group by result""",
            (d["device_name"], start, end), as_dict=True,
        )
        ok = sum(a.n for a in acts if a.result == "Success")
        bad = sum(a.n for a in acts if a.result == "Failed")
        lines.append(
            f"• <b>{_esc(_label(d))}</b>: "
            + _esc(_("{0} punches ({1} after hours, {2} unknown ID) · {3} ERP opens{4}").format(
                len(punches), after, unknown, ok, (", " + _("{0} failed").format(bad)) if bad else ""))
        )
    if names:
        offline = [_label(d) for d in doors if (frappe.cache.get_value(f"door_alerts:offline:{d['device_name']}") or {}).get("alerted")]
        if offline:
            lines.append("🔴 " + _esc(_("Still offline: {0}").format(", ".join(offline))))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# scheduler entry point
# ---------------------------------------------------------------------------

def tick():
    """Cron every minute. Cheap no-op while switched off."""
    if not frappe.db.get_single_value(SETTING, "enabled"):
        return
    try:
        # a slow device must not let two runs overlap
        with filelock("door_alerts_tick", timeout=1):
            run_checks(commit=True)
    except LockTimeoutError:
        return


def run_checks(now=None, probe=None, read_punches=None, commit=False, force=False):
    """One pass. `probe` / `read_punches` are injectable for tests; only the
    scheduler passes commit=True (tests end with a rollback)."""
    _use_site_language()
    settings = _settings()
    if not settings.enabled:
        return {"skipped": "disabled"}
    now = now or now_datetime()
    out = {"events": 0, "summary": False}

    last = get_datetime(settings.last_check_at) if settings.last_check_at else None
    interval = timedelta(minutes=settings.check_interval_minutes or 2)
    doors = _watched_doors()
    muted = _muted(settings, now)
    out["muted"] = muted

    # 10 s of slack: cron fires at :00, the job may start a few seconds late
    if force or not last or now - last >= interval - timedelta(seconds=10):
        # never look back more than a day (e.g. after a long Telegram outage)
        since = max(last or (now - interval), now - timedelta(days=1))
        probes = (probe or (lambda ds: dc._probe_all(ds, force=True)))(doors)
        online = [d for d in doors if probes.get(d["device_name"], {}).get("online")]
        if online and (_wants_punches(settings) or settings.daily_summary):
            (read_punches or (lambda ds: dc.read_new_punches(ds, pause_device=False)))(online)

        events, not_locked_keys = [], []
        if settings.alert_device_offline:
            events += _offline_events(settings, doors, probes, now)
        if settings.use_lock_sensor and settings.alert_not_locked_after_hours:
            nl_events, not_locked_keys = _not_locked_events(settings, doors, probes, now)
            events += nl_events
        events += _action_events(settings, doors, since, now)
        events += _punch_events(settings, doors, since, now)

        delivered = True
        # muted: events are dropped on purpose (not queued for later)
        if events and not muted:
            results = send_telegram(settings, _format_events(events, now))
            _record_send_errors(results)
            # nobody got it (Telegram down, bad token): keep the window so the
            # next run sends these events again; partial success moves on
            delivered = any(r["ok"] for r in results)
            out["sent_ok"] = delivered
            if delivered:
                _count_sent(settings, now)
        if delivered or muted:
            # muted: the reminder clock keeps running, nothing piles up for later
            _mark_not_locked_sent(not_locked_keys, now)
        out["events"] = len(events)
        if delivered:
            _set_status(last_check_at=now)

    if settings.daily_summary and settings.daily_summary_time:
        today = getdate(now)
        due = now.time() >= _to_time(settings.daily_summary_time)
        if due and str(settings.last_summary_date or "") != str(today):
            if not muted:
                results = send_telegram(settings, build_daily_summary(settings, doors, today))
                _record_send_errors(results)
                if any(r["ok"] for r in results):
                    _count_sent(settings, now)
                out["summary"] = True
            _set_status(last_summary_date=today)

    if commit:
        frappe.db.commit()  # scheduler job: persist status + Door Access Log rows
    return out


# ---------------------------------------------------------------------------
# form buttons + status panel (Door Alert Setting)
# ---------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def check_now():
    """Run one check immediately, ignoring the interval (button "Check Now")."""
    _check_role()
    if not frappe.db.get_single_value(SETTING, "enabled"):
        frappe.throw(_("Turn on Enabled and save first"))
    try:
        with filelock("door_alerts_tick", timeout=20):
            return run_checks(force=True, commit=True)
    except LockTimeoutError:
        frappe.throw(_("A check is already running. Try again in a minute"))


@frappe.whitelist(methods=["POST"])
def get_chat_ids():
    """Chats the bot has seen in the last 24 h (button "Get Chat ID").

    Telegram only delivers group messages that are commands to a bot in privacy
    mode, hence the hint to send /start@<bot> in the group first.
    """
    import requests

    _check_role()
    settings = _settings()
    token = settings.get_password("bot_token", raise_exception=False)
    if not token:
        frappe.throw(_("Enter and save the Bot Token first"))
    base = TELEGRAM_URL.format(token=token).rsplit("/", 1)[0]
    try:
        me = requests.get(f"{base}/getMe", timeout=SEND_TIMEOUT_S).json()
        upd = requests.get(f"{base}/getUpdates", timeout=SEND_TIMEOUT_S).json()
    except Exception as e:
        frappe.throw(_("Telegram is not reachable: {0}").format(str(e).replace(token, "<token>")[:200]))
    if not upd.get("ok"):
        frappe.throw(_("Telegram error: {0}").format(_esc(upd.get("description") or "")))

    known = {r.chat_id for r in settings.recipients or []}
    chats = {}
    for u in upd.get("result", []):
        for key in ("message", "edited_message", "my_chat_member", "channel_post"):
            m = u.get(key)
            if not m or not m.get("chat"):
                continue
            c = m["chat"]
            # a group upgraded to a supergroup gets a new id
            chat_id = str(m.get("migrate_to_chat_id") or c["id"])
            chats[chat_id] = {
                "chat_id": chat_id,
                "title": c.get("title") or " ".join(filter(None, [c.get("first_name"), c.get("last_name")])) or c.get("username") or chat_id,
                "type": c.get("type"),
                "added": chat_id in known,
            }
    return {"bot": (me.get("result") or {}).get("username"), "chats": list(chats.values())}


@frappe.whitelist()
def get_status():
    """Data for the status panel on the Door Alert Setting form."""
    _check_role()
    settings = _settings()
    now = now_datetime()
    doors = dc._doors()
    probes = dc._probe_all(doors) if doors else {}
    today = getdate(now)
    sensor_on = bool(settings.use_lock_sensor)
    return {
        "enabled": bool(settings.enabled),
        "use_lock_sensor": sensor_on,
        "muted_until": str(settings.mute_until) if _muted(settings, now) else None,
        "in_work_hours": in_work_hours(now, settings.work_start_time, settings.work_end_time),
        "doors": [
            {
                "device_name": d["device_name"],
                "location": d.get("location") or "",
                "ip_address": d["ip_address"] if dc.can_see_ip() else "",
                "watched": bool(d.get("send_door_alerts", True)),
                "online": bool(probes.get(d["device_name"], {}).get("online")),
                "sensor": dc.sensor_reading(d, probes.get(d["device_name"], {}))[0] if sensor_on else None,
            }
            for d in doors
        ],
        "recipients": sum(1 for r in settings.recipients or [] if r.enabled and r.chat_id),
        "last_check_at": str(settings.last_check_at) if settings.last_check_at else None,
        "last_sent_at": str(settings.last_sent_at) if settings.last_sent_at else None,
        "sent_today": (settings.sent_count or 0) if str(settings.sent_count_date or "") == str(today) else 0,
        "last_error": dc.mask_ip(settings.last_error),
    }


@frappe.whitelist(methods=["POST"])
def read_sensors():
    """Button "Read Sensors Now": raw sensor byte + Door Sensor Mode of every enabled
    door, read even while Use Door Sensor / Sensor Installed is off (this is how it
    gets calibrated).
    Read-only: connect, read, disconnect."""
    from concurrent.futures import ThreadPoolExecutor
    from customize_erpnext.api.attendance_machines import get_machines

    _check_role()
    doors = get_machines(enabled_only=True, door_only=True)
    for d in doors:
        d["has_door_sensor"] = True   # read the input whatever the row says
    with ThreadPoolExecutor(max_workers=max(1, min(len(doors), 8))) as pool:
        probes = list(pool.map(dc._probe, doors)) if doors else []
    closed_value = dc.sensor_closed_value()
    rows = []
    for d, p in zip(doors, probes):
        raw = p.get("sensor_raw")
        rows.append({
            "door": _label(d),
            "online": bool(p.get("online")),
            "error": dc.mask_ip(p.get("error")),
            "raw": raw,
            "device_sensor_mode": p.get("device_sensor_mode"),
            "sensor_installed": d.get("sensor_installed"),
            "sensor_type": d.get("sensor_type"),
            "mode_matches": p.get("device_sensor_mode") == d.get("sensor_type"),
            "state": None if raw is None else ("closed" if int(raw) == closed_value else "open"),
        })
    return {"closed_value": closed_value, "doors": rows}

import frappe
from frappe.utils import now_datetime, getdate, get_time
from customize_erpnext.network.utils.hikvision import HikvisionNVR


def _parse_dt(iso_str):
    if not iso_str:
        return None
    try:
        from datetime import datetime as _dt
        return (
            _dt.fromisoformat(iso_str.replace("Z", "+00:00"))
               .astimezone()
               .strftime("%Y-%m-%d %H:%M:%S")
        )
    except Exception:
        return None


def _days_since(iso_str):
    if not iso_str:
        return None
    try:
        from datetime import datetime as _dt, timezone
        dt = (
            _dt.fromisoformat(iso_str.replace("Z", "+00:00"))
               .astimezone()
               .replace(tzinfo=None)
        )
        return round((now_datetime() - dt).total_seconds() / 86400, 1)
    except Exception:
        return None


def _parse_recipients(recipients):
    """Trả về list email, hoặc [] nếu rỗng.
    Hỗ trợ cả newline và comma làm separator.
    """
    if not recipients:
        return []
    if isinstance(recipients, list):
        return [r.strip() for r in recipients if r.strip()]
    import re
    return [r.strip() for r in re.split(r"[,\n]+", str(recipients)) if r.strip()]


@frappe.whitelist()
def run_monitor_for_nvr(nvr_name, send_email=True, recipients=None, gap_days=7, gap_min_minutes=10):
    """Chạy monitor cho một NVR, tạo CCTV Tracking record."""
    nvr_doc = frappe.get_doc("NVR", nvr_name)
    now = now_datetime()

    tracker = frappe.new_doc("CCTV Tracking")
    tracker.date = getdate(now)
    tracker.time = get_time(now)
    tracker.nvr  = nvr_name

    gap_days        = int(gap_days)
    gap_min_minutes = int(gap_min_minutes)

    client = HikvisionNVR(nvr_doc)

    if not client.is_online():
        tracker.status = "Offline"
        tracker.note   = f"Cannot connect to {nvr_doc.host}:{nvr_doc.port}"
        frappe.db.set_value("NVR", nvr_name, "status", "Offline")
        tracker.insert(ignore_permissions=True)
        frappe.db.commit()
        if send_email and send_email != "false":
            _send_email(tracker, recipients=recipients)
        return tracker.name

    tracker.status = "Online"

    # System status
    sys_st = client.get_system_status()
    tracker.up_time = sys_st.get("uptime")
    tracker.cpu     = sys_st.get("cpu")
    tracker.ram     = sys_st.get("ram")

    # Update NVR master
    dev_info = client.get_device_info()
    if dev_info:
        frappe.db.set_value("NVR", nvr_name, {
            "model":    dev_info.get("model"),
            "firmware": dev_info.get("firmware"),
            "serial":   dev_info.get("serial"),
            "status":   "Online",
        })

    # HDD summary
    hdds = client.get_hdd_status()
    if hdds:
        tracker.hdd_summary = " | ".join(
            f"HDD{h['id']}: {h['status']} {h['used_pct']}% ({h['capacity_gb']}GB)"
            for h in hdds
        )

    # Lấy danh sách camera đã đăng ký trong DocType (keyed by channel_no)
    registered = {
        d.channel_no: d.name
        for d in frappe.get_all(
            "Camera",
            filters={"nvr": nvr_name},
            fields=["name", "channel_no"],
            order_by="channel_no asc",
        )
    }

    # Camera details — chỉ xử lý các channel có trong Camera master
    cameras = client.get_camera_status()
    matched = [c for c in cameras if int(c["id"]) in registered]

    tracker.camera_total   = len(matched)
    tracker.camera_online  = sum(1 for c in matched if c["online"])
    tracker.camera_offline = tracker.camera_total - tracker.camera_online

    for cam in matched:
        row = tracker.append("details", {})
        row.camera      = registered[int(cam["id"])]
        row.nvr         = nvr_name
        row.channel_no  = int(cam["id"])
        row.camera_name = cam["name"]
        row.status      = "Online" if cam["online"] else "Offline"

        if cam["online"]:
            oldest = client.get_oldest_recording(cam["id"])
            row.last_time_recorded = _parse_dt(oldest)
            row.days_recorded      = _days_since(oldest)
            row.gap = client.get_recording_gaps(cam["id"], days=gap_days, min_gap_minutes=gap_min_minutes)
        else:
            latest = client.get_latest_recording(cam["id"])
            row.offline_since = _parse_dt(latest)

    tracker.insert(ignore_permissions=True)
    frappe.db.commit()

    if send_email and send_email != "false":
        _send_email(tracker, recipients=recipients, hdds=hdds)
    return tracker.name


@frappe.whitelist()
def run_all_nvr(send_email=True, recipients=None, gap_days=7, gap_min_minutes=10):
    """Chạy monitor cho tất cả NVR — gọi từ scheduler hoặc "Run Now" button."""
    results = []
    for nvr_name in frappe.get_all("NVR", pluck="name", order_by="name asc"):
        try:
            doc_name = run_monitor_for_nvr(
                nvr_name,
                send_email=send_email,
                recipients=recipients,
                gap_days=gap_days,
                gap_min_minutes=gap_min_minutes,
            )
            results.append({"nvr": nvr_name, "doc": doc_name, "ok": True})
        except Exception as e:
            frappe.log_error(f"Network - NVR Monitor [{nvr_name}]: {e}", "Network")
            results.append({"nvr": nvr_name, "error": str(e), "ok": False})
    return results


def run_all_nvr_daily():
    """Gọi từ scheduler hàng ngày — gap_days=1, recipients mặc định."""
    run_all_nvr(send_email=True, gap_days=1, gap_min_minutes=10)


def _hdd_status_color(status: str) -> str:
    s = (status or "").lower()
    if s in ("normal", "ok"):
        return "#1a7a1a"   # xanh lá
    if s in ("sleeping", "standby"):
        return "#555"      # xám
    if s in ("unformatted",):
        return "#b86e00"   # cam
    if s == "full":
        return "#1a7a1a"   # xanh lá — full là bình thường (HDD đang ghi vòng)
    if s in ("error", "damaged"):
        return "#c00"      # đỏ
    return "#888"          # mặc định


def _hdd_html(hdds: list) -> str:
    """Tạo HTML highlight từng HDD theo status."""
    if not hdds:
        return "<span style='color:#888'>N/A</span>"
    parts = []
    for h in hdds:
        color = _hdd_status_color(h.get("status", ""))
        label = (
            f"<span style='color:{color};font-weight:bold'>"
            f"HDD{h['id']}: {h['status']}"
            f"</span>"
            f" {h['used_pct']}% / {h['capacity_gb']} GB"
            f" (free {h['free_gb']} GB)"
        )
        parts.append(label)
    return " &nbsp;|&nbsp; ".join(parts)


def _send_email(tracker_doc, recipients=None, hdds=None):
    """Gửi email tóm tắt + chi tiết tất cả camera.
    recipients: string CSV hoặc list. Nếu rỗng → không gửi.
    hdds: list từ get_hdd_status() để render màu theo status.
    """
    recipient_list = _parse_recipients(recipients)
    if not recipient_list:
        # Dùng danh sách mặc định khi không truyền (gọi từ scheduler)
        recipient_list = ["son.nt@tiqn.com.vn", "vinh.nt@tiqn.com.vn"]

    subject = (
        f"[CCTV] {tracker_doc.nvr} — {tracker_doc.date} "
        f"| {tracker_doc.camera_offline or 0} offline"
    )

    details = tracker_doc.details or []
    offline_rows = [r for r in details if r.status == "Offline"]

    nvr_color     = "green" if tracker_doc.status == "Online" else "red"
    offline_color = "red" if tracker_doc.camera_offline else "green"

    # Min / Max days stored (chỉ tính camera Online có dữ liệu)
    days_vals = [r.days_recorded for r in details if r.status == "Online" and r.days_recorded]
    min_days  = f"{min(days_vals):.1f}" if days_vals else "N/A"
    max_days  = f"{max(days_vals):.1f}" if days_vals else "N/A"

    # ── NVR summary table ─────────────────────────────────────
    summary_html = f"""
<h2 style='margin-bottom:4px'>CCTV Monitoring Report — {tracker_doc.nvr}</h2>
<table border='1' cellpadding='5' style='border-collapse:collapse;font-size:13px;min-width:400px'>
<tr><th style='background:#f0f0f0;text-align:left'>Field</th><th style='background:#f0f0f0;text-align:left'>Value</th></tr>
<tr><td>Check Time</td><td>{tracker_doc.date} {tracker_doc.time}</td></tr>
<tr><td>NVR Status</td>
    <td><b style='color:{nvr_color}'>{tracker_doc.status}</b></td></tr>
<tr><td>Online Since</td><td>{tracker_doc.up_time or 'N/A'}</td></tr>
<tr><td>HDD</td><td style='font-size:12px'>{_hdd_html(hdds or [])}</td></tr>
<tr><td>Cameras Online</td>
    <td style='color:green;font-weight:bold'>{tracker_doc.camera_online} / {tracker_doc.camera_total}</td></tr>
<tr><td>Cameras Offline</td>
    <td style='color:{offline_color};font-weight:bold'>{tracker_doc.camera_offline}</td></tr>
<tr><td>Min Days Stored</td><td>{min_days} days</td></tr>
<tr><td>Max Days Stored</td><td>{max_days} days</td></tr>
</table>"""

    # ── Offline cameras table ──────────────────────────────────
    offline_html = ""
    if offline_rows:
        rows_html = "".join(
            f"<tr>"
            f"<td style='text-align:center'>{r.channel_no}</td>"
            f"<td>{r.camera_name}</td>"
            f"<td>{r.location or '—'}</td>"
            f"<td style='color:red'>{r.offline_since or 'N/A'}</td>"
            f"</tr>"
            for r in offline_rows
        )
        offline_html = f"""
<h3 style='color:red;margin-top:20px'>&#9888; Offline Cameras ({len(offline_rows)})</h3>
<table border='1' cellpadding='5' style='border-collapse:collapse;font-size:13px'>
<tr style='background:#ffdddd'>
  <th>Ch.</th><th>Camera</th><th>Location</th><th>Offline Since</th>
</tr>
{rows_html}
</table>"""

    # ── All cameras detail table ───────────────────────────────
    all_rows_html = ""
    for r in sorted(details, key=lambda x: x.channel_no or 0):
        if r.status == "Online":
            status_cell = "<td style='color:green;text-align:center'>&#10004; Online</td>"
            last_rec    = r.last_time_recorded or "—"
            days_rec    = f"{r.days_recorded:.1f} days" if r.days_recorded else "—"
            offline_since = "—"
            gap_cell    = f"<td style='font-size:11px;color:#c60'>{r.gap or ''}</td>"
        else:
            status_cell   = "<td style='color:red;text-align:center'>&#10008; Offline</td>"
            last_rec      = "—"
            days_rec      = "—"
            offline_since = f"<span style='color:red'>{r.offline_since or 'N/A'}</span>"
            gap_cell      = "<td></td>"

        all_rows_html += (
            f"<tr>"
            f"<td style='text-align:center'>{r.channel_no}</td>"
            f"<td>{r.camera_name}</td>"
            f"<td>{r.location or '—'}</td>"
            f"{status_cell}"
            f"<td style='font-size:12px'>{last_rec}</td>"
            f"<td style='text-align:center'>{days_rec}</td>"
            f"<td>{offline_since}</td>"
            f"{gap_cell}"
            f"</tr>"
        )

    detail_html = f"""
<h3 style='margin-top:24px'>All Cameras Detail ({len(details)})</h3>
<table border='1' cellpadding='4' style='border-collapse:collapse;font-size:12px;width:100%'>
<tr style='background:#e8f0fe'>
  <th>Ch.</th>
  <th>Camera</th>
  <th>Location</th>
  <th>Status</th>
  <th>Oldest Recording</th>
  <th>Days Stored</th>
  <th>Offline Since</th>
  <th>Gap</th>
</tr>
{all_rows_html}
</table>"""

    message = f"""
{summary_html}
{offline_html}
{detail_html}
<br>
<p style='font-size:12px;color:#666'>
  <a href='/app/cctv-tracking/{tracker_doc.name}'>&#128279; Xem chi tiết trong ERPNext</a>
</p>
"""

    frappe.sendmail(
        recipients=recipient_list,
        subject=subject,
        message=message,
        now=True,
    )

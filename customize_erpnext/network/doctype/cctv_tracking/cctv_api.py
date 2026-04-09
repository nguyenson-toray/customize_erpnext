"""
cctv_api.py — REST API for CCTV Tracking data (Excel / Power Query integration)

Endpoints (allow_guest=True):
  cctv_detail   — Video Recorded Detail rows
  cctv_summary  — CCTV Tracking summary with shortest-storage camera
"""
import frappe


def _parse_date_filter(date_param):
    """
    Parse date parameter:
      - "YYYY-MM-DD"            → exact date: [date, date]
      - "YYYY-MM-DD:YYYY-MM-DD" → range:      [from, to]
    Returns (date_from, date_to) or (None, None).
    """
    if not date_param:
        return None, None
    if ":" in date_param:
        parts = date_param.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    d = date_param.strip()
    return d, d


# ─── cctv_detail ─────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def cctv_detail(nvr=None, date=None):
    """
    Load Video Recorded Detail rows.

    Parameters
    ----------
    nvr  : str  — filter by NVR name (exact match on nvr field)
    date : str  — filter by modified date
                  "YYYY-MM-DD"              → single day
                  "YYYY-MM-DD:YYYY-MM-DD"   → date range (inclusive)

    Returns
    -------
    { columns: [...], col_keys: [...], data: [...], total: int }
    """
    date_from, date_to = _parse_date_filter(date)

    filters = {}
    if nvr:
        filters["nvr"] = nvr
    if date_from:
        filters["modified"] = ["between", [date_from + " 00:00:00", date_to + " 23:59:59"]]

    rows = frappe.get_all(
        "Video Recorded Detail",
        filters=filters,
        fields=[
            "nvr",
            "channel_no",
            "camera_name",
            "location",
            "priority",
            "status",
            "last_time_recorded",
            "gap",
            "offline_since",
            "parent",
            "modified",
        ],
        order_by="nvr asc, channel_no asc",
        limit=0,
    )

    col_keys = [
        "nvr",
        "channel_no",
        "camera_name",
        "location",
        "priority",
        "status",
        "last_time_recorded",
        "gap",
        "offline_since",
        "parent",
        "modified",
    ]
    columns = [
        "NVR",
        "Channel No.",
        "Camera Name",
        "Location",
        "Priority",
        "Status",
        "Last Time Recorded",
        "Gap Info",
        "Offline Since",
        "Tracking Record",
        "Last Modified",
    ]

    data = []
    for r in rows:
        data.append({k: (str(r[k]) if r.get(k) is not None else "") for k in col_keys})

    return {"columns": columns, "col_keys": col_keys, "data": data, "total": len(data)}


# ─── cctv_summary ────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def cctv_summary(nvr=None, date=None):
    """
    Load CCTV Tracking summary with shortest-storage camera.

    Parameters
    ----------
    nvr  : str  — filter by nvr_name field
    date : str  — filter by date field
                  "YYYY-MM-DD"              → single day
                  "YYYY-MM-DD:YYYY-MM-DD"   → date range (inclusive)

    Returns
    -------
    { columns: [...], col_keys: [...], data: [...], total: int }
    """
    date_from, date_to = _parse_date_filter(date)

    filters = {}
    if nvr:
        filters["nvr_name"] = nvr
    if date_from:
        filters["date"] = ["between", [date_from, date_to]]

    trackers = frappe.get_all(
        "CCTV Tracking",
        filters=filters,
        fields=[
            "name",
            "date",
            "time",
            "nvr_name",
            "up_time",
            "camera_total",
            "camera_online",
            "camera_offline",
            "hdd_summary",
            "note",
        ],
        order_by="date desc, time desc",
        limit=0,
    )

    # Find shortest-storage camera (smallest days_recorded > 0) per tracker
    tracker_names = [t["name"] for t in trackers]
    shortest_map = {}
    if tracker_names:
        details = frappe.get_all(
            "Video Recorded Detail",
            filters={
                "parent": ["in", tracker_names],
                "status": "Online",
                "days_recorded": [">", 0],
            },
            fields=["parent", "camera_name", "days_recorded"],
            order_by="days_recorded asc",
            limit=0,
        )
        for d in details:
            p = d["parent"]
            if p not in shortest_map:
                shortest_map[p] = {
                    "camera": d["camera_name"] or "",
                    "days": d["days_recorded"],
                }

    col_keys = [
        "name",
        "date",
        "time",
        "nvr_name",
        "up_time",
        "camera_total",
        "camera_online",
        "camera_offline",
        "hdd_summary",
        "note",
        "shortest_storage_camera",
        "shortest_storage_days",
    ]
    columns = [
        "Tracking Record",
        "Date",
        "Time",
        "NVR Name",
        "Online Since",
        "Total Cameras",
        "Online Cameras",
        "Offline Cameras",
        "HDD Summary",
        "Note",
        "Shortest Storage Camera",
        "Shortest Storage Days",
    ]

    data = []
    for t in trackers:
        sh = shortest_map.get(t["name"], {})
        row = {}
        for k in col_keys:
            if k == "shortest_storage_camera":
                row[k] = sh.get("camera", "")
            elif k == "shortest_storage_days":
                row[k] = str(sh["days"]) if sh.get("days") is not None else ""
            else:
                v = t.get(k)
                row[k] = str(v) if v is not None else ""
        data.append(row)

    return {"columns": columns, "col_keys": col_keys, "data": data, "total": len(data)}

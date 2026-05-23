# Plan & Prompt: Migrate NVR Monitor → ERPNext

> **Dành cho Claude Code** — Đọc toàn bộ file này trước khi bắt đầu.
> Dự án gốc: `D:\03.Dev\01.Project\NVR\NVR_Monitor\`
> Mục tiêu: Tích hợp hệ thống giám sát NVR/Camera Hikvision vào ERPNext thành một module độc lập.

---

## 0. Quy tắc bắt buộc — ĐỌC TRƯỚC

> ⚠️ **LUÔN LUÔN** đọc và tuân thủ skill/code mẫu tại `/home/frappe/frappe-bench/.claude/skills` trong project `customize_erpnext` trước khi viết bất kỳ dòng code nào.
> Mọi convention về cấu trúc file, naming, coding style phải theo đúng mẫu đã có trong project.

---

## 1. Tổng quan kiến trúc

### 1.1 App & Module

**App đã có sẵn — KHÔNG tạo app mới:**

```bash
# App: customize_erpnext (đã cài)
# KHÔNG chạy bench new-app
# KHÔNG chạy bench install-app
```

**Tạo Module mới trong app `customize_erpnext`:**

- **Module name:** `Network`
- Module này sẽ chứa nhiều chức năng về hạ tầng mạng, thiết bị.
- CCTV Monitor là chức năng **đầu tiên** trong module `Network`.
- Các chức năng sau sẽ tiếp tục được thêm vào module này.

Thêm `Network` vào `customize_erpnext/modules.txt`:
```
Network
```

### 1.2 Cấu trúc thư mục

```
apps/customize_erpnext/
└── customize_erpnext/
    ├── hooks.py              ← Thêm scheduler_events vào đây
    ├── modules.txt           ← Thêm dòng "Network"
    └── network/              ← Module mới (tạo thư mục này)
        ├── __init__.py
        ├── doctype/
        │   ├── nvr/
        │   ├── camera/
        │   ├── video_recorded_detail/
        │   └── cctv_tracking/
        └── utils/
            ├── __init__.py
            ├── hikvision.py       ← ISAPI client (dựa trên NVR_Monitor/src/nvr.py)
            └── monitor_runner.py  ← Logic chạy monitor & lưu CCTV Tracking
```

> **Lưu ý path import trong ERPNext:**
> `customize_erpnext.network.utils.hikvision`
> `customize_erpnext.network.utils.monitor_runner`

---

## 2. DocTypes

### 2.1 DocType: NVR

**Mục đích:** Master data các đầu ghi NVR Hikvision.
**Naming:** field `nvr_name` làm title, nhập thủ công.

| Fieldname | Fieldtype | Label | Ghi chú |
|-----------|-----------|-------|---------|
| nvr_name  | Data      | NVR Name | title_field, bắt buộc |
| host      | Data      | IP Address | Bắt buộc. VD: 10.0.1.9 |
| port      | Int       | Port | Bắt buộc. VD: 80 |
| user      | Data      | Username | Bắt buộc |
| password  | Password  | Password | Bắt buộc |
| status    | Select    | Status | Options: Online\nOffline |
| model     | Data      | Model | VD: DS-9664NI-I8 |
| firmware  | Data      | Firmware | VD: V4.50.010 |
| serial    | Data      | Serial Number | |

**Data import (2 records):**

```json
[
  {
    "nvr_name": "NVR-Insite",
    "host": "10.0.1.9", "port": 80,
    "user": "monitor", "password": "T0ray25#",
    "status": "Online", "model": "DS-9664NI-I8",
    "firmware": "V4.50.010",
    "serial": "DS-9664NI-I81620210610CCRRG18129610WCVU"
  },
  {
    "nvr_name": "NVR-Outsite",
    "host": "10.0.1.8", "port": 82,
    "user": "monitor", "password": "T0ray25#",
    "status": "Online", "model": "DS-9664NI-I8",
    "firmware": "V4.50.010",
    "serial": "DS-9664NI-I81620210719CCRRG37553994WCVU"
  }
]
```

Import script:
```python
import frappe
for d in data:
    doc = frappe.get_doc({"doctype": "NVR", **d})
    doc.insert(ignore_permissions=True)
frappe.db.commit()
```

---

### 2.2 DocType: Camera

**Mục đích:** Master data 87 cameras từ `docs/Cameras.csv`.
**Naming Series:** `CAM-{####}`

| Fieldname   | Fieldtype   | Label       | Ghi chú |
|-------------|-------------|-------------|---------|
| camera_name | Data        | Camera Name | title_field, bắt buộc |
| nvr         | Link → NVR  | NVR         | Bắt buộc |
| channel_no  | Int         | Channel No. | Số kênh trên NVR |
| ip_address  | Data        | IP Address  | |
| location    | Data        | Location    | Vị trí lắp đặt |

**Mapping tên NVR (CSV → DocType):**
- `NVR_Insite` → `NVR-Insite`
- `NVR_outsite` → `NVR-Outsite`

Import script:
```python
import frappe, csv
with open("/path/to/Cameras.csv") as f:
    for row in csv.DictReader(f):
        doc = frappe.get_doc({
            "doctype": "Camera",
            "camera_name": row["CameraName"],
            "nvr": NVR_MAP.get(row["NVR"], row["NVR"]),
            "channel_no": int(row["Channel No."]),
            "ip_address": row["IP Address"],
            "location": row["Location"],
        })
        doc.insert(ignore_permissions=True)
frappe.db.commit()
```

---

### 2.3 DocType: Video Recorded Detail (Child Table)

**istable = 1** | **Parent DocType: CCTV Tracking**

| Fieldname          | Fieldtype     | Label               | Ghi chú |
|--------------------|---------------|---------------------|---------|
| camera             | Link→Camera   | Camera              | fetch_from dùng để tự điền các field bên dưới |
| nvr                | Data          | NVR                 | fetch_from: camera.nvr |
| channel_no         | Int           | Channel No.         | fetch_from: camera.channel_no |
| camera_name        | Data          | Camera Name         | fetch_from: camera.camera_name |
| location           | Data          | Location            | fetch_from: camera.location |
| status             | Select        | Status              | Online\nOffline |
| last_time_recorded | Datetime      | Last Time Recorded  | Thời điểm video xa nhất còn lưu |
| days_recorded      | Float         | Days Recorded       | Số ngày tính từ last_time_recorded đến hôm nay |
| gap                | Small Text    | Gap Info            | Mô tả các khoảng ngắt quãng |
| offline_since      | Datetime      | Offline Since       | Thời điểm mất kết nối (nếu offline) |

---

### 2.4 DocType: CCTV Tracking

**Mục đích:** Lưu kết quả mỗi lần chạy giám sát.
**Naming:** Override `autoname()` → format `YYMMDDHHMM-NVR-Name`
Ví dụ: `2604081049-NVR-Outsite`

| Fieldname      | Fieldtype              | Label           | Ghi chú |
|----------------|------------------------|-----------------|---------|
| date           | Date                   | Date            | Bắt buộc |
| time           | Time                   | Time            | |
| nvr            | Link → NVR             | NVR             | Bắt buộc |
| nvr_name       | Data                   | NVR Name        | fetch_from: nvr.nvr_name |
| status         | Select                 | NVR Status      | Online\nOffline |
| up_time        | Data                   | Up Time         | VD: 1 ngày 18:56:30 |
| cpu            | Percent                | CPU Usage (%)   | |
| ram            | Percent                | RAM Usage (%)   | |
| camera_total   | Int                    | Total Cameras   | |
| camera_online  | Int                    | Online Cameras  | |
| camera_offline | Int                    | Offline Cameras | |
| hdd_summary    | Small Text             | HDD Summary     | |
| note           | Text                   | Note            | |
| details        | Table→Video Recorded Detail | Camera Details | Child table |

`autoname()` trong `cctv_tracking.py`:
```python
def autoname(self):
    from frappe.utils import now_datetime
    dt = now_datetime()
    nvr_slug = (self.nvr or "NVR").replace(" ", "-")
    self.name = dt.strftime("%y%m%d%H%M") + "-" + nvr_slug
```

---

## 3. ISAPI Client — `utils/hikvision.py`

Dựa trên `src/nvr.py` của project gốc. Sửa constructor nhận frappe document:

```python
import requests, xmltodict
from requests.auth import HTTPDigestAuth
from datetime import datetime, timezone
import urllib3
urllib3.disable_warnings()

class HikvisionNVR:
    def __init__(self, nvr_doc):
        """Nhận frappe document NVR."""
        self.name     = nvr_doc.nvr_name
        self.base_url = f"http://{nvr_doc.host}:{nvr_doc.port}"
        self.auth     = HTTPDigestAuth(nvr_doc.user, nvr_doc.get_password("password"))
        self.session  = requests.Session()
        self.session.verify = False

    def _get(self, path):
        r = self.session.get(f"{self.base_url}{path}", auth=self.auth, timeout=10)
        r.raise_for_status()
        return xmltodict.parse(r.text)

    def _post(self, path, xml_body):
        r = self.session.post(f"{self.base_url}{path}", auth=self.auth,
            data=xml_body.encode("utf-8"),
            headers={"Content-Type": "application/xml"}, timeout=15)
        r.raise_for_status()
        return xmltodict.parse(r.text)

    def is_online(self):
        try:
            r = self.session.get(f"{self.base_url}/ISAPI/System/deviceInfo",
                                  auth=self.auth, timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def get_system_status(self):
        """
        Uptime: GET /ISAPI/System/status → deviceUpTime (giây)
        CPU/RAM: GET /ISAPI/System/workingstatus?format=json (docs/nvr.md)
        """
        result = {"uptime": "N/A", "cpu": None, "ram": None}
        try:
            data = self._get("/ISAPI/System/status")
            secs = int(data.get("DeviceStatus", {}).get("deviceUpTime", 0))
            d, h, m, s = secs//86400, (secs%86400)//3600, (secs%3600)//60, secs%60
            result["uptime"] = f"{d} ngày {h:02d}:{m:02d}:{s:02d}"
        except Exception:
            pass
        try:
            r = self.session.get(
                f"{self.base_url}/ISAPI/System/workingstatus?format=json",
                auth=self.auth, timeout=10)
            if r.status_code == 200:
                ws = r.json().get("JSON_WorkingStatus", {})
                result["cpu"] = ws.get("cpuUtilization")
                result["ram"] = ws.get("memoryUtilization")
        except Exception:
            pass
        return result

    def get_device_info(self):
        """GET /ISAPI/System/deviceInfo"""
        try:
            data = self._get("/ISAPI/System/deviceInfo")
            info = data.get("DeviceInfo", {})
            return {
                "model":    info.get("model"),
                "firmware": info.get("firmwareVersion"),
                "serial":   info.get("serialNumber"),
            }
        except Exception:
            return {}

    def get_hdd_status(self):
        """GET /ISAPI/ContentMgmt/Storage"""
        try:
            data = self._get("/ISAPI/ContentMgmt/Storage")
            hdds = data.get("storage", {}).get("hddList", {}).get("hdd", [])
            if isinstance(hdds, dict): hdds = [hdds]
            result = []
            for h in hdds:
                cap  = int(h.get("capacity", 0))
                free = int(h.get("freeSpace", 0))
                pct  = round((cap-free)/cap*100, 1) if cap > 0 else 0.0
                result.append({
                    "id": h.get("id"),
                    "name": h.get("hddName", f"hdd{h.get('id')}"),
                    "status": h.get("status", "unknown"),
                    "capacity_gb": round(cap/1024, 1),
                    "free_gb": round(free/1024, 1),
                    "used_pct": pct,
                })
            return result
        except Exception:
            return []

    def get_camera_status(self):
        """
        Kết hợp 2 endpoint (docs/chanel.md):
        1. GET /ISAPI/System/Video/inputs/channels → tên camera
        2. GET /ISAPI/System/workingstatus/chanStatus?format=json → online/offline
        Fallback: /ISAPI/System/Video/inputs/channels/status
        """
        name_map = {}
        try:
            data = self._get("/ISAPI/System/Video/inputs/channels")
            chs = (data.get("VideoInputChannelList") or {}).get("VideoInputChannel", [])
            if isinstance(chs, dict): chs = [chs]
            for ch in chs:
                name_map[str(ch.get("id",""))] = ch.get("name", f"Camera {ch.get('id')}")
        except Exception:
            pass

        status_map = {}
        try:
            r = self.session.get(
                f"{self.base_url}/ISAPI/System/workingstatus/chanStatus?format=json",
                auth=self.auth, timeout=10)
            if r.status_code == 200:
                items = r.json().get("JSON_ChanStatus", {}).get("ChanStatus", [])
                if isinstance(items, dict): items = [items]
                for ch in items:
                    cid = str(ch.get("chanNo", ""))
                    status_map[cid] = int(ch.get("online", 0)) == 1
        except Exception:
            try:
                data = self._get("/ISAPI/System/Video/inputs/channels/status")
                chs = (data.get("VideoInputChannelList") or {}).get("VideoInputChannel", [])
                if isinstance(chs, dict): chs = [chs]
                for ch in chs:
                    cid = str(ch.get("id",""))
                    status_map[cid] = str(ch.get("online","false")).lower() == "true"
            except Exception:
                pass

        all_ids = sorted(set(list(name_map) + list(status_map)),
                         key=lambda x: int(x) if x.isdigit() else x)
        return [{"id": cid, "name": name_map.get(cid, f"Camera {cid}"),
                 "online": status_map.get(cid, False)} for cid in all_ids]

    def get_oldest_recording(self, channel_id):
        """
        POST /ISAPI/ContentMgmt/search — bản ghi cũ nhất (docs/record_gap.md)
        """
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CMSearchDescription>
  <searchID>oldest</searchID>
  <trackList><trackID>{channel_id}01</trackID></trackList>
  <timeSpanList><timeSpan>
    <startTime>2000-01-01T00:00:00Z</startTime><endTime>{now_utc}</endTime>
  </timeSpan></timeSpanList>
  <maxResults>1</maxResults><searchResultPosition>0</searchResultPosition>
  <metaDataList><metaData>//recordType.meta.std-cgi.com</metaData></metaDataList>
</CMSearchDescription>"""
        try:
            data = self._post("/ISAPI/ContentMgmt/search", xml)
            items = data.get("CMSearchResult",{}).get("matchList",{}).get("searchMatchItem",[])
            if isinstance(items, dict): items = [items]
            if items:
                return items[0].get("timeSpan",{}).get("startTime")
        except Exception:
            pass
        return None

    def get_latest_recording(self, channel_id):
        """Bản ghi mới nhất — ước tính thời điểm camera offline."""
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        xml_count = f"""<?xml version="1.0" encoding="UTF-8"?>
<CMSearchDescription>
  <searchID>count</searchID>
  <trackList><trackID>{channel_id}01</trackID></trackList>
  <timeSpanList><timeSpan>
    <startTime>2000-01-01T00:00:00Z</startTime><endTime>{now_utc}</endTime>
  </timeSpan></timeSpanList>
  <maxResults>0</maxResults><searchResultPosition>0</searchResultPosition>
  <metaDataList><metaData>//recordType.meta.std-cgi.com</metaData></metaDataList>
</CMSearchDescription>"""
        try:
            data = self._post("/ISAPI/ContentMgmt/search", xml_count)
            total = int(data.get("CMSearchResult",{}).get("numOfMatches", 0))
            if total > 0:
                xml_last = xml_count \
                    .replace("<searchID>count</searchID>", "<searchID>last</searchID>") \
                    .replace("<maxResults>0</maxResults>", "<maxResults>1</maxResults>") \
                    .replace("<searchResultPosition>0</searchResultPosition>",
                             f"<searchResultPosition>{total-1}</searchResultPosition>")
                data2 = self._post("/ISAPI/ContentMgmt/search", xml_last)
                items = data2.get("CMSearchResult",{}).get("matchList",{}).get("searchMatchItem",[])
                if isinstance(items, dict): items = [items]
                if items:
                    return items[0].get("timeSpan",{}).get("endTime")
        except Exception:
            pass
        return None
```

---

## 4. Monitor Runner — `utils/monitor_runner.py`

```python
import frappe
from frappe.utils import now_datetime, getdate, get_time
from customize_erpnext.network.utils.hikvision import HikvisionNVR

def _parse_dt(iso_str):
    if not iso_str: return None
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(iso_str.replace("Z","+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_str

def _days_since(iso_str):
    if not iso_str: return None
    try:
        from datetime import datetime as _dt, timezone
        dt = _dt.fromisoformat(iso_str.replace("Z","+00:00")).astimezone().replace(tzinfo=None)
        return round((now_datetime() - dt).total_seconds() / 86400, 1)
    except Exception:
        return None

@frappe.whitelist()
def run_monitor_for_nvr(nvr_name, send_email=True):
    nvr_doc = frappe.get_doc("NVR", nvr_name)
    now = now_datetime()

    tracker = frappe.new_doc("CCTV Tracking")
    tracker.date = getdate(now)
    tracker.time = get_time(now)
    tracker.nvr  = nvr_name

    client = HikvisionNVR(nvr_doc)

    if not client.is_online():
        tracker.status = "Offline"
        tracker.note   = f"Không thể kết nối tới {nvr_doc.host}:{nvr_doc.port}"
        frappe.db.set_value("NVR", nvr_name, "status", "Offline")
        tracker.insert(ignore_permissions=True)
        frappe.db.commit()
        if send_email:
            _send_email(tracker)
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
            f"HDD{h['id']}: {h['status']} {h['used_pct']}% ({h['capacity_gb']}GB)" for h in hdds
        )

    # Camera details
    cameras = client.get_camera_status()
    tracker.camera_total   = len(cameras)
    tracker.camera_online  = sum(1 for c in cameras if c["online"])
    tracker.camera_offline = tracker.camera_total - tracker.camera_online

    for cam in cameras:
        row = tracker.append("details", {})
        # Tìm Camera master theo NVR + channel_no
        cam_name = frappe.db.get_value("Camera",
            {"nvr": nvr_name, "channel_no": int(cam["id"])}, "name")
        if cam_name:
            row.camera = cam_name
        row.nvr         = nvr_name
        row.channel_no  = int(cam["id"])
        row.camera_name = cam["name"]
        row.status      = "Online" if cam["online"] else "Offline"

        if cam["online"]:
            oldest = client.get_oldest_recording(cam["id"])
            row.last_time_recorded = _parse_dt(oldest)
            row.days_recorded      = _days_since(oldest)
        else:
            latest = client.get_latest_recording(cam["id"])
            row.offline_since = _parse_dt(latest)

    tracker.insert(ignore_permissions=True)
    frappe.db.commit()

    if send_email:
        _send_email(tracker)
    return tracker.name


@frappe.whitelist()
def run_all_nvr(send_email=True):
    """Chạy monitor cho tất cả NVR — gọi từ scheduler hoặc "Run Now" button."""
    results = []
    for nvr_name in frappe.get_all("NVR", pluck="name"):
        try:
            doc_name = run_monitor_for_nvr(nvr_name, send_email=send_email)
            results.append({"nvr": nvr_name, "doc": doc_name, "ok": True})
        except Exception as e:
            frappe.log_error(f"Network - NVR Monitor [{nvr_name}]: {e}", "Network")
            results.append({"nvr": nvr_name, "error": str(e), "ok": False})
    return results


def _send_email(tracker_doc):
    """Gửi email tóm tắt — dùng frappe.sendmail."""
    subject = f"[CCTV] {tracker_doc.nvr} — {tracker_doc.date} | {tracker_doc.camera_offline or 0} offline"

    offline_rows = [r for r in (tracker_doc.details or []) if r.status == "Offline"]
    offline_html = ""
    if offline_rows:
        rows = "".join(
            f"<tr><td>{r.channel_no}</td><td>{r.camera_name}</td>"
            f"<td>{r.location or ''}</td>"
            f"<td style='color:red'>{r.offline_since or 'N/A'}</td></tr>"
            for r in offline_rows
        )
        offline_html = f"""
<h3 style='color:red'>⚠️ Camera Offline ({len(offline_rows)})</h3>
<table border='1' cellpadding='4' style='border-collapse:collapse;font-size:13px'>
<tr style='background:#f0f0f0'><th>Ch.</th><th>Camera</th><th>Location</th><th>Offline Since</th></tr>
{rows}
</table>"""

    message = f"""
<h2>Báo cáo giám sát CCTV — {tracker_doc.nvr}</h2>
<table border='1' cellpadding='4' style='border-collapse:collapse;font-size:13px'>
<tr><th>Thông tin</th><th>Giá trị</th></tr>
<tr><td>Thời gian kiểm tra</td><td>{tracker_doc.date} {tracker_doc.time}</td></tr>
<tr><td>Trạng thái NVR</td><td><b style='color:{"green" if tracker_doc.status=="Online" else "red"}'>{tracker_doc.status}</b></td></tr>
<tr><td>Uptime</td><td>{tracker_doc.up_time or 'N/A'}</td></tr>
<tr><td>CPU / RAM</td><td>{tracker_doc.cpu or 'N/A'}% / {tracker_doc.ram or 'N/A'}%</td></tr>
<tr><td>HDD</td><td>{tracker_doc.hdd_summary or 'N/A'}</td></tr>
<tr><td>Camera Online</td><td style='color:green'>{tracker_doc.camera_online} / {tracker_doc.camera_total}</td></tr>
<tr><td>Camera Offline</td><td style='color:{"red" if tracker_doc.camera_offline else "green"}'>{tracker_doc.camera_offline}</td></tr>
</table>
{offline_html}
<br><p><a href='/app/cctv-tracking/{tracker_doc.name}'>Xem chi tiết trong ERPNext</a></p>
"""
    frappe.sendmail(
        recipients=["son.nt@tiqn.com.vn"],
        subject=subject,
        message=message,
        now=True,
    )
```

---

## 5. Scheduler — `hooks.py`

```python
# Thêm vào customize_erpnext/hooks.py
# QUAN TRỌNG: merge vào scheduler_events đã có sẵn, không overwrite
scheduler_events = {
    "cron": {
        "0 7 * * *": [
            "customize_erpnext.network.utils.monitor_runner.run_all_nvr"
        ]
    }
}
```

Kích hoạt:
```bash
bench enable-scheduler
bench restart
```

---

## 6. Client Script — "Run Now" button

**File:** `customize_erpnext/network/doctype/cctv_tracking/cctv_tracking.js`

> ⚠️ Đọc code mẫu JS tại `/home/frappe/frappe-bench/.claude/skills` trước khi viết file này.

```javascript
// Tuân thủ convention JS của project customize_erpnext
frappe.listview_settings["CCTV Tracking"] = {
    onload(listview) {
        listview.page.add_inner_button(__("Run Now"), function () {
            frappe.prompt(
                [{
                    label: "NVR",
                    fieldname: "nvr",
                    fieldtype: "Link",
                    options: "NVR",
                    reqd: 0,
                    description: "Để trống để chạy tất cả NVR"
                }],
                function (values) {
                    frappe.show_alert({ message: __("Đang chạy giám sát..."), indicator: "orange" });
                    frappe.call({
                        method: values.nvr
                            ? "customize_erpnext.network.utils.monitor_runner.run_monitor_for_nvr"
                            : "customize_erpnext.network.utils.monitor_runner.run_all_nvr",
                        args: values.nvr ? { nvr_name: values.nvr } : {},
                        callback(r) {
                            if (!r.exc) {
                                frappe.show_alert({ message: __("Hoàn tất! Đã tạo bản ghi mới."), indicator: "green" });
                                listview.refresh();
                            }
                        }
                    });
                },
                __("Chọn NVR"),
                __("Chạy ngay")
            );
        }, __("Actions"));
    }
};
```

---

## 7. Cài đặt Python dependencies

```bash
# Thêm vào requirements.txt của customize_erpnext (nếu chưa có)
bench pip install requests xmltodict
```

---

## 8. Thứ tự triển khai

```
Bước 0: Đọc /home/frappe/frappe-bench/.claude/skills để nắm convention của project customize_erpnext

Bước 1: Tạo thư mục module Network
  - Tạo customize_erpnext/network/__init__.py
  - Thêm "Network" vào customize_erpnext/modules.txt

Bước 2: Tạo DocTypes theo thứ tự (module = "Network"):
  NVR → Camera → Video Recorded Detail → CCTV Tracking

Bước 3: Tạo utils
  - customize_erpnext/network/utils/__init__.py
  - customize_erpnext/network/utils/hikvision.py  (từ section 3)
  - customize_erpnext/network/utils/monitor_runner.py  (từ section 4)

Bước 4: Cập nhật customize_erpnext/hooks.py
  - Merge scheduler_events (KHÔNG overwrite toàn bộ file)

Bước 5: Tạo cctv_tracking.js (List View + Run Now button)

Bước 6: bench --site [site] migrate
         bench build --app customize_erpnext
         bench restart

Bước 7: Import data
  - NVR: 2 records (Insite + Outsite)
  - Camera: 87 records từ NVR_Monitor/docs/Cameras.csv

Bước 8: Test
  bench --site [site] execute \
    customize_erpnext.network.utils.monitor_runner.run_all_nvr \
    --kwargs '{"send_email": false}'
```

---

## 9. Checklist xác nhận sau deploy

- [ ] NVR doctype: 2 records với đầy đủ model/firmware/serial/status
- [ ] Camera doctype: 87 records đúng mapping NVR
- [ ] Chạy "Run Now" → tạo CCTV Tracking name format `YYMMDDHHMM-NVR-Name`
- [ ] Child table Video Recorded Detail có last_time_recorded cho camera online
- [ ] Camera offline hiển thị offline_since
- [ ] Email gửi tới son.nt@tiqn.com.vn
- [ ] Scheduler 07:00 hàng ngày hoạt động

---

## 10. Dữ liệu thực tế (tham khảo)

### NVR-Outsite (26-04-08-10-49)
- DS-9664NI-I8 | V4.50.010 | Serial: DS-9664NI-I81620210719CCRRG37553994WCVU
- 39/39 online | 8 HDD × 5589GB, 100% full, tất cả ok

### NVR-Insite (26-04-08-10-49)
- DS-9664NI-I8 | V4.50.010 | Serial: DS-9664NI-I81620210610CCRRG18129610WCVU
- 57 online / 1 offline (Camera 35, offline từ 2025-11-27 21:02:07)
- HDD 3,4,5,8 trạng thái `idle` — cần kiểm tra

---

## 11. Lưu ý quan trọng

1. **Skill/Code mẫu** — Luôn đọc `/home/frappe/frappe-bench/.claude/skills` TRƯỚC khi code. Tuân thủ convention đã có trong project `customize_erpnext`.
2. **App đã tồn tại** — KHÔNG tạo app mới. KHÔNG chạy `bench new-app`. Chỉ thêm module `Network` vào `customize_erpnext`.
3. **hooks.py** — Merge scheduler_events cẩn thận, KHÔNG overwrite các config đã có.
4. **Module name** — `Network` (có dấu hoa đầu trong modules.txt, snake_case khi dùng trong code: `network`).
5. **Password field** — Dùng Frappe `PasswordField`, đọc bằng `nvr_doc.get_password("password")`.
6. **autoname()** — Override thủ công, không dùng naming_series thông thường.
7. **fetch_from** — Chỉ tự động khi chọn từ UI; khi tạo bằng Python cần set thủ công.
8. **Email SMTP** — Cần cấu hình Outgoing Mail Server trước trong ERPNext Settings.
9. **@frappe.whitelist()** — Bắt buộc cho mọi method gọi từ JS client.
10. **bench restart** — Cần chạy sau mỗi lần sửa hooks.py.
11. **ISAPI docs** — Tham khảo trong `NVR_Monitor/docs/`: `chanel.md`, `nvr.md`, `record_gap.md`.
12. **Scalability** — Module `Network` sẽ có thêm chức năng trong tương lai. Đặt tên DocType, utils rõ ràng, không hardcode `cctv` vào tên utils dùng chung.
                                                                     
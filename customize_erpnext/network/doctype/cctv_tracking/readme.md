# CCTV Tracking — Tài liệu kỹ thuật

Module: `Network` | App: `customize_erpnext`

---

## 1. Mục đích

Lưu kết quả mỗi lần giám sát hệ thống NVR/Camera Hikvision. Mỗi record = 1 lần chạy monitor cho 1 NVR.

---

## 2. Cấu trúc DocType

### 2.1 CCTV Tracking (parent)

| Field | Type | Mô tả |
|-------|------|-------|
| `date` | Date | Ngày chạy monitor |
| `time` | Time | Giờ chạy monitor |
| `nvr` | Link → NVR | NVR được kiểm tra |
| `nvr_name` | Data | fetch_from nvr.nvr_name |
| `status` | Select | Online / Offline |
| `up_time` | Data | Thời gian hoạt động VD: `2 ngày 03:15:42` |
| `cpu` | Percent | CPU usage (N/A với firmware DS-9664NI-I8) |
| `ram` | Percent | RAM usage (N/A với firmware DS-9664NI-I8) |
| `camera_total` | Int | Tổng số camera **đã đăng ký trong DocType** |
| `camera_online` | Int | Số camera online |
| `camera_offline` | Int | Số camera offline |
| `hdd_summary` | Small Text | Tóm tắt HDD: `HDD1: ok 100% (5589GB) \| HDD2: ...` |
| `note` | Text | Ghi chú lỗi khi NVR offline |
| `details` | Table | Child table: Video Recorded Detail |

**Naming:** Override `autoname()` → `YYMMDDHHMM-NVR-Name`
VD: `2604081049-NVR-Outsite`

### 2.2 Video Recorded Detail (child table)

| Field | Type | Mô tả |
|-------|------|-------|
| `camera` | Link → Camera | Camera master record |
| `nvr` | Data | fetch_from camera.nvr |
| `channel_no` | Int | Số kênh trên NVR |
| `camera_name` | Data | Tên camera (lấy từ NVR qua ISAPI) |
| `location` | Data | Vị trí lắp đặt (fetch_from camera.location) |
| `priority` | Int | Độ ưu tiên (mặc định 0) |
| `status` | Select | Online / Offline |
| `last_time_recorded` | Datetime | Thời điểm bản ghi cũ nhất còn lưu (camera Online) |
| `days_recorded` | Float | Số ngày tính từ last_time_recorded đến hôm nay |
| `gap` | Small Text | Các khoảng ngắt quãng ghi hình 7 ngày gần nhất |
| `offline_since` | Datetime | Thời điểm camera mất kết nối (camera Offline) |

---

## 3. Luồng xử lý Monitor

```
run_all_nvr()
  └─ for each NVR in DocType:
       run_monitor_for_nvr(nvr_name)
         ├─ HikvisionNVR.is_online()
         │    ├─ Offline → lưu tracker status=Offline, gửi email, return
         │    └─ Online → tiếp tục
         ├─ get_system_status()     → up_time, cpu, ram
         ├─ get_device_info()       → cập nhật NVR master (model, firmware, serial)
         ├─ get_hdd_status()        → hdd_summary
         ├─ load registered cameras → Camera DocType {channel_no: cam_name}
         ├─ get_camera_status()     → danh sách tất cả channel từ NVR
         ├─ filter matched          → chỉ giữ channel có trong Camera DocType
         └─ for each matched camera:
              ├─ Online:
              │    ├─ get_oldest_recording()   → last_time_recorded, days_recorded
              │    └─ get_recording_gaps()     → gap (7 ngày, gap > 10 phút)
              └─ Offline:
                   └─ get_latest_recording()  → offline_since
```

**Quan trọng:** `camera_total / online / offline` chỉ đếm camera đã đăng ký trong DocType Camera.
Channel NVR không có trong Camera master → **bỏ qua hoàn toàn**.

---

## 4. ISAPI Endpoints sử dụng

| Endpoint | Method | Mục đích |
|----------|--------|---------|
| `/ISAPI/System/deviceInfo` | GET | Kiểm tra online, lấy model/firmware/serial |
| `/ISAPI/System/status` | GET | Uptime (`deviceUpTime`), CPU/RAM |
| `/ISAPI/ContentMgmt/Storage` | GET | Danh sách HDD và dung lượng |
| `/ISAPI/System/workingstatus/chanStatus?format=json` | GET | Trạng thái online/offline từng kênh + tên |
| `/ISAPI/System/Video/inputs/channels` | GET | Fallback: lấy tên camera |
| `/ISAPI/System/Video/inputs/channels/status` | GET | Fallback: lấy trạng thái online |
| `/ISAPI/ContentMgmt/record/tracks` | GET | Track discovery (map channel → TrackID) |
| `/ISAPI/ContentMgmt/record/tracks/{tid}/dailyDistribution` | POST | Ngày ghi hình cũ nhất (ưu tiên, nhanh) |
| `/ISAPI/ContentMgmt/search` | POST | Tìm bản ghi cụ thể, phát hiện gap |

### Track ID
NVR dùng TrackID (VD: `101`) thay vì Channel ID (`1`).
Code tự discover qua `/ISAPI/ContentMgmt/record/tracks`, fallback về `{channel_id}01`.
Cache trong `self._track_map` để tránh gọi lại nhiều lần trong cùng 1 lần chạy.

### Lưu ý firmware DS-9664NI-I8 V4.50.010
- CPU/RAM: endpoint trả về `0` thay vì null → xử lý `or None` → lưu `None` → hiển thị N/A
- chanStatus JSON: response wrapper là `data["ChanStatus"]["JSON_ChanStatus"]` hoặc `data["JSON_ChanStatus"]` (tùy firmware version)
- `oldest_recording`: dùng `DailyDistribution` trước (1 call/camera), fallback `CMSearch` (chậm hơn)

---

## 5. Gap Detection

**File:** `network/utils/hikvision.py` → `get_recording_gaps(cid, days=7, min_gap_minutes=10)`

**Thuật toán:**
1. Đếm tổng số segment bằng `CMSearch` với `maxResults=0`
2. Lấy tối đa 200 segment video trong `days` ngày gần nhất
3. Sort theo `startTime`
4. So sánh `endTime[i]` với `startTime[i+1]`
5. Nếu khoảng cách > `min_gap_minutes` → ghi nhận gap

**Format kết quả:** `04-01 22:15→04-02 01:30(3h15m); 04-05 08:00→04-05 09:45(1h45m)`

**Mặc định:** 7 ngày gần nhất, gap > 10 phút

**Hiển thị:** Cột "Gap (7 ngày)" trong email chi tiết + field `gap` trên child table.

---

## 6. Email

**File:** `network/utils/monitor_runner.py` → `_send_email(tracker_doc)`

**Recipients:** `son.nt@tiqn.com.vn`, `vinh.nt@tiqn.com.vn`

**Subject:** `[CCTV] NVR-Outsite — 2026-04-08 | 0 offline`

**Body — 3 phần:**

| Phần | Nội dung | Điều kiện hiển thị |
|------|----------|--------------------|
| Tóm tắt NVR | Status, Uptime, CPU/RAM, HDD, Online/Offline count | Luôn hiện |
| Camera Offline | Bảng nền đỏ: Ch / Camera / Location / Offline Since | Chỉ khi có camera offline |
| Chi tiết tất cả camera | Ch / Camera / Location / Trạng thái / Lưu trữ từ / Số ngày / Offline từ / Gap | Luôn hiện |

**Trigger:** Tự động sau mỗi lần chạy monitor (`send_email=True`).
Khi test thủ công truyền `send_email=False`.

---

## 7. Scheduler

```python
# customize_erpnext/hooks.py
scheduler_events = {
    "cron": {
        "0 7 * * *": [
            "customize_erpnext.network.utils.monitor_runner.run_all_nvr"
        ]
    }
}
```

Chạy **07:00 mỗi ngày** cho tất cả NVR trong DocType.

---

## 8. Chạy thủ công

```bash
# Chạy tất cả NVR, không gửi email
bench --site erp.tiqn.local execute \
  customize_erpnext.network.utils.monitor_runner.run_all_nvr \
  --kwargs '{"send_email": False}'

# Chạy 1 NVR cụ thể, không gửi email
bench --site erp.tiqn.local execute \
  customize_erpnext.network.utils.monitor_runner.run_monitor_for_nvr \
  --kwargs '{"nvr_name": "NVR-Outsite", "send_email": False}'
```

Hoặc từ giao diện: **List View CCTV Tracking → Actions → Run Now**

---

## 9. Cấu trúc file

```
network/
├── doctype/
│   ├── nvr/                        ← Master NVR (2 records)
│   ├── camera/                     ← Master Camera (85 records)
│   ├── video_recorded_detail/      ← Child table của CCTV Tracking
│   └── cctv_tracking/
│       ├── cctv_tracking.json      ← DocType definition
│       ├── cctv_tracking.py        ← autoname() override
│       ├── cctv_tracking.js        ← List view "Run Now" button
│       └── readme.md               ← File này
└── utils/
    ├── hikvision.py                ← HikvisionNVR ISAPI client
    └── monitor_runner.py           ← Logic monitor + email
```

---

## 10. Data thực tế (2026-04-08)

| NVR | Status | Camera đăng ký | Online | Offline | HDD | Oldest Record |
|-----|--------|----------------|--------|---------|-----|---------------|
| NVR-Insite | Online | 46 | 46 | 0 | 8 × 5589GB (idle: 3,4,5,8) | ~2026-02-01 |
| NVR-Outsite | Online | 39 | 39 | 0 | 8 × 5589GB (all ok) | ~2025-12-30 |

- HDD 100% full → ghi đè vòng tròn liên tục (~99-65 ngày lưu trữ)
- Camera35 (NVR-Insite, Ch35): đã offline từ 2025-11-27 21:02:07 → hiện đã back online
- CPU/RAM firmware không expose → hiển thị N/A

---

## 11. Quản lý Camera

### Thêm camera mới
1. Vào **Camera DocType** → New → điền đúng `nvr` và `channel_no`
2. Monitor tự nhận khi chạy tiếp theo (không cần restart)

### Camera trên NVR nhưng không trong DocType
- Bị bỏ qua hoàn toàn, không xuất hiện trong CCTV Tracking
- Để giám sát: thêm vào Camera DocType

### Cameras.csv
- File nguồn: `network/docs_sample/docs/Cameras.csv`
- NVR-Insite: 46 cameras (channel 1-59, không liên tục)
- NVR-Outsite: 39 cameras (channel 1-39)
- Tên NVR trong CSV: `NVR-outsite` (lowercase) → Frappe tự chuẩn hóa thành `NVR-Outsite`

---

## 12. Lỗi thường gặp

| Lỗi | Nguyên nhân | Xử lý |
|-----|-------------|-------|
| `camera_total = 0` | chanStatus JSON parse sai cấu trúc | Kiểm tra firmware response, dùng fallback XML |
| `last_time_recorded = None` | DailyDistribution không có data | Fallback tự động sang Search API |
| `gap` rỗng toàn bộ | Camera ghi hình liên tục, không có gap | Bình thường |
| Email không gửi | Chưa cấu hình Outgoing Mail Server | ERPNext Settings → Email Account |
| Monitor chậm | Gap detection gọi nhiều ISAPI call | Giảm `days` hoặc tắt gap detection |
| `frappe.log_error` trong Error Log | NVR không kết nối được | Kiểm tra IP/port/credential trong NVR DocType |

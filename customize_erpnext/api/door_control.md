# /door_control — đóng/mở cửa ZKTeco F21Lite

Trang web điều khiển chốt điện các cửa dùng máy ZKTeco F21Lite (cùng model với máy chấm công)
và xem nhật ký ra vào. Chạy thật từ 08/10/2026.

> ⚠ **Đừng đặt tài liệu này (hay bất kỳ file nào không phải `.py`) trong `www/door_control/`.**
> Frappe phục vụ mọi file trong `www/` ra web, KHÔNG cần đăng nhập
> (`frappe/website/page_renderers/template_page.py::get_index_path_options` thử
> `<path>`, `.html`, `.md`, `/index.html`, `/index.md`). Ví dụ đang bị lộ:
> `www/biometric_sync/biometric_sync.md` → `/biometric_sync/biometric_sync` (HTTP 200, không login).

---

## 1. Truy cập

| Thứ | Giá trị |
|---|---|
| URL | `/door_control` (trang `www`, không phải Desk Page) |
| Quyền | Role **`Door Control`** — trang + mọi API đều `frappe.only_for("Door Control")`. Role không gán cho ai ⇒ mặc định chỉ Administrator (Administrator có mọi role). Người không có role: trang 403, API `PermissionError` |
| Shortcut Desk | `desktop_icon/door_control.json` (roles: Door Control) **+** `workspace_sidebar/door_control.json` |

🔴 Desktop Icon kiểu `Link` (v16) chỉ hiện khi có **Workspace Sidebar CÙNG TÊN** và sidebar có ≥1 item
user thấy được (`frappe/desk/doctype/desktop_icon/desktop_icon.py::get_desktop_icons`). Chỉ tạo
`desktop_icon/*.json` thì icon im lặng không hiện.

## 2. Cấu hình máy cửa

Máy cửa là một dòng của **Attendance Machine Setting → bảng `machines` (Attendance Machine Detail)**:

| Field | Ý nghĩa |
|---|---|
| `is_door_control` | Đánh dấu máy quản lý cửa |
| `enable` | Phải bật thì mới hiện trên `/door_control` |
| `unlock_seconds` | Số giây mở mỗi lần bấm "Mở" (1–60, validate trong Setting) |
| `sensor_type` | `None` / `NO` / `NC` — sensor trạng thái chốt đấu vào cổng `SEN` của máy. Phải khớp Door Sensor Mode trên menu máy. **Hiện tất cả = None** (xem §6) |
| `allow_hold_close` | Hiện nút "Giữ mở"/"Đóng" cho cửa này. Hiện tất cả = 0 |
| `has_door_sensor` | Cột cũ, đã thay bằng `sensor_type`; còn trong DB, không dùng |

Validate (`attendance_machine_setting.py::_validate_door_controllers`): máy cửa không được là
`master_device`; `unlock_seconds` 1–60.

Cửa thật (08/10/2026): `.48` Machine 8 - Door - Office (cửa 2 cánh, 2 khoá),
`.49` Machine 9 - Door - IT, `.50` Machine 10 - Door - Main Hall. Khoá: **ZKTeco LB-35**
(fail-safe: có điện = khoá; trễ chốt 0/3/6 s chỉnh trên khoá; có sensor chốt NO/COM).

## 3. Tách biệt khỏi chấm công

`api/attendance_machines.py` là lớp truy cập duy nhất:

- `get_machines(enabled_only, include_door=False, door_only=False)` — **mặc định LOẠI máy cửa**.
- `get_machine(name, allow_door=False)` — **từ chối máy cửa** trừ khi `allow_door=True`. Mọi chức
  năng chấm công (resync → Employee Checkin, reboot, đồng bộ giờ, dọn NV nghỉ, menu 4.2…) đều
  resolve máy qua đây ⇒ tự loại máy cửa.
- `check_door_machine_access(machine)` — đẩy vân tay lên máy cửa = cấp quyền vào cửa ⇒ chỉ role
  Door Control.

Ngoại lệ duy nhất: dialog **"Sync Fingerprints to Machines"** (`public/js/shared_fingerprint_sync.js`,
dùng ở menu 4.1 Employee list + nút trên form Employee) gọi
`utilities.get_enabled_attendance_machines(include_door=1, include_disabled=1)`:

| Loại máy | Hiện | Tự tick |
|---|---|---|
| Máy chấm công đang bật | ✔ | ✔ |
| Máy đang tắt | ✔ (pill "Disabled") | ✘ |
| Máy cửa | ✔ chỉ với role Door Control (pill "Door") | ✘ |

"Select All" chỉ tick máy chấm công đang bật. Sync lên máy tắt được phép khi user tự tick.

Service chấm công tự động `erpnext-sync-all` (`apps/biometric-attendance-sync-tool`) đọc IP từ
`local_config.py::devices`, **không** đọc Setting ⇒ không liên quan.

## 4. File

| File | Vai trò |
|---|---|
| `api/door_control.py` | Toàn bộ API + giao tiếp máy (docstring đầu file có các sự thật đo được) |
| `api/door_access.py` | `store_door_punches()` dùng chung với tab "IT Door Access" cũ trên /biometric_sync |
| `api/attendance_machines.py` | Lọc máy cửa (§3) |
| `www/door_control/index.py` | Kiểm tra login/role, CSRF, gom chuỗi dịch |
| `www/door_control/index.html` | Toàn bộ UI (CSS + JS inline) |
| `network/doctype/door_control_action/` | Nhật ký lệnh ERP |
| `network/doctype/door_access_log/` | Log quẹt vân tay (có sẵn, thêm quyền Door Control) |
| `patches/create_door_control_role.py` | `pre_model_sync` — role phải có trước khi sync DocPerm |
| `api/test_door_control.py` | Test hồi quy (§9) |

## 5. API (`customize_erpnext.api.door_control.*`)

| Hàm | Method | Việc |
|---|---|---|
| `get_doors(force=0)` | GET | Máy cửa đang bật + trạng thái. Probe song song, cache 8 s/cửa (nhiều trình duyệt = 1 lần kết nối) |
| `unlock_door(device_name)` | POST | `conn.unlock(unlock_seconds)` + ghi Door Control Action |
| `hold_open` / `close_door` | POST | **Tạm tắt** (`HOLD_CLOSE_ENABLED = False`) — throw |
| `unlock_all()` | POST | Mở mọi cửa song song (cửa offline không làm chậm cửa khác) |
| `fetch_logs(device_name=None, force=0)` | POST | Đọc log máy → Door Access Log (30 ngày gần nhất). So số record với lần trước, không đổi thì bỏ qua. Không xoá log trên máy |
| `get_timeline(device_name=None, limit=150)` | GET | Gộp Door Access Log + Door Control Action, mới nhất trước |

Lệnh lỗi **không throw** mà trả `{success: False}` — để dòng Failed của Door Control Action vẫn được
commit (throw sẽ rollback cả dòng log).

Kết nối: dùng `force_udp`/`timeout` của Setting; khoá theo từng máy bằng `filelock`; retry 2 lần.
Hàm `_run`/`_probe` không gọi frappe ⇒ chạy được trong ThreadPool.

## 6. Trạng thái cửa trên trang

- **Không sensor (hiện tại):** trang **KHÔNG hiện "Đã khoá"** (user yêu cầu 08/10/2026 — không
  phản ánh thực tế: kính thoát hiểm vỡ ở Main Hall làm chốt nhả mà trang vẫn báo khoá). Card ở
  trạng thái trung tính (icon cửa, dải xanh dương, không dòng trạng thái). Chỉ hiện điều chắc chắn:
  "Mở · còn Xs" sau lệnh ERP (cache `door_control:open:<hash>`) và "Ngoại tuyến". Bật lại hiển thị
  khoá khi sensor chạy (`sensor_type` NO/NC ⇒ "Đã chốt/Đã nhả chốt").
- **Có sensor (`sensor_type` NO/NC):** đọc `CMD_DOORSTATE_RRQ` (75) → 1 byte, dịch bằng
  `SENSOR_STATES = {1: "locked", 0: "unlocked"}` (**đoán, chưa hiệu chỉnh**). Chỉ tin khi option
  `DSM` của máy khớp `sensor_type`; lệch ⇒ bỏ sensor + cảnh báo cam trên card.
- 🔴 **Mã option `DSM` (đo thật, fw 6.60): `0=NO`, `1=NC`, `2=None` (mặc định nhà máy).** Đừng tin
  tài liệu/đoán — từng đoán ngược và gây cảnh báo sai.

## 7. Sự thật đo trên máy thật (F21Lite, fw Ver 6.60 May 14 2018, ZMM220_TFT)

- pyzk 0.9 chỉ có `unlock(seconds)` — gửi `pack("I", seconds*10)`. Không có lệnh "đóng ngay";
  `unlock(0)` được ACK nhưng chưa xác minh có khoá sớm không.
- **Mở bằng phần mềm KHÔNG ghi log trên máy** ⇒ Door Control Action là nguồn duy nhất biết ai mở.
- `CMD_DOORSTATE_RRQ` trên cả `.48/.49/.50` **luôn `01`** — kể cả chốt nhả, mở cánh, đóng, khoá
  (~800 lần đọc trên .48 với 4 lần quẹt, DSM=NO). Hoặc dây sensor LB-35 chưa vào `SEN`, hoặc
  firmware không báo ⇒ để `sensor_type = None`.
- Thời gian unlock tối đa: **không có tài liệu nào xác nhận** (SDK `ACUnlock(Delay)` không ghi
  đơn vị/giới hạn; tài liệu Axxon gợi ý 1–254 s). `HOLD_OPEN_SECONDS = 900` là chưa kiểm chứng.
- TCP: kết nối lại ngay sau disconnect → BrokenPipe; UDP (Setting đang `force_udp=1`) không bị.
- pyzk có `reg_event(EF_ALARM | EF_UNLOCK …)` nhưng `live_capture` chỉ parse log chấm công;
  nghe sự kiện realtime cần tiến trình chạy nền riêng — **chưa thử**.

🔴 Quy ước khi test: máy `.50` được thử tự do (đã từng là máy test); `.49` **chỉ đọc**; máy khác
phải hỏi. Không `disable_device`, không ghi option khi chỉ được phép đọc.

## 8. UI

- Mobile-first. < 640 px: card gọn (~165 px) để **3 cửa/màn hình**; Open/Hold/Close chung 1 hàng.
  < 1024 px: tab dưới "Cửa / Nhật ký ra vào". ≥ 1024 px: lưới cửa trái + nhật ký phải.
- 🔴 Lưới phải là `minmax(0, 1fr)` + `.doors, .log { min-width: 0 }`. Với `1fr` thường, hàng chip
  tên cửa (nowrap) kéo trang rộng hơn màn hình → điện thoại zoom-out → thanh tab dưới rơi khỏi màn
  hình (bug 08/10).
- Xác nhận trước khi mở (bottom sheet trên điện thoại); "Mở tất cả" 2 bước, bước 2 giữ nút 1,5 s.
- Polling trạng thái 15 s khi tab đang hiện; "Tự làm mới 30s" (nhớ ở localStorage) gọi `fetch_logs`.
- Đếm ngược tính từ `open_remaining` do server trả (không phụ thuộc giờ máy client).
- **Chuỗi dịch:** mọi `__('...')` trong `index.html` được `index.py` gom tự động bằng regex, dịch
  server-side, nhúng vào `window.__messages`. Thêm chuỗi mới ⇒ thêm vào `translations/vi.csv`
  (test §9 mục 9 bắt chuỗi thiếu). Chuỗi HTML tĩnh dùng `{{ _('...') }}`.

## 9. Test

```bash
cd ~/frappe-bench/sites
../env/bin/python -c "import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); \
    exec(open('../apps/customize_erpnext/customize_erpnext/api/test_door_control.py').read())"
```

42 assert. Dựng Setting trong bộ nhớ (không ghi DB), chỉ kết nối `10.0.1.50` (relay kêu 2 lần) +
máy giả `192.0.2.1` (TEST-NET, offline); mọi máy cửa khác bị tắt trong bộ nhớ. Kết thúc rollback +
xoá cache key test. 🔴 `frappe.render_template` từ CHUỖI chặn `.__` ("Illegal template") — render
trang phải theo path (`is_path=True`).

Thay đổi `.py` cần `bench restart`; đổi field DocType cần `bench migrate` (hoặc `import_file_by_path`
cho đúng file JSON); `index.html` không cần restart.

## 10. Còn treo

1. **Giữ mở / Đóng:** đo thời gian unlock tối đa + `unlock(0)` có khoá sớm không (cần người đứng
   cạnh cửa). Xong ⇒ `HOLD_CLOSE_ENABLED = True`, chỉnh `HOLD_OPEN_SECONDS`, tick `allow_hold_close`.
2. **Sensor:** kỹ thuật kiểm tra dây NO/COM của LB-35 vào `SEN` + `GND`. Nếu chạy ⇒ hiệu chỉnh
   `SENSOR_STATES`; cửa 2 cánh (.48) cần biết 2 sensor nối tiếp hay song song.
3. **Realtime `EF_UNLOCK`:** biết lúc relay mở (kể cả vân tay) mà không cần sensor.
4. Tab 4.1 trên `/biometric_sync` chưa hiện máy cửa/máy tắt (chỉ dialog trên Desk có).

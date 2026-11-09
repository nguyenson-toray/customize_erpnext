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
| Quyền mở từng cửa (29/10/2026) | Door Alert Setting › tab **Unlock Permissions** (bảng con `Door Unlock Permission`: Door = Select máy cửa, options do `onload` gửi + JS đổ vào; Users = User ID gõ tay, cách nhau dấu phẩy). Ai có role vẫn **thấy mọi cửa**; chỉ chặn Unlock / Hold open / Close (server `_require_unlock`, nút bị tắt trên trang). Mở tất cả **bỏ qua** cửa không có quyền (trả `skipped`). Cửa không có dòng hoặc Users trống = mọi user Door Control. Administrator luôn được. Bảng ở **permlevel 1**: chỉ System Manager sửa, Door Control chỉ xem (Door Control vốn SỬA được Door Alert Setting). Lưu sẽ chuẩn hoá: Door nhận cả Location (nếu duy nhất) → Device Name, user không tồn tại → throw, user thiếu role → cảnh báo. Đổi Device Name trong Attendance Machine Setting tự cập nhật bảng (`on_update`), nếu không cửa đổi tên sẽ im lặng mở cho tất cả. Test: `test_unlock_permission.py` (không kết nối máy) |
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
| `sensor_installed` | Cửa này đã đấu sensor thật vào `SEN`/`GND` (mặc định 0). Chỉ cửa có tick mới được đọc sensor. **Hiện chỉ `.50` Production = 1** (19/10/2026) |
| `sensor_type` | `None` / `NO` / `NC` — cách đấu sensor (hiện khi tick `sensor_installed`). Phải khớp Door Sensor Mode trên menu máy (xem §6) |
| `allow_hold_close` | Hiện nút "Giữ mở"/"Đóng" cho cửa này. Hiện tất cả = 0 |
| `has_door_sensor` | Cột cũ, đã thay bằng `sensor_type`; còn trong DB, không dùng |

Validate (`attendance_machine_setting.py::_validate_door_controllers`): `unlock_seconds` 1–60
(cờ `master_device` đã bỏ 23/10/2026).

Cửa thật (08/10/2026): `.48` Machine 8 - Door - Office (cửa 2 cánh, 2 khoá),
`.49` Machine 9 - Door - IT, `.50` Machine 10 - Door - Production (trước 19/10 tên "Main Hall"). Khoá: **ZKTeco LB-35**
(fail-safe: có điện = khoá; trễ chốt 0/3/6 s chỉnh trên khoá; có sensor chốt NO/COM).

## 3. Tách biệt khỏi chấm công

`network/biometric/machines.py` là lớp truy cập duy nhất:

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
| `network/door/control.py` | Toàn bộ API + giao tiếp máy (docstring đầu file có các sự thật đo được) |
| `network/door/sensor.py` | Cảm biến cửa ESP32: endpoint `report` + đọc trạng thái cho trang / cảnh báo (§13) |
| `network/doctype/door_sensor/`, `door_sensor_event/` | Cửa chỉ giám sát + nhật ký đổi trạng thái (§13) |
| `network/door/access.py` | `store_door_punches()` dùng chung với tab "IT Door Access" cũ trên trang www /biometric_sync (đã bỏ 19/10/2026) |
| `network/biometric/machines.py` | Lọc máy cửa (§3) |
| `www/door_control/index.py` | Kiểm tra login/role, CSRF, gom chuỗi dịch |
| `www/door_control/index.html` | Toàn bộ UI (CSS + JS inline) |
| `network/doctype/door_control_action/` | Nhật ký lệnh ERP |
| `network/doctype/door_access_log/` | Log quẹt vân tay (có sẵn, thêm quyền Door Control) |
| `patches/create_door_control_role.py` | `pre_model_sync` — role phải có trước khi sync DocPerm |
| `api/test_door_control.py` | Test hồi quy (§9) |

## 5. API (`customize_erpnext.network.door.control.*`)

| Hàm | Method | Việc |
|---|---|---|
| `get_doors(force=0)` | GET | Máy cửa đang bật + trạng thái. Probe song song, cache 8 s/cửa (nhiều trình duyệt = 1 lần kết nối) |
| `unlock_door(device_name)` | POST | `conn.unlock(unlock_seconds)` + ghi Door Control Action |
| `hold_open` / `close_door` | POST | **Tạm tắt** (`HOLD_CLOSE_ENABLED = False`) — throw |
| `unlock_all()` | POST | Mở mọi cửa song song (cửa offline không làm chậm cửa khác) |
| `fetch_logs(device_name=None, force=0)` | POST | Đọc log máy → Door Access Log (30 ngày gần nhất). So số record với lần trước, không đổi thì bỏ qua. Không xoá log trên máy. `access.store_door_punches` chỉ lưu ID **khớp nhân viên** (từ 29/10/2026: ID không khớp = đối tác chấm công, bỏ qua như ID ≥ ngưỡng đối tác ⇒ "Unknown Fingerprint ID" của Door Alert Setting không còn tác dụng, đã ẩn) và ghi `device_name` theo IP lúc lưu (IP vẫn permlevel 1, chỉ Administrator thấy) |
| `get_timeline(device_name=None, limit=150)` | GET | Gộp Door Access Log + Door Control Action + Door Sensor Event (`kind: "sensor"`), mới nhất trước |

Lệnh lỗi **không throw** mà trả `{success: False}` — để dòng Failed của Door Control Action vẫn được
commit (throw sẽ rollback cả dòng log).

Kết nối: dùng `force_udp`/`timeout` của Setting; khoá theo từng máy bằng `filelock`; retry 2 lần.
Hàm `_run`/`_probe` không gọi frappe ⇒ chạy được trong ThreadPool.

## 6. Trạng thái cửa trên trang

- **Không sensor (hiện tại):** trang **KHÔNG hiện "Đã khoá"** (user yêu cầu 08/10/2026 — không
  phản ánh thực tế: kính thoát hiểm vỡ ở Main Hall làm chốt nhả mà trang vẫn báo khoá). Card ở
  trạng thái trung tính (icon cửa, dải xanh dương, không dòng trạng thái). Chỉ hiện điều chắc chắn:
  "Mở · còn Xs" sau lệnh ERP (cache `door_control:open:<hash>`) và "Ngoại tuyến". Bật lại hiển thị
  trạng thái cửa khi có sensor.
- **Có sensor (`sensor_installed` + `sensor_type` NO/NC + cờ `use_lock_sensor`):** đọc
  `CMD_DOORSTATE_RRQ` (75) → 1 byte; byte = `sensor_locked_value` (nhãn "Sensor Value When Closed")
  ⇒ `"closed"`, khác ⇒ `"open"`. Production `.50` (19/10/2026): **1 = cửa mở, 0 = cửa đóng** ⇒ giá trị = 0.
  Card hiện "Cửa đang mở / Cửa đang đóng" (+ "· Đã mở khóa · Xs" khi đang trong cửa sổ lệnh ERP);
  dải cam khi cửa mở hoặc đang mở khoá. Chỉ tin khi option `DSM` của máy khớp `sensor_type`; lệch ⇒
  bỏ sensor + cảnh báo cam trên card.
- **Nút "Mở khoá N giây"** (19/10/2026, phương án C): nút chỉ nhả chốt, không mở cánh ⇒ chữ là "Mở khoá"
  (hộp xác nhận, toast, dòng lịch sử cũng vậy). Sensor báo cửa đang mở và không trong cửa sổ lệnh ERP ⇒
  nút hạ thành nút viền + dòng "Cửa đang mở — không cần mở khoá". **Cố ý KHÔNG khoá nút**: số đọc có thể
  cũ tới `STATUS_CACHE_S`, và sensor hỏng không được phép chặn việc mở cửa. "Mở tất cả" giữ nguyên.
- **Màu card** (19/10/2026): sensor báo đóng ⇒ cả card nền xanh (`is-closed`); cửa mở hoặc đang trong
  cửa sổ mở khoá ERP ⇒ nền vàng (`is-open`). Cửa không sensor giữ nền trắng (không biết thật ⇒ không tô
  xanh). "Theo cảm biến cửa" nằm cùng hàng với trạng thái.
- **Máy offline:** không bao giờ hiện trạng thái cũ như hiện tại — card xám "Ngoại tuyến". Mỗi lần đọc
  được sensor, `sensor_reading` lưu cache `door_control:last_sensor:<hash>` = {state, at} 24 h
  (`LAST_SENSOR_TTL_S`); card offline hiện dòng phụ "Lần đọc cuối: Cửa đang mở · 21:40", tin Telegram
  "Door device offline" thêm "last reading: **DOOR OPEN** at 21:40".
- 🔴 **Mã option `DSM` (đo thật, fw 6.60): `0=NO`, `1=NC`, `2=None` (mặc định nhà máy).** Đừng tin
  tài liệu/đoán — từng đoán ngược và gây cảnh báo sai.

## 7. Sự thật đo trên máy thật (F21Lite, fw Ver 6.60 May 14 2018, ZMM220_TFT)

- pyzk 0.9 chỉ có `unlock(seconds)` — gửi `pack("I", seconds*10)`. Không có lệnh "đóng ngay";
  `unlock(0)` được ACK nhưng chưa xác minh có khoá sớm không.
- **Mở bằng phần mềm KHÔNG ghi log trên máy** ⇒ Door Control Action là nguồn duy nhất biết ai mở.
- `CMD_DOORSTATE_RRQ` khi CHƯA đấu sensor **luôn `01`** — kể cả chốt nhả, mở cánh, đóng, khoá
  (~800 lần đọc trên .48 với 4 lần quẹt, DSM=NO). 19/10/2026 user lắp sensor cho `.50`: 1 = mở, 0 = đóng.
- Thời gian unlock tối đa: **không có tài liệu nào xác nhận** (SDK `ACUnlock(Delay)` không ghi
  đơn vị/giới hạn; tài liệu Axxon gợi ý 1–254 s). `HOLD_OPEN_SECONDS = 900` là chưa kiểm chứng.
- TCP: kết nối lại ngay sau disconnect → BrokenPipe; UDP (Setting đang `force_udp=1`) không bị.
- pyzk có `reg_event(EF_ALARM | EF_UNLOCK …)` nhưng `live_capture` chỉ parse log chấm công;
  nghe sự kiện realtime cần tiến trình chạy nền riêng — **chưa thử**.

🔴 Quy ước khi test: máy `.50` được thử tự do (đã từng là máy test); `.49` **chỉ đọc**; máy khác
phải hỏi. Không `disable_device`, không ghi option khi chỉ được phép đọc.

## 8. UI

- Mobile-first. < 640 px: card gọn (~165 px) để **3 cửa/màn hình**; Open/Hold/Close chung 1 hàng.
- **Tên hiển thị = field `location`** của dòng máy (19/10: "Production", "Office", "IT"), trống thì dùng
  `device_name`. Dùng cho card, chip lọc, nhật ký, hộp xác nhận, toast VÀ tin Telegram. `device_name`
  vẫn là khoá (API, filter), hiện ở tooltip tiêu đề; dòng phụ chỉ còn IP. Card offline không có dòng
  lỗi riêng (lỗi ở tooltip chữ "Ngoại tuyến"). ≥ 1200 px: 3 cột.
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

`test_door_control.py` tắt `frappe.log_error` trong lúc chạy (Error Log ghi ngoài transaction, rollback không xoá). Thay đổi `.py` cần `bench restart`; đổi field DocType cần `bench migrate` (hoặc `import_file_by_path`
cho đúng file JSON); `index.html` không cần restart.

## 10. Còn treo

1. **Giữ mở / Đóng:** đo thời gian unlock tối đa + `unlock(0)` có khoá sớm không (cần người đứng
   cạnh cửa). Xong ⇒ `HOLD_CLOSE_ENABLED = True`, chỉnh `HOLD_OPEN_SECONDS`, tick `allow_hold_close`.
2. **Sensor `.48` / `.49`:** chưa lắp. Lắp xong ⇒ Read Sensors Now (đóng/mở phải đổi giá trị) ⇒ tick
   `sensor_installed`; cửa 2 cánh (.48) cần 2 sensor nối tiếp.
3. **Realtime `EF_UNLOCK`:** biết lúc relay mở (kể cả vân tay) mà không cần sensor.
4. Tab "Sync ERP → Machines" trên trang desk `biometric-sync` chưa hiện máy cửa/máy tắt (chỉ dialog trên Desk có).

## 11. Cảnh báo Telegram (`network/door/alerts.py`, 09/10/2026)

Plan + quyết định: `.claude/plans/door_alerts.md`.

- **Setting:** Single `Door Alert Setting` (module Network) — tạo **TẮT**, bảng `recipients`
  (`Door Alert Recipient`: label, chat_id, enabled); bot token là field Password.
  Nút: **Send Test Message** (gửi được cả khi tắt) · **Get Chat ID** (đọc `getUpdates`, cần gõ
  `/start@<bot>` trong group trước vì bot ở privacy mode; group nâng cấp supergroup → id mới) ·
  **Check Now** (chạy ngay, bỏ qua chu kỳ). Khung trạng thái (HTML) trên form: cửa đang theo dõi +
  online, lần kiểm tra/gửi cuối, số tin hôm nay, lỗi gần nhất. Trang /door_control có nút ⚙ tới
  form. Quyền: System Manager + Door Control.
- **Sự kiện (09/10 bản 2):** `erp_open_alert` / `fingerprint_alert` = Off / After Hours / Always ·
  `alert_unknown_user` · `alert_device_offline` (+ `offline_after_minutes`) · `alert_unlock_all` ·
  `alert_command_failed`. 1 lần mở = 1 dòng ("ngoài giờ" thắng). "Mở tất cả" = đúng 1 dòng "N/M cửa đã mở" (chỉ nêu tên cửa LỖI), gom theo người bấm + khoảng cách ≤ 10 s chứ không theo phút đồng hồ. Patch
  `door_alert_setting_select_fields` chuyển 4 ô tick cũ sang 2 Select.
- **Chọn cửa:** ô `send_door_alerts` trên dòng máy cửa của Attendance Machine Setting (mặc định bật).
- **Người nhận theo loại (22/10/2026):** mỗi dòng `recipients` có 2 ô **Door Alerts** (mở cửa, vân tay,
  mở tất cả, lệnh lỗi, cửa mở ngoài giờ, tổng hợp ngày) và **Device Alerts** (máy offline / có lại), mặc
  định cùng bật. Tin thiết bị và tin cửa gửi thành 2 tin riêng. Không ai nhận một loại ⇒ bỏ qua, không
  tính là lỗi gửi. Chat riêng: mở bot → Start → nút Get Chat ID.
- 🔴 **Trạng thái cảnh báo theo cửa nằm trong DB** (field ẩn `alert_state`, JSON, chỉ ghi khi đổi), KHÔNG
  ở Redis: `frappe.clear_cache()` (bench clear-cache, migrate, lưu vài cài đặt) xoá MỌI key cache của
  site trừ `persistent_cache_keys`. 21/10/2026 máy Production offline cả ngày ⇒ mỗi lần clear-cache
  trạng thái mất ⇒ 8 tin "offline for 7–8 minutes" lặp, không có tin "back online" nào. Trạng thái cảm
  biến cuối (`door_control:last_sensor:*`) vẫn ở Redis nhưng khai trong `persistent_cache_keys`
  (hooks.py) nên sống qua clear-cache; chỉ mất khi Redis khởi động lại (~1 lần/tuần, ~06:xx). Mỗi
  lượt job đọc lại sensor của cửa online ⇒ tin offline có "last reading" kể cả khi không ai mở trang.
- **Mute Until:** trước thời điểm đó không gửi gì; sự kiện bị BỎ (không dồn lại), mốc vẫn dời.
- **Bối cảnh vận hành:** giờ làm (mặc định 06:00–22:00, mọi ngày) công tắc trên khoá để OFF ⇒
  chốt luôn nhả, ~1000 công nhân qua lại ⇒ hoạt động cửa trong giờ KHÔNG báo. Ngoài giờ báo ngay
  mọi lượt quẹt + mọi lệnh mở từ ERP. Tin ghi mã NV + họ tên.
- **Job:** cron `* * * * *` → `door_alerts.tick()`. Tắt ⇒ đọc 1 field rồi thoát. Bật ⇒ mỗi
  `check_interval_minutes`: probe cửa, đọc log **không `disable_device`** (job không bao giờ làm
  cửa từ chối vân tay), lấy Door Control Action + Door Access Log có `creation` trong cửa sổ
  (`last_check_at`, now] → gom thành **1 tin / người nhận / loại** (Door / Device). Tổng hợp ngày: 1 lần sau
  `daily_summary_time`.
- **Sự kiện:** mất kết nối ≥ N phút (1 tin mất + 1 tin có lại) · Mở tất cả (gộp 1 sự kiện) · lệnh
  lỗi · mở từ ERP ngoài giờ · quẹt ngoài giờ · ID lạ (mọi lúc). Tuỳ chọn thêm (09/10, user yêu cầu):
  `alert_every_erp_open` / `alert_every_fingerprint` — báo MỌI lần mở từ ERP / mọi lượt quẹt, kể cả
  trong giờ; 1 lần mở vẫn 1 dòng ("ngoài giờ" thắng khi áp dụng). Chỉ xét cửa đang bật trong Setting. Punch có `timestamp` cũ hơn 30 phút
  (log tồn đọng lần đầu đọc máy) chỉ lưu, không báo.
- **Bền vững:** gửi lỗi ở MỌI người nhận ⇒ không dời `last_check_at` (lần sau gửi lại, tối đa
  nhìn lùi 1 ngày); token bị thay `<token>` trong mọi lỗi. Trạng thái runtime ghi bằng
  `set_value(update_modified=False)` ⇒ admin đang mở form không bị TimestampMismatch.
- **Ngôn ngữ tin:** theo System Settings → hiện là `en` ⇒ tin tiếng Anh (bản dịch vi đã có trong
  vi.csv nhưng chưa dùng; user: "dịch để sau").
- **Test:** `api/test_door_alerts.py` (56 assert; máy giả, `requests.post` mock, không gửi thật).
- 🔴 Cron mới cần `bench migrate` (restart không đủ).

## 12. Cảm biến cửa + cảnh báo "cửa mở sau giờ làm" (10/10/2026, đổi 19/10/2026)

Plan: `.claude/plans/door_sensor.md`.

- **Cờ tổng** `Door Alert Setting.use_lock_sensor` (mặc định TẮT): tắt ⇒ `door_control._apply_sensor_flag`
  ép `has_door_sensor = False` ⇒ không đọc sensor/DSM, trang + form + Telegram không hiện gì về sensor.
- **Ánh xạ**: `sensor_locked_value` (Select 1/0, mặc định 1) thay hằng `SENSOR_STATES`.
  `door_control.sensor_reading(door, probe)` → ("locked"/"unlocked"/None, mismatch) — dùng chung cho
  trang, khung trạng thái và cảnh báo. Lệch Door Sensor Mode ⇒ None.
- **Sensor Type mặc định NO** (patch `door_sensor_type_default_no` đặt NO cho 3 cửa; máy chấm công giữ None).
- **Cảnh báo** (`door_alerts._not_locked_events`): ngoài giờ, chốt nhả liên tục ≥ 2 phút
  (`NOT_LOCKED_CONFIRM_MIN`, lọc quẹt vân tay/mở ERP) ⇒ 🔴 "Door not locked after hours"; nhắc mỗi
  `not_locked_repeat_minutes` (mặc định 30) ⇒ "Door still not locked"; khoá lại ⇒ 🟢 "Door locked".
  Vào giờ làm ⇒ xoá trạng thái, im lặng. Offline/lệch DSM ⇒ giữ trạng thái, không báo. Trạng thái ở cache
  `door_alerts:not_locked:<cửa>`; `last_sent` chỉ dời khi gửi được (hoặc đang mute).
- **Read Sensors Now** (`door_alerts.read_sensors`): đọc thô mọi cửa kể cả khi cờ tắt — để hiệu chỉnh.
  10/10: cả 3 cửa đọc `1`/DSM=NO, kể cả Main Hall đang nhả chốt ⇒ **sensor chưa đấu dây — KHÔNG bật cờ**
  (bật lúc này sẽ luôn báo "đã khoá", không bao giờ cảnh báo).
- Test: `test_door_alerts.py` 81 assert, `test_door_control.py` 52 assert.

**19/10/2026 — đổi sang cảm biến CỬA (đóng/mở), áp dụng từng cửa:**
- Thêm `Attendance Machine Detail.sensor_installed` (mặc định 0): `has_door_sensor` =
  `sensor_installed` AND `sensor_type ∈ {NO, NC}` AND cờ tổng. Đã tick cho `.50`; `.48/.49` = 0.
- Trạng thái đổi tên `locked/unlocked` → `closed/open`; tin Telegram: "Door left open after hours",
  "Door still open", "Door closed". **Fieldname giữ nguyên** (`use_lock_sensor`, `sensor_locked_value`,
  `alert_not_locked_after_hours`, cache `door_alerts:not_locked:*`) — chỉ đổi nhãn để khỏi patch dữ liệu.
- DB: `use_lock_sensor = 1`, `sensor_locked_value = 0`, `alert_not_locked_after_hours` vẫn 0.
- 19/10/2026: `.50` đổi tên `Machine 10 - Door - Main Hall` → `Machine 10 - Door - Production`, Location
  `Production` (SQL trực tiếp + 17 dòng `Door Control Action.device_name`; cache theo tên máy rỗng, không phải chuyển).
  ⚠ Tên máy là khoá của cache/lock file (`_key` băm tên) và của lịch sử Door Control Action — đổi tên phải sửa cả hai.
- `door_control.sensor_closed_value()` đọc giá trị trong Setting (test patch hàm này).

## 12. UDP + dò nhanh (23/10/2026)

- Máy cửa **luôn đi UDP** (`biometric/machines._row_to_dict`), bất kể ô Force UDP của Setting — ô đó đã bỏ tick
  cho máy chấm công (đọc log TCP nhanh gấp 15 lần). Qua TCP, F21Lite lỗi BrokenPipe khi kết nối lại ngay sau khi
  ngắt (Tab 3 đẩy vân tay từng NV một → kết nối lại liên tục).
- Dò trạng thái (`_probe`) thử TCP 4370 trước, tối đa `PROBE_PRECHECK_S`=1,5 s: máy tắt nguồn → báo offline sau
  1,5 s thay vì 7,5 s (UDP) / 13,8 s (TCP). Lệnh mở/đóng cửa KHÔNG qua bước này (máy chậm vẫn phải nhận lệnh).
- Máy tắt lâu ngày: bỏ tick Enable trong Setting để trang không phải dò nó.
- ⚠ 22–23/10 Telegram trả "Unauthorized bot" → cảnh báo cửa KHÔNG tới được ai (token bot sai/bị thu hồi).

## 13. Door sensors (ESP32) — cửa chỉ giám sát (02/11/2026)

Cửa không có F21/khoá, chỉ cần biết **đóng hay mở**. Mỗi cửa có một board ESP32-C6 Super Mini + cảm biến
từ; board tự POST về ERP qua Wi-Fi. ERP **không bao giờ** gọi ngược board (không lệnh, không polling).

### Hợp đồng (firmware viết theo)

```
POST /api/method/customize_erpnext.network.door.sensor.report
Authorization: token <api_key>:<api_secret>
Content-Type: application/json

{"door_id": "KHO-01", "state": "open", "event": "change", "age_ms": 120,
 "rssi": -61, "ip": "10.0.1.80", "fw": "1.0.0"}
→ 200 {"message": {"ok": true, "changed": <bool>}}
```

- Board gửi khi đổi trạng thái (lỗi mạng → thử lại mỗi 5 s, luôn gửi trạng thái mới nhất), heartbeat 60 s, 1 lần lúc boot.
- **Mọi report đã xử lý đều trả 200** (trùng lặp, sensor tắt, door_id lạ): board coi mã khác 200 là lỗi và gửi lại mãi.
  Chỉ lỗi khi: token sai (401) / không có role Door Sensor (403) · dữ liệu sai (417: `door_id` không khớp `[A-Za-z0-9._-]{1,32}`,
  `state` ∉ open/closed/fault, `event` ∉ boot/change/heartbeat, `age_ms` không phải số).
- `age_ms` < 0 hoặc > 24 h ⇒ coi như 0. Thời điểm đổi thật = lúc nhận − `age_ms`. Trường lạ được bỏ qua (`**kwargs`).
- `state != last_state` (kể cả `unknown`) ⇒ cập nhật `last_state` + `last_state_change` + insert **Door Sensor Event**
  (có `previous_state`), `changed: true`. Heartbeat cùng trạng thái chỉ cập nhật `last_seen`/IP/RSSI/firmware.
- Ghi bằng `db.set_value(update_modified=False)`, `track_changes = 0` ⇒ heartbeat mỗi phút không sinh Version, không đổi `modified`.
- `filelock` theo door_id (2 request của 1 board có thể chồng nhau). Request không gọi Telegram.
- **door_id lạ (đã chọn):** tự tạo `Door Sensor` với `enabled = 0` + 1 Error Log "Door Sensor", trả 200 `ok: false`.
  Admin chỉ cần tick Enabled + gõ Location. Lý do: throw ⇒ board gửi lại mỗi 5 s mãi mãi + đầy Error Log. Tối đa
  `MAX_PENDING = 20` sensor đang tắt; vượt ⇒ từ chối (417) — chặn key bị lộ tự bịa door_id. Sensor `enabled = 0` ⇒ 200
  `ok: false, reason: disabled`, chỉ cập nhật last_seen/IP/firmware, không Event, không cảnh báo, không lên trang.

### Role + user kỹ thuật

- Role **`Door Sensor`** (patch `create_door_sensor_role`, `pre_model_sync`, `desk_access = 0`): không có quyền DocType
  nào, không vào được `/door_control` (trang + API đòi `Door Control`). User chỉ có role này là **Website User**.
- Tạo user (1 user dùng chung cho mọi board, hoặc mỗi board 1 user nếu muốn thu hồi riêng):
  1. User › New: Email `door-sensor@tiqn.com.vn`, First Name `Door Sensor`, bỏ tick *Send Welcome Email*.
  2. Tab Roles: chỉ tick **Door Sensor** (bỏ mọi role mặc định khác). Lưu.
  3. Tab Settings › API Access › **Generate Keys** ⇒ copy API Secret ngay (chỉ hiện 1 lần). API Key nằm trên form.
  4. Nạp `api_key:api_secret` vào firmware. **Không** ghi key/secret vào repo, README hay ticket.
- Thu hồi: Generate Keys lại (secret cũ hết hiệu lực) hoặc tắt user.
- ⚠ **Role Profile:** nếu user được gán Role Profile (ô *Role Profile* trên form), mỗi lần lưu Frappe đặt lại role theo
  profile ⇒ bỏ tick Door Control / tick Door Sensor không có tác dụng. Xoá ô Role Profile trước rồi mới chỉnh role.
  Tuyệt đối không để user của board có role **Door Control**: key nằm trong board, lộ key = mở được cửa thật.
- Bấm vào tên role Door Sensor trong tab Roles hiện "Door Sensor role does not have permission on any doctype" — **bình
  thường**, đúng thiết kế: `report` kiểm role bằng `frappe.only_for`, rồi tự ghi với `ignore_permissions`.
- Đang dùng (03/11/2026): user **`esp32_door@tiqn.com.vn`** (Website User, chỉ role Door Sensor), sensor
  `production_canteen` (enabled). Đã test từ PC; **chưa có board thật**.

### DocType

- **Door Sensor** (`autoname: field:sensor_id`): `sensor_id` (= door_id, unique, không trùng Device Name máy cửa —
  validate), `location` (tên hiển thị), `enabled`, `send_door_alerts`, `last_state` (open/closed/fault/unknown),
  `last_state_change`, `last_seen`, `sensor_ip` (**permlevel 1** ⇒ chỉ Administrator thấy, như `device_ip`), `sensor_rssi`,
  `sensor_fw`, `note`. Quyền: System Manager đủ; Door Control đọc.
- **Door Sensor Event** (`autoname: hash`, `event_time DESC`, `in_create`): `door_sensor`, `state`, `previous_state`,
  `event_time`, `event`, `received_at`. Chỉ ghi khi đổi trạng thái. Quyền: chỉ đọc cho System Manager (+ xoá),
  Door Control, HR User.
- Không đụng Attendance Machine Setting/Detail, không qua pyzk.

### Cảnh báo (`alerts.run_checks`, cùng `tick` mỗi phút)

| Sự kiện | Điều kiện | kind |
|---|---|---|
| Door opened / Door opened after hours | Door Sensor Event `open` tạo trong cửa sổ, `sensor_open_alert` = After Hours / Always | door |
| Door left open after hours / still open / closed | `alert_not_locked_after_hours` (không cần Use Door Sensor), mở ≥ 2 phút ngoài giờ tính từ `last_state_change`, nhắc mỗi `not_locked_repeat_minutes` | door |
| Door sensor fault / working again | Event `fault` hoặc `previous_state = fault`, `alert_sensor_fault` | device |
| Door sensor offline / back online | `now − last_seen > offline_after_minutes`, `alert_device_offline`; tin offline kèm trạng thái cuối | device |

- Chỉ sensor `enabled = 1` + `send_door_alerts = 1` gây cảnh báo. Phát hiện offline chạy cho MỌI sensor đang bật và đặt
  `last_state = "unknown"` (UPDATE có điều kiện `last_seen` ⇒ không đè report vừa tới). Board có lại ⇒ report đầu tiên
  (unknown → X) ghi Event; nếu là `open` thì tin ghi chú "first report after the sensor was offline or restarted".
- Khoá trong `alert_state`: `door_alerts:sensor_offline:<id>`, `door_alerts:sensor_open:<id>` (không đụng khoá của máy cửa).
- Field mới (tab Door Sensor › ESP32 Door Sensors): `sensor_open_alert` (Off), `alert_sensor_fault` (0). Bỏ
  `depends_on: use_lock_sensor` của `alert_not_locked_after_hours` vì giờ dùng cho cả ESP32.
- Khung trạng thái trên form có thêm bảng Door Sensor (Online/Offline, trạng thái, Last seen, RSSI).

### Trang /door_control

- `get_doors` trả thêm sensor đang bật, `kind: "sensor"` (cửa F21: `kind: "lock"`); `online` = `last_seen` trong
  `offline_after_minutes`; `can_unlock: false`; IP chỉ cho Administrator.
- Thẻ cảm biến: Door open / Door closed / Sensor fault / Offline + "From the door sensor", dòng cuối "Since {giờ đổi}"
  (offline: "Last seen …"). Không nút nào, không "Try to reconnect". "Mở tất cả" chỉ xét `kind !== "sensor"`.
- Nhật ký: sự kiện `kind: "sensor"` (Door opened / Door closed / Sensor fault), chú thích nguồn thêm "Sensor".

### URL cho board (đo 02/11/2026)

- DNS LAN `10.0.1.3` trả `erp.tiqn.com.vn → 10.0.1.20` (split DNS; DNS công cộng trả IP WAN 103.17.90.89).
- Cả 2 server block cổng 8888 đều `proxy_set_header X-Frappe-Site-Name erp.tiqn.local` ⇒ Host header nào cũng vào đúng site.
- **Khuyến nghị:** `https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.network.door.sensor.report` — cert Let's
  Encrypt hợp lệ, board có thể kiểm chứng bằng root CA ISRG Root X1. Điều kiện: Wi-Fi nhà máy cấp DNS `10.0.1.3`/`10.0.1.6`
  (nếu Wi-Fi dùng DNS công cộng thì tên này ra IP WAN, phụ thuộc NAT hairpin). Kiểm: `nslookup erp.tiqn.com.vn` từ điện thoại
  cùng Wi-Fi phải ra `10.0.1.20`.
- Dự phòng: `https://10.0.1.20:8888/...` — chạy được (vào server block mặc định), nhưng cert không khớp IP ⇒ firmware phải
  bỏ kiểm cert (`setInsecure`). `erp.tiqn.local` cũng vậy (cert tự ký) và cần DNS nội bộ biết tên này.

```bash
curl -X POST https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.network.door.sensor.report \
  -H "Authorization: token <key>:<secret>" -H "Content-Type: application/json" \
  -d '{"door_id":"TEST-01","state":"open","event":"change","age_ms":0,"rssi":-60,"ip":"10.0.1.99","fw":"1.0.0"}'
```

Windows PowerShell (dấu `\` cuối dòng là của bash; dán lệnh trên vào PowerShell thì `curl` chạy không kèm header ⇒ Guest ⇒
"Login to access … is not whitelisted"):

```powershell
$h = @{ Authorization = "token <key>:<secret>" }
$b = @{ door_id="TEST-01"; state="open"; event="change"; age_ms=0; rssi=-60; ip="10.0.1.99"; fw="1.0.0" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.network.door.sensor.report" -Headers $h -ContentType "application/json" -Body $b
```

Lưu ý: lệnh test ghi dữ liệu thật (Event + IP giả trên Door Sensor) tới khi board thật gửi đè.

### Ghi chú firmware

- **Wokwi không gửi thật:** firmware bỏ Wi-Fi khi giả lập (`[SIM] Bo qua Wi-Fi`), dòng `>>POST …` chỉ là in Serial. Kể cả có
  mạng, Wokwi đi ra Internet qua gateway của nó, không vào được LAN 10.0.1.x ⇒ phải test trên board thật trong Wi-Fi nhà máy.
- **Không in token ra Serial** (bản 1.0.0 đang in `api_key:api_secret`). Test xong: Generate Keys lại, nạp secret mới.
- **Cửa đóng mở liên tục** (canteen…): server chịu được (≈1.000 lượt/ngày ≈ 2.000 request + 1.440 heartbeat, vài chục ms
  mỗi request). Nên làm phía firmware:
  - chống dội: chỉ coi là đổi khi tín hiệu đứng yên ~50 ms (cửa có tay co bật lại: ~1 s, đổi lại mất lần mở < 1 s);
  - giữ kết nối TLS (`http.setReuse(true)` + giữ `WiFiClientSecure`): mỗi lần bắt tay TLS trên ESP32-C6 ~1 s + tốn heap;
  - bỏ heartbeat nếu 60 s qua đã gửi một report bất kỳ.
- Cảnh báo cho cửa đông người: để `sensor_open_alert = Off`, dùng "Door Open After Hours" (chỉ báo khi bị bỏ mở quá N phút
  ngoài giờ); không muốn cảnh báo gì ⇒ bỏ tick *Send Door Alerts* trên Door Sensor.

### Còn treo (làm khi có board thật)

- Nhật ký "tất cả cửa" chỉ lấy 150 sự kiện mới nhất ⇒ một cửa cảm biến đông người sẽ đẩy mất log vân tay/ERP của cửa F21.
  Hướng sửa: ở chế độ tất cả cửa giới hạn sự kiện cảm biến (vd. tối đa 30), lọc riêng cửa thì hiện đủ.
- Door Sensor Event không tự xoá (~2.000 dòng/ngày với cửa đông). Hướng sửa: `default_log_clearing_doctypes`
  (`hooks.py`, giữ 90 ngày) + `clear_old_logs` trên controller ⇒ Log Settings tự dọn; cần migrate + restart.
- Chưa dịch vi.po các chuỗi mới (trang `/door_control`, Door Alert Setting, tin Telegram).
- Xác nhận Wi-Fi nhà máy cấp DNS `10.0.1.3`/`10.0.1.6` (xem "URL cho board").

### Test

`network/door/test_sensor.py` — 56 assert, chạy tay như các test khác (không kết nối máy cửa, `requests.post` mock, user +
sensor test tạo trong transaction rồi rollback): quyền (Door Control / Guest bị chặn, user Door Sensor không vào /door_control),
report (boot/change/heartbeat, trùng, age_ms, dữ liệu sai, sensor tắt, door_id lạ, modified không đổi), get_doors/timeline/unlock_all,
và `run_checks` (mở ngoài giờ, Always/Off, fault, offline + unknown, có lại, mở quá lâu, Send Door Alerts tắt).


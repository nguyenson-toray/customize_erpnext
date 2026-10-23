# network/biometric — máy chấm công ↔ ERPNext

Từ 23/10/2026 toàn bộ việc với máy chấm công chạy trong customize_erpnext; service
`biometric-attendance-sync-tool` (systemd `erpnext-sync-all`) đã dừng, sẽ gỡ hẳn khi lấy log tự động ổn định.
Plan + quyết định: `.claude/plans/biometric_tool_slimdown.md`. UI: trang `/app/biometric-sync`
(tài liệu `network/page/biometric_sync/biometric_sync.md`). Máy cửa: `network/door/README.md`.

## File

| File | Nội dung |
|---|---|
| `device_log_sync.py` | **Lấy log tự động** mỗi 3 phút: máy → Employee Checkin |
| `mongodb_sync.py` | MongoDB AttLog + OtRegister → ERPNext (Tab 6 thủ công + cron 18:00). Tạm thời |
| `resync.py` | Tab 6: re-sync máy theo khoảng ngày, xoá OT; `_add_checkin` dùng chung cho mọi lần nhập log |
| `biometric_sync.py` | Tab 2–5: vân tay máy → ERP, xoá NV nghỉ trên máy, quản lý máy, sync giờ (cron thứ Hai 05:00) |
| `fingerprint.py` | Vân tay trên Employee (dialog quét) + đẩy NV xuống máy (batch 1 kết nối) |
| `zk_device.py` | Helper pyzk dùng chung: config, connect, đọc log, `upsert_users`, tên ngón, rút gọn tên |
| `machines.py` | Lớp duy nhất đọc Attendance Machine Setting (`get_machines` / `get_machine`, chặn máy cửa). Comm key từng máy (`comm_password`, Data, trống = không key, chỉ số 0–999999) đi vào dict máy dưới key `password` → `build_zk_cfg`; 🔴 dict máy trả về trình duyệt phải qua `public_machine()` |
| `auth.py` | `check_biometric_access` (System Manager / HR Manager / HR User) |
| `log_viewer.py` | Tab 1: `sites/<site>/logs/biometric_*.log` + log cũ của tool (`tool/<file>`) |
| `error_report.py` | Endpoint email lỗi mà tool cũ gọi qua REST — chỉ System Manager (trước 23/10 mọi user đều gửi được mail tuỳ ý); xoá cùng lúc gỡ service |
| `test_device_log_sync.py` | Hồi quy chạy tay (máy/DB/mail đều giả) |

`customize_erpnext/api/{biometric_*,attendance_machines,door_*}.py` và phần vân tay trong
`api/utilities.py` chỉ còn **file chuyển tiếp** (`import *`) cho trình duyệt còn giữ JS cũ — xoá sau ~1 tuần.

## Lấy log tự động (`device_log_sync.py`)

- Bật/tắt: **Attendance Machine Setting → Auto Log Sync → Auto Pull Attendance Logs**. Tắt = cron không làm gì.
- Máy: mọi dòng **Enable** của Setting, trừ máy cửa. Thêm/bớt máy = sửa Setting (chỉ System Manager).
- Cron `*/3 * * * *` → `enqueue_device_log_sync` → queue **`biometric`** (worker riêng, khai trong
  `common_site_config.json → workers`), `job_id` cố định + `deduplicate` nên không bao giờ chạy chồng.
  Chưa khai worker thì job rơi về queue `long`.
- **Mốc lấy của mỗi máy = MAX(`Employee Checkin.time`) WHERE `device_id` = tên máy** (index
  `idx_emp_checkin_device_time`, patch `add_employee_checkin_device_time_index`). Không có file trạng thái.
  Không bao giờ lấy trước **Import Start Date**.
- Lượt có giờ ≥ mốc được gửi lại; `_add_checkin` tự bỏ lượt đã có (kiểm employee + time trước khi insert).
- **Đọc 7 máy SONG SONG** (1 thread/máy, chỉ pyzk — `zk_device.read_attendance`), ghi DB tuần tự ở thread chính.
  Đo 23/10: cả pha đọc **23 s** (= máy chậm nhất, Machine 7) thay vì ~90 s đọc lần lượt; mỗi máy vẫn chỉ bị khoá
  trong lúc đọc chính nó (9–23 s). 🔴 Code trong thread KHÔNG được gọi `frappe.*` (db/cache/log_error là thread-local).
  Không bắt đầu đọc trong giờ cao điểm hoặc < 60 s trước giờ cao điểm (`PEAK_START_MARGIN`).
- Bỏ qua: uid 0 / user_id rỗng (log rác năm 2000 của máy 6/7), giờ > hiện tại + 10 phút (đồng hồ máy sai
  không được kéo mốc ra tương lai).
- Lỗi ghi bất thường → **dừng máy đó ở chu kỳ này** (mốc không vượt qua lượt lỗi), chu kỳ sau thử lại.
- Mất kết nối: chỉ tính là lỗi từ **lần thứ 3 liên tiếp** (~9 phút); Error Log ghi 1 lần lúc chạm 3.
- Email lỗi: Setting → Error Email. **Mặc định tắt + không có người nhận**; tối đa 1 mail / cooldown.
- `clear_from_device_on_fetch` read-only, mặc định 0 (xoá log trên máy sau khi đọc = có thể mất dữ liệu).
- **Peak Times / Peak Window Minutes** (Setting, mặc định `07:30,07:45,17:00,18:00` / 15'): đọc log KHOÁ máy
  8–22 s (`disable_device`), nên trong cửa sổ cao điểm **không đọc máy nào**. Kiểm tra ở cron VÀ trước từng máy
  (chu kỳ ~90 s có thể lấn sang giờ cao điểm). Xoá trống = tắt; chưa từng đặt hoặc giá trị hỏng = mặc định
  (phía an toàn). Dry run cũng tôn trọng giờ cao điểm trừ khi `ignore_peak=1`.
  Số liệu chọn mặc định (01–22/10/2026, 7 máy): 17:00–17:10 ~620 lượt/ngày = 1 lượt/7 s/máy;
  07:40–08:00 ~730; 18:00–18:10 ~290; 07:20–07:40 ~340; 19:00 ~130.
- **Ghi dồn sau cao điểm** (~950 lượt lúc 08:00; Machine 7 tối đa 331) vào hết trong **1 chu kỳ** (~2–5 phút,
  ghi ~0,1–0,3 s/lượt): ghi checkin KHÔNG xếp job nào (Attendance Calculation Setting →
  `recalc_attendance_on_checkin_change` = 0; công tính hourly + job email 08:20 tự `recalculate_attendance`).
  🔴 Email 08:20 tính công TỪ checkin → checkin tới 08:15 phải vào ERP trước 08:20. Đừng hạ
  `MAX_INSERTS_PER_MACHINE` (1000) — đặt 50 thì Machine 7 mất 6–7 chu kỳ, xong ~08:20–08:28 (đã tính 23/10).
  Vẫn giữ: dừng chu kỳ khi queue `short` > 400 job (phòng khi bật tính công theo checkin — Frappe chặn ở 550,
  `QueueOverloaded` từng xảy ra 16/09) và `QueueOverloaded` lúc ghi = hoãn, không tính lỗi.
- Log mỗi máy mỗi chu kỳ: `sites/<site>/logs/biometric_device_sync.log`.
- **Kiểm tra job còn sống** (`check_heartbeat`, cron `*/15`): cứ quá 15 phút (không tính giờ cao điểm) mà không có
  chu kỳ nào ĐỌC XONG máy → Error Log 1 lần/đợt + email theo cooldown. Bắt được: worker `biometric` chết, job
  dedupe bị kẹt, queue `short` bận nhiều giờ, job crash trước khi đọc. KHÔNG bắt được: scheduler chết (cron này
  cũng chạy trên scheduler). Mốc nằm ở cache `biometric_device_log_sync:*` — giữ qua `bench clear-cache`
  (hooks `persistent_cache_keys`). Tắt Auto Pull → xoá mốc (bật lại không bị coi là treo).
- **Thao tác tay trong giờ cao điểm**: trang `/app/biometric-sync` (đọc user, sync, quét/xoá NV nghỉ, Users,
  Reboot, đẩy NV, Re-sync) và dialog đẩy vân tay ở Employee hỏi xác nhận (`get_peak_status`). 1 câu trả lời có
  hiệu lực 2 phút (vòng lặp Tab 3 không hỏi lại). Info / Sync Time không hỏi (< 1 s, không khoá máy).
- ⚠ `clear_from_device_on_fetch` (read-only, 0): nếu bật, log trên máy bị xoá NGAY sau khi đọc, TRƯỚC khi ghi vào
  ERP → lượt nào ghi lỗi / bị hoãn (queue bận, giới hạn) là MẤT. Đừng bật; xoá log máy thủ công sau khi chu kỳ
  báo `new=1`.
- Chạy thử chỉ đọc (không ghi, không xoá, không mail, chạy cả khi đang tắt):
  `bench --site erp.tiqn.local execute customize_erpnext.network.biometric.device_log_sync._run_device_log_sync --kwargs '{"dry_run": 1}'`

## ⚠ Bẫy

1. **Đọc log hàng loạt phải đi TCP** (`zk_device.bulk_read_cfg`): Setting đặt `force_udp=1` cho mọi máy;
   đo 23/10 trên Machine 1 (32.939 log) UDP **142 s**, TCP ~9 s. pyzk KHÔNG lọc được theo ngày: mỗi lần đọc là tải
   TOÀN BỘ log trên máy (log không bao giờ bị xoá — user tự xoá thủ công), nên thời gian đọc tăng dần theo số log.
2. Xoá checkin **mới nhất** của 1 máy → mốc lùi → chu kỳ sau ghi lại lượt đó. Xoá lượt cũ hơn thì không.
3. NV chưa có `attendance_device_id` lúc chấm → lượt đó bị bỏ (`skipped_no_employee`) và không tự quay lại
   khi mốc đã vượt qua; bổ sung ID xong thì dùng Tab 6 Re-sync.
4. Thêm hàm mới vào file .py đã import → phải `bench restart` (worker giữ code cũ).
5. Dung lượng máy (đo 23/10): log Machine 7 = 62.693/100.000 (63%, ~3 tháng nữa đầy), Machine 5–6 ~45%;
   vân tay 2.198/3.000 (73%). Log càng nhiều thì đọc càng lâu = khoá máy lâu hơn.
6. MongoDB: bản ghi bị sửa tại chỗ (cùng `_id`, giờ mới) → quét lại thêm giờ mới nhưng **không xoá giờ cũ**.

# Health Check Up — Review Module (2026-07-11) + Fix toàn bộ (2026-07-12)

> Kết quả review toàn bộ module `health_check_up`. **Tất cả bug và improvement bên dưới đã được sửa ngày 2026-07-12** — xem mục 5 (Changelog). Tài liệu kỹ thuật chi tiết của trang quản lý: `page/health_check_up_management/readme.md`.

---

## 1. Cấu trúc module

```
health_check_up/
├── api/health_check_api.py                  ← 9 API whitelisted (read / scan / admin / excel) + permission guards
├── doctype/health_check_up/
│   ├── health_check_up.json                 ← DocType "Health Check-Up" (autoname: hash)
│   ├── health_check_up.py                   ← Controller: compute_status, fetch employee, pregnant (theo khoảng ngày), unique hospital_code + employee, validate_times
│   ├── health_check_up.js                   ← Form script (nút mở Web App, logic gender/pregnant/x_ray)
│   ├── health_check_up_list.js              ← List view: 3 menu admin (Clear Actual / Recalc Status / Change Date)
│   └── test_health_check_up.py              ← Tests: compute_status, validate_times, pregnant reset
└── page/health_check_up_management/
    ├── health_check_up_management.js        ← Web App chính: dashboard, scan phát/thu, danh sách, offline queue, camera
    ├── health_check_up_management.css/html/json
    ├── document_for_user.md                 ← Hướng dẫn người dùng
    └── readme.md                            ← Tài liệu kỹ thuật chi tiết

Ngoài module: public/js/lib/html5-qrcode.min.js ← camera lib bundle local
```

Module đã đăng ký trong `modules.txt` (`Health Check Up`). **Không** có entry nào trong `hooks.py` (không scheduler, không doc_events — mọi logic nằm trong controller + API).

## 2. Logic hiện tại (tóm tắt)

### DocType `Health Check-Up`
- 1 record = 1 NV trong 1 đợt khám (1 ngày). Unique: `hospital_code + date` **và** `employee + date` (validate trong controller).
- `validate()`: fetch thông tin Employee (chỉ khi field trống) → auto set `pregnant` (nữ + ngày khám nằm trong `[pregnant_from_date, pregnant_to_date]` trên Employee Maternity) → unique checks → `compute_status()` → `validate_times()`.
- `compute_status()`: `end_time_actual` → "Hoàn thành"; `start_time_actual` → "Đang khám"; còn lại "Chưa khám".
- Roles: HR User/Manager full quyền; `Health Check Operator` read+write; Employee read.

### Luồng scan (Web App `/desk/health-check-up-management`)
1. Operator chọn tab Phát/Thu, quét barcode (máy quét, camera html5-qrcode local bundle, hoặc gõ 4 số cuối mã NV / mã bệnh viện).
2. Client preview record từ `state.records` (`endsWith` — cùng rule suffix match với server).
3. Gọi `scan_distribute` / `scan_collect` (server check quyền write) → tìm record (`_find_record`, suffix match, throw nếu ambiguous), ghi actual time (= `scanned_at` nếu flush từ offline queue, ngược lại `nowtime()`), append note, save.
4. Server publish realtime `health_check_update` → mọi client cập nhật ngay; polling (mặc định 15s, hash theo `modified`) làm fallback.
5. Guard nghiệp vụ: phát lại / **thu lại** → client confirm trước khi ghi đè; thu khi chưa phát → dialog nhập giờ phát thủ công; đã thu xong thì không cho phát; `validate_times` chặn giờ thu < giờ phát.
6. Mất mạng (offline / server down / timeout): retry 2 lần → queue localStorage kèm `scanned_at` → tự flush khi online lại (có lock chống gửi trùng; item bị server từ chối hiện msgprint để xử lý tay).

### Admin (List View, "Only for IT")
- Clear Actual Data / Recalculate Status / Change Date — mật khẩu client (`"1111"`) chỉ là chặn thao tác nhầm; **server yêu cầu role System Manager** (`_require_admin`).

---

## 3. 🐛 Bug đã tìm thấy — TẤT CẢ ĐÃ SỬA 2026-07-12

| # | Vấn đề (tóm tắt) | Cách sửa |
|---|------|--------|
| B1 ✅ | Admin APIs không có permission check server-side | `_require_admin()` — role System Manager; sửa docstring "ddmm" |
| B2 ✅ | Scan APIs `ignore_permissions` không check role | `_require_write()` — `has_permission("Health Check-Up", "write")`; read APIs có `_require_read()` |
| B3 ✅ | `isNetworkError` không nhận diện server down/timeout → scan mất | Thêm check `status/readyState/httpStatus === 0`, `statusText === "timeout"` |
| B4 ✅ | Rời trang rồi quay lại mất listener online/offline → queue không tự flush | Chuyển gắn listener sang `on_page_show` (remove-first), flush queue tồn khi show |
| B5 ✅ | Flush queue ghi giờ flush thay vì giờ scan thật | Queue lưu `scanned_at` (local datetime), server nhận param `scanned_at` → `_resolve_scan_time()` |
| B6 ✅ | Flush không có lock (gửi trùng); server error drop im lặng | Lock `hcFlushInProgress`; item server-reject → `frappe.msgprint` liệt kê từng mã |
| B7 ✅ | Match mã NV `LIKE %code%` (contains) + LIMIT 1 không ORDER BY; lệch với client `endsWith` | Suffix match `LIKE %code`, `ORDER BY employee`, `LIMIT 2` → throw nếu khớp ≥2 hồ sơ |
| B8 ✅ | Pregnant chỉ check `pregnant_from_date` có giá trị → mang thai vĩnh viễn | So `date` khám với `[pregnant_from_date, pregnant_to_date]` (to_date trống = đang mang thai); sửa cả client `check_pregnant` |
| B9 ✅ | `validate_times()` bị comment out | Bật lại, so sánh bằng `get_time()` (tránh bug so string "9:00" > "10:00") |
| B10 ✅ | Thu lại không có confirm (phát lại thì có) | Thêm `frappe.confirm` khi `end_time_actual` đã tồn tại |
| B11 ✅ | Không unique `employee + date` | Thêm `validate_employee_unique()` trong controller |
| B12 ✅ | Form JS `gender` chỉ so `'Female'` | So cả `'Female'` và `'Nữ'` |
| B13 ✅ | XSS: note/tên chèn thẳng vào HTML | Helper `esc()` (frappe.utils.escape_html) áp dụng cho scan result, history, bảng, modal, filter options, chart labels |
| B14 ✅ | Polling 3s tải toàn bộ records, arg thừa, hash chỉ theo actual times | Mặc định 15s; bỏ `hospital_code: null`; hash theo `name + modified` (bắt mọi thay đổi) |
| B15 ✅ | Excel: trả `[]` khi trống, export HTML thô, không check quyền | `_require_read()`; throw khi không có data; `strip_html_tags` cột Result |
| B16 ✅ | Camera lib load từ CDN unpkg | Bundle `public/js/lib/html5-qrcode.min.js`, CDN chỉ là fallback |
| B17 ✅ | Xoay label chart bằng setTimeout 500ms fragile, code lặp 3 lần | Helper `rotateChartLabels()` retry tới 10×200ms |
| B18 ✅ | `frappe.db.commit()` thủ công trong request | Bỏ hết (Frappe tự commit; `after_commit=True` của realtime vẫn hoạt động) |
| B19 ✅ | `change_date` raw SQL không cập nhật modified | Set `modified = now` trong cùng câu UPDATE (để polling client bắt được) |
| B20 ✅ | readme nhắc file guide không tồn tại | Đã xóa reference, cập nhật cây file |

## 4. 💡 Improvement đã làm thêm

- Persist cấu hình (ngưỡng trễ, polling, chart layout, time compare mode) vào `localStorage` (`hc_mgmt_settings`).
- `recalculate_status_by_date` chịu lỗi từng record: record fail validate được skip và trả về trong `errors` thay vì chết cả batch.
- Viết test cho `compute_status`, `validate_times` (string-compare edge case), pregnant reset — `test_health_check_up.py`.
- Ghi chú trong `health_check_up_list.js` nói rõ mật khẩu chỉ là UX gate.

## 5. Changelog 2026-07-12 — đã verify

- **Files sửa**: `api/health_check_api.py`, `doctype/.../health_check_up.py`, `health_check_up.js`, `health_check_up_list.js`, `test_health_check_up.py`, `page/.../health_check_up_management.js`, 2 readme. **File mới**: `public/js/lib/html5-qrcode.min.js`.
- **Verify đã chạy**: py_compile + node --check toàn bộ file; bench console trên site `erp.tiqn.local` (rollback): guards chặn Guest ✓, `_resolve_scan_time` ✓, `compute_status`/`validate_times` ✓, suffix lookup `0045 → TIQN-0045` ✓; restart `frappe-bench-frappe-web` + ping 200 ✓; API gọi không đăng nhập bị chặn ✓.
- **Chưa test tay** (cần làm khi có đợt khám thật / staging): flow scan trên UI (phát/thu/thu lại confirm), offline queue end-to-end (tắt mạng → scan → bật mạng), camera scanner với lib local.

### Lưu ý vận hành
- `validate_times` giờ chặn giờ thu < giờ phát: nếu dữ liệu cũ có record sai giờ, "Recalculate Status" sẽ skip record đó và liệt kê trong kết quả — sửa tay record rồi chạy lại.
- User bấm menu admin ("Only for IT") giờ cần role **System Manager**, nếu không server trả lỗi quyền dù nhập đúng mật khẩu.

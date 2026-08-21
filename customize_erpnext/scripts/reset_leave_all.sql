-- =====================================================================
-- RESET TOÀN BỘ DỮ LIỆU NGHỈ PHÉP — xoá sạch để import lại từ đầu
-- =====================================================================
-- Khác `reset_leave_allocation.sql`: file kia GIỮ đơn nghỉ và chiều TRỪ
-- của ledger, chỉ reset phần cấp phép. File này xoá HẾT.
--
-- Chạy:  bench --site erp.tiqn.local mariadb < reset_leave_all.sql
--
-- ⚠ SAU KHI IMPORT LẠI: chạy `repair_leave_application_series.sql`.
--   Script này xoá bằng SQL thuần nên KHÔNG lùi `tabSeries`, nhưng nếu bộ đếm `LA-YYYY-MM-` từng
--   bị mất vì đường khác thì đơn mới sẽ đụng tên đã tồn tại (DuplicateEntryError). Chạy cho chắc,
--   script đó idempotent.
--
-- ⚠⚠ NĂM BẪY — đọc trước khi sửa ⚠⚠
--
-- 1. `tabLeave Ledger Entry` có HAI CHIỀU:
--       transaction_type = 'Leave Allocation'   -> CỘNG  (+8.679 ngày)
--       transaction_type = 'Leave Application'  -> TRỪ   (−8.085 ngày)
--    File này xoá CẢ HAI. Nếu chỉ muốn import lại đơn nghỉ mà GIỮ phần
--    cấp phép thì dùng `reset_leave_allocation.sql`, đừng dùng file này.
--
-- 2. Xoá ledger chiều CỘNG thì PHẢI xoá luôn `Leave Allocation`.
--    Leave Control Panel lọc người "đã có allocation" theo bảng
--    `tabLeave Allocation`, KHÔNG theo ledger — giữ allocation lại thì
--    panel vẫn bỏ qua 1.496 người đó và không cấp lại được.
--
-- 3. Xoá `Leave Allocation` thì PHẢI xoá luôn `Leave Policy Assignment`.
--    Nút `Allocate Leave` TẠO LPA MỚI (`create_leave_policy_assignments`),
--    không cấp lại từ LPA cũ. Giữ LPA lại thì
--    `validate_policy_assignment_overlap()` chặn toàn bộ — sự cố thật
--    17/08/2026: 1.496 dòng Error Log, 0 allocation tạo được.
--
-- 4. `tabEarned Leave Schedule` là child table của Leave Allocation;
--    xoá bằng SQL thì phải xoá tay (đã kiểm: 100% parenttype = 'Leave Allocation').
--
-- 5. ĐỪNG dùng `frappe.delete_doc()`: nó enqueue một background job mỗi
--    record -> "Too many queued background jobs (550)" ở mức ~1.000.
--
-- Attendance: KHÔNG xoá bản ghi, chỉ gỡ dấu vết nghỉ phép và TRẢ LẠI giờ
-- thực tế (bỏ phần bị chặn theo đơn nghỉ). Cột `status` để nguyên —
-- chạy Bulk Update Attendance sau khi import xong là engine tính lại đúng.
--
-- Số đo lần chạy thật 20/08/2026: 7.097 đơn · 8.244 ledger · 1.496 allocation
-- · 5.419 schedule · 1.496 LPA · 9.261 Attendance được gỡ link · 312 bản ghi
-- được trả lại giờ.
--
-- SAU KHI CHẠY (người dùng tự làm):
--   1. bench --site erp.tiqn.local clear-cache
--   2. Leave Control Panel -> cấp lại phép cho toàn bộ nhân viên
--   3. Import lại đơn nghỉ phép
--   4. Bulk Update Attendance cho cả kỳ
-- =====================================================================

SET SQL_SAFE_UPDATES = 0;

SELECT 'TRƯỚC' AS moc,
  (SELECT COUNT(*) FROM `tabLeave Application`)                                              AS don_nghi,
  (SELECT COUNT(*) FROM `tabLeave Ledger Entry`)                                             AS ledger,
  (SELECT COUNT(*) FROM `tabLeave Allocation`)                                               AS allocation,
  (SELECT COUNT(*) FROM `tabEarned Leave Schedule`)                                          AS schedule,
  (SELECT COUNT(*) FROM `tabLeave Policy Assignment`)                                        AS lpa,
  (SELECT COUNT(*) FROM `tabAttendance` WHERE IFNULL(leave_application,'') <> '')            AS att_co_link,
  (SELECT COUNT(*) FROM `tabAttendance`
     WHERE custom_actual_working_hours > working_hours + 0.001)                              AS att_bi_chan_gio;

-- ---------- 1. Đơn nghỉ phép ----------
DELETE FROM `tabLeave Application`;

-- ---------- 2. Ledger — CẢ HAI CHIỀU (xem bẫy #1) ----------
DELETE FROM `tabLeave Ledger Entry`;

-- ---------- 3. Child table của Leave Allocation (bẫy #4) ----------
DELETE FROM `tabEarned Leave Schedule` WHERE parenttype = 'Leave Allocation';

-- ---------- 4. Leave Allocation (bẫy #2) ----------
DELETE FROM `tabLeave Allocation`;

-- ---------- 5. Leave Policy Assignment (bẫy #3) ----------
DELETE FROM `tabLeave Policy Assignment`;

-- ---------- 6. Attendance: gỡ dấu vết nghỉ phép ----------
-- Trả working_hours về giờ thực tế theo check in/out. `custom_actual_working_hours`
-- chưa bao giờ bị chặn nên nó là nguồn đúng — xem overrides/shift_type/leave_hour_cap.py
UPDATE `tabAttendance`
SET working_hours = custom_actual_working_hours
WHERE custom_actual_working_hours > working_hours + 0.001;

UPDATE `tabAttendance`
SET leave_type = NULL,
    leave_application = NULL,
    custom_leave_type_2 = NULL,
    custom_leave_application_2 = NULL,
    custom_leave_application_abbreviation = NULL,
    half_day_status = NULL
WHERE IFNULL(leave_type,'') <> ''
   OR IFNULL(leave_application,'') <> ''
   OR IFNULL(custom_leave_application_abbreviation,'') <> ''
   OR IFNULL(half_day_status,'') <> '';

-- ---------- 7. Dọn audit trail mồ côi ----------
DELETE FROM `tabVersion` WHERE ref_doctype IN
  ('Leave Application', 'Leave Allocation', 'Leave Policy Assignment', 'Leave Ledger Entry');
DELETE FROM `tabComment` WHERE reference_doctype IN
  ('Leave Application', 'Leave Allocation', 'Leave Policy Assignment', 'Leave Ledger Entry');
DELETE FROM `tabToDo` WHERE reference_type IN ('Leave Application', 'Leave Allocation');

-- ---------- SAU + kiểm rò ----------
SELECT 'SAU' AS moc,
  (SELECT COUNT(*) FROM `tabLeave Application`)                                              AS don_nghi,
  (SELECT COUNT(*) FROM `tabLeave Ledger Entry`)                                             AS ledger,
  (SELECT COUNT(*) FROM `tabLeave Allocation`)                                               AS allocation,
  (SELECT COUNT(*) FROM `tabEarned Leave Schedule`)                                          AS schedule,
  (SELECT COUNT(*) FROM `tabLeave Policy Assignment`)                                        AS lpa,
  (SELECT COUNT(*) FROM `tabAttendance` WHERE IFNULL(leave_application,'') <> '')            AS att_co_link,
  (SELECT COUNT(*) FROM `tabAttendance`
     WHERE custom_actual_working_hours > working_hours + 0.001)                              AS att_bi_chan_gio;

SELECT 'kiểm rò: đơn nghỉ còn sót'      AS muc, COUNT(*) AS n FROM `tabLeave Application`
UNION ALL SELECT 'kiểm rò: ledger còn sót',        COUNT(*) FROM `tabLeave Ledger Entry`
UNION ALL SELECT 'kiểm rò: allocation còn sót',    COUNT(*) FROM `tabLeave Allocation`
UNION ALL SELECT 'kiểm rò: schedule mồ côi',       COUNT(*) FROM `tabEarned Leave Schedule`
UNION ALL SELECT 'kiểm rò: LPA còn sót',           COUNT(*) FROM `tabLeave Policy Assignment`
UNION ALL SELECT 'kiểm rò: Attendance còn link',   COUNT(*) FROM `tabAttendance` WHERE IFNULL(leave_application,'') <> ''
UNION ALL SELECT 'kiểm rò: Attendance còn abbr',   COUNT(*) FROM `tabAttendance` WHERE IFNULL(custom_leave_application_abbreviation,'') <> ''
UNION ALL SELECT 'kiểm rò: Attendance còn bị chặn giờ', COUNT(*) FROM `tabAttendance` WHERE custom_actual_working_hours > working_hours + 0.001
UNION ALL SELECT 'PHẢI CÒN: tổng Attendance',      COUNT(*) FROM `tabAttendance`
UNION ALL SELECT 'PHẢI CÒN: Employee Checkin',     COUNT(*) FROM `tabEmployee Checkin`
UNION ALL SELECT 'PHẢI CÒN: Overtime Registration', COUNT(*) FROM `tabOvertime Registration`;

SET SQL_SAFE_UPDATES = 1;

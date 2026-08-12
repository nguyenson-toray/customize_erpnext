-- =============================================================================
-- RESET dữ liệu chấm công / làm thêm giờ / lương  —  TIQN
-- =============================================================================
-- Dùng khi cần dựng lại chấm công từ đầu: xoá dữ liệu DẪN XUẤT, giữ dữ liệu GỐC.
--
--   XOÁ  : Attendance · Overtime Registration · Salary Slip · Shift Assignment
--          · Employee Checkin nhập tay (không từ máy chấm công)
--   GIỮ  : Employee Checkin từ máy · Leave Application · Leave Allocation
--          · Leave Ledger Entry · Salary Structure · Employee · Holiday List
--
-- 🔴 KHÔNG HOÀN TÁC ĐƯỢC. Backup trước:
--      bench --site erp.tiqn.local backup --with-files
--
-- Chạy cả file:
--      bench --site erp.tiqn.local mariadb < \
--        apps/customize_erpnext/customize_erpnext/scripts/reset_attendance_payroll.sql
--   hoặc chạy từng mục — các mục ĐỘC LẬP với nhau, trừ mục 3 (xem ghi chú).
--
-- Vì sao SQL chứ không phải `frappe.delete_doc()`:
--   `delete_doc()` enqueue MỘT background job mỗi bản ghi (`delete_dynamic_links`)
--   → tràn queue ở ~1.000 bản: "Too many queued background jobs (550)".
--
-- Sau khi chạy: chạy lại Bulk Update Attendance cho toàn khoảng ngày, rồi tính
-- lại Salary Slip. Xem `overrides/payroll_docs/PAYROLL_SETUP.md`.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Tắt safe-update mode
-- -----------------------------------------------------------------------------
-- MariaDB chặn DELETE/UPDATE không dùng cột index:
--   ERROR 1175: You are using safe update mode...
-- Các câu lệnh dưới cố ý xoá theo điều kiện không index (hoặc xoá cả bảng).
SET SQL_SAFE_UPDATES = 0;

-- -----------------------------------------------------------------------------
-- 0. Đếm trước khi xoá
-- -----------------------------------------------------------------------------
SELECT 'TRƯỚC KHI XOÁ' AS ' ';
SELECT 'Employee Checkin (tổng)'        AS muc, COUNT(*) AS so_luong FROM `tabEmployee Checkin`
UNION ALL SELECT '  ↳ nhập tay (device_id rỗng/0)', COUNT(*) FROM `tabEmployee Checkin`
          WHERE IFNULL(device_id,'') IN ('','0')
UNION ALL SELECT 'Attendance',                  COUNT(*) FROM `tabAttendance`
UNION ALL SELECT 'Overtime Registration',       COUNT(*) FROM `tabOvertime Registration`
UNION ALL SELECT 'Overtime Registration Detail',COUNT(*) FROM `tabOvertime Registration Detail`
UNION ALL SELECT 'Salary Slip',                 COUNT(*) FROM `tabSalary Slip`
UNION ALL SELECT 'Shift Assignment',            COUNT(*) FROM `tabShift Assignment`;

-- -----------------------------------------------------------------------------
-- 1. Employee Checkin nhập TAY  (device_id rỗng hoặc '0')
-- -----------------------------------------------------------------------------
-- `device_id` = "Location / Device ID". Bản ghi từ máy chấm công luôn có tên máy
-- ("Machine 1".."Machine 10"); rỗng hoặc '0' nghĩa là nhập thủ công.
DELETE FROM `tabEmployee Checkin` WHERE IFNULL(device_id,'') IN ('','0');

-- -----------------------------------------------------------------------------
-- 2. Overtime Registration  (+ bảng con)
-- -----------------------------------------------------------------------------
-- Xoá con TRƯỚC để không để lại bản ghi mồ côi.
DELETE FROM `tabOvertime Registration Detail` WHERE parenttype = 'Overtime Registration';
DELETE FROM `tabOvertime Registration`;

-- -----------------------------------------------------------------------------
-- 3. Attendance
-- -----------------------------------------------------------------------------
-- 🔴 HAI CÂU NÀY PHẢI ĐI CÙNG NHAU.
-- `Employee Checkin.attendance` trỏ tới Attendance. Xoá Attendance mà không gỡ
-- link thì engine ở chế độ incremental — lọc `attendance = "not set"`
-- (`overrides/shift_type/shift_type_optimized.py:1627`) — sẽ coi các checkin đó
-- là "đã xử lý" và KHÔNG BAO GIỜ tính lại chúng.
DELETE FROM `tabAttendance`;
UPDATE `tabEmployee Checkin` SET attendance = NULL WHERE IFNULL(attendance,'') != '';

-- -----------------------------------------------------------------------------
-- 4. Salary Slip  (+ bảng con)
-- -----------------------------------------------------------------------------
-- ⚠ `tabSalary Detail` DÙNG CHUNG cho Salary Slip và Salary Structure.
--   Bắt buộc lọc `parenttype`, nếu không sẽ xoá luôn công thức của Salary Structure.
DELETE FROM `tabSalary Detail`          WHERE parenttype = 'Salary Slip';
DELETE FROM `tabSalary Slip Timesheet`  WHERE parenttype = 'Salary Slip';
DELETE FROM `tabEmployee Benefit Detail` WHERE parenttype = 'Salary Slip';
DELETE FROM `tabSalary Slip Leave`      WHERE parenttype = 'Salary Slip';
DELETE FROM `tabSalary Slip`;
-- Payroll Entry KHÔNG bị xoá (giữ cấu hình kỳ chạy lương). Bỏ chú thích nếu muốn xoá:
-- DELETE FROM `tabPayroll Entry Employee` WHERE parenttype = 'Payroll Entry';
-- DELETE FROM `tabPayroll Entry`;

-- -----------------------------------------------------------------------------
-- 5. Shift Assignment
-- -----------------------------------------------------------------------------
-- Sau khi xoá, engine suy ca theo: Shift Assignment → `Employee.default_shift` → Day.
-- Kiểm độ phủ trước khi xoá:
--   SELECT COUNT(*) FROM tabEmployee WHERE IFNULL(default_shift,'')='' AND status='Active';
DELETE FROM `tabShift Assignment`;

-- -----------------------------------------------------------------------------
-- 6. Metadata bám theo các doctype vừa xoá
-- -----------------------------------------------------------------------------
DELETE FROM `tabVersion`  WHERE ref_doctype       IN
  ('Attendance','Overtime Registration','Salary Slip','Shift Assignment','Employee Checkin');
DELETE FROM `tabComment`  WHERE reference_doctype IN
  ('Attendance','Overtime Registration','Salary Slip','Shift Assignment','Employee Checkin');
DELETE FROM `tabDocShare` WHERE share_doctype     IN
  ('Attendance','Overtime Registration','Salary Slip','Shift Assignment','Employee Checkin');

-- -----------------------------------------------------------------------------
-- 7. Đếm lại + kiểm sót
-- -----------------------------------------------------------------------------
SELECT 'SAU KHI XOÁ' AS ' ';
SELECT 'Employee Checkin (còn lại)'     AS muc, COUNT(*) AS so_luong FROM `tabEmployee Checkin`
UNION ALL SELECT '  ↳ còn link Attendance treo (phải = 0)', COUNT(*) FROM `tabEmployee Checkin`
          WHERE IFNULL(attendance,'') != ''
UNION ALL SELECT '  ↳ nhập tay còn sót (phải = 0)', COUNT(*) FROM `tabEmployee Checkin`
          WHERE IFNULL(device_id,'') IN ('','0')
UNION ALL SELECT 'Attendance',                  COUNT(*) FROM `tabAttendance`
UNION ALL SELECT 'Overtime Registration',       COUNT(*) FROM `tabOvertime Registration`
UNION ALL SELECT 'Overtime Reg. Detail mồ côi', COUNT(*) FROM `tabOvertime Registration Detail`
UNION ALL SELECT 'Salary Slip',                 COUNT(*) FROM `tabSalary Slip`
UNION ALL SELECT 'Salary Detail mồ côi (phải = 0)', COUNT(*) FROM `tabSalary Detail`
          WHERE parenttype = 'Salary Slip'
UNION ALL SELECT 'Salary Detail của Structure (PHẢI CÒN)', COUNT(*) FROM `tabSalary Detail`
          WHERE parenttype = 'Salary Structure'
UNION ALL SELECT 'Shift Assignment',            COUNT(*) FROM `tabShift Assignment`
UNION ALL SELECT 'Leave Application (PHẢI CÒN)', COUNT(*) FROM `tabLeave Application`
UNION ALL SELECT 'Leave Ledger Entry (PHẢI CÒN)', COUNT(*) FROM `tabLeave Ledger Entry`;

-- Bật lại cho phiên hiện tại
SET SQL_SAFE_UPDATES = 1;

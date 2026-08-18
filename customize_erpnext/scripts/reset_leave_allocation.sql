-- =====================================================================
-- RESET LEAVE ALLOCATION — xoá sạch allocation + ledger CỘNG để cấp lại
-- =====================================================================
-- Dùng khi: đổi logic earned leave (earned_leave_config.py) và cần dựng
-- lại toàn bộ lịch cấp phép từ đầu.
--
-- Chạy:  bench --site erp.tiqn.local mariadb < reset_leave_allocation.sql
--
-- ⚠⚠ BỐN BẪY — đọc trước khi sửa file này ⚠⚠
--
-- 1. `tabLeave Ledger Entry` chứa CẢ HAI CHIỀU:
--       transaction_type = 'Leave Allocation'   → dòng CỘNG  (xoá)
--       transaction_type = 'Leave Application'  → dòng TRỪ   (GIỮ)
--    Xoá sạch bảng này sẽ để lại các Leave Application docstatus=1 mà
--    không có ledger → đơn nghỉ đã duyệt biến mất khỏi mọi báo cáo số dư.
--    Section 2 BẮT BUỘC có mệnh đề WHERE transaction_type.
--
-- 2. `tabEarned Leave Schedule` là child table, `delete_doc` mới dọn giúp;
--    xoá bằng SQL thì phải xoá tay (Section 1). Kiểm parenttype trước —
--    hiện tại 100% thuộc 'Leave Allocation'.
--
-- 3. 🔴 PHẢI XOÁ LUÔN `Leave Policy Assignment` (Section 4).
--    Nút `Allocate Leave` trên Leave Control Panel **TẠO LPA MỚI**
--    (`create_leave_policy_assignments`), nó KHÔNG cấp lại từ LPA có sẵn.
--    Nếu chỉ đặt `leaves_allocated = 0` mà giữ LPA thì
--    `validate_policy_assignment_overlap()` (leave_policy_assignment.py:63)
--    chặn TOÀN BỘ:
--        ValidationError: Leave Policy <X> already assigned for Employee <Y>
--                         for period <from> to <to>
--    Sự cố thật 17/08/2026: giữ 1.518 LPA → 1.496 dòng Error Log
--    "Leave Policy Assignment failed for employee ...", 0 allocation tạo được.
--    Xoá LPA KHÔNG mất gì: LPA không có child table, và panel tự dựng lại
--    y hệt (`effective_from/to` lấy từ Leave Period, số ngày thử việc nằm ở
--    `Employee.custom_probation_days` chứ không nằm trên LPA).
--
--    ⚠ Chỉ GIỮ LPA khi bạn định cấp lại BẰNG SCRIPT
--    (`doc.grant_leave_alloc_for_employee()` cho từng LPA) — HRMS không có
--    nút UI nào làm việc đó. Khi đó đổi Section 4 thành:
--        UPDATE `tabLeave Policy Assignment` SET leaves_allocated = 0;
--
-- 4. ĐỪNG dùng `frappe.delete_doc()` cho việc này: nó enqueue một
--    background job mỗi record → "Too many queued background jobs (550)"
--    ở mức ~1.000 record, và đã từng xoá lây record không thuộc phạm vi.
--
-- Số đo lần chạy thật 17/08/2026: 1.518 allocation · 5.491 schedule ·
-- 1.518 LLE cộng (+8.742,2) · 1.518 LPA · giữ 6.748 LLE trừ (−8.085,0)
-- và 7.097 Leave Application.
--
-- Sau khi chạy:
--   1. bench --site erp.tiqn.local clear-cache
--   2. Leave Control Panel → Dates Based On = Leave Period → chọn kỳ
--      → Allocate based on Leave Policy → Select Employees → Allocate Leave
-- =====================================================================

SET SQL_SAFE_UPDATES = 0;

-- ---------- TRƯỚC ----------
SELECT 'TRƯỚC' AS moc,
  (SELECT COUNT(*) FROM `tabLeave Allocation`)                                             AS allocation,
  (SELECT COUNT(*) FROM `tabEarned Leave Schedule`)                                        AS schedule,
  (SELECT COUNT(*) FROM `tabLeave Ledger Entry` WHERE transaction_type='Leave Allocation')  AS lle_cong,
  (SELECT COUNT(*) FROM `tabLeave Ledger Entry` WHERE transaction_type='Leave Application') AS lle_tru_giu,
  (SELECT COUNT(*) FROM `tabLeave Application`)                                            AS leave_application,
  (SELECT COUNT(*) FROM `tabLeave Policy Assignment`)                                       AS lpa;

-- ---------- 1. Child table của Leave Allocation ----------
DELETE FROM `tabEarned Leave Schedule` WHERE parenttype = 'Leave Allocation';

-- ---------- 2. Ledger — CHỈ chiều CỘNG (xem bẫy #1) ----------
DELETE FROM `tabLeave Ledger Entry` WHERE transaction_type = 'Leave Allocation';

-- ---------- 3. Leave Allocation ----------
DELETE FROM `tabLeave Allocation`;

-- ---------- 4. Leave Policy Assignment (xem bẫy #3 — PHẢI xoá) ----------
DELETE FROM `tabLeave Policy Assignment`;

-- ---------- 5. Dọn audit trail mồ côi ----------
DELETE FROM `tabVersion` WHERE ref_doctype IN ('Leave Allocation', 'Leave Policy Assignment');
DELETE FROM `tabComment` WHERE reference_doctype IN ('Leave Allocation', 'Leave Policy Assignment');
DELETE FROM `tabError Log` WHERE method LIKE 'Leave Policy Assignment failed for employee%';

-- ---------- SAU + kiểm rò ----------
SELECT 'SAU' AS moc,
  (SELECT COUNT(*) FROM `tabLeave Allocation`)                                             AS allocation,
  (SELECT COUNT(*) FROM `tabEarned Leave Schedule`)                                        AS schedule,
  (SELECT COUNT(*) FROM `tabLeave Ledger Entry` WHERE transaction_type='Leave Allocation')  AS lle_cong,
  (SELECT COUNT(*) FROM `tabLeave Ledger Entry` WHERE transaction_type='Leave Application') AS lle_tru_giu,
  (SELECT COUNT(*) FROM `tabLeave Application`)                                            AS leave_application,
  (SELECT COUNT(*) FROM `tabLeave Policy Assignment`)                                       AS lpa;

SELECT 'kiểm rò: allocation còn sót'   AS muc, COUNT(*) AS n FROM `tabLeave Allocation`
UNION ALL SELECT 'kiểm rò: schedule mồ côi',      COUNT(*) FROM `tabEarned Leave Schedule`
UNION ALL SELECT 'kiểm rò: LLE cộng còn sót',     COUNT(*) FROM `tabLeave Ledger Entry` WHERE transaction_type='Leave Allocation'
UNION ALL SELECT 'kiểm rò: LPA còn sót',          COUNT(*) FROM `tabLeave Policy Assignment`
UNION ALL SELECT 'PHẢI CÒN: LLE trừ của LA',      COUNT(*) FROM `tabLeave Ledger Entry` WHERE transaction_type='Leave Application'
UNION ALL SELECT 'PHẢI CÒN: LA submitted',        COUNT(*) FROM `tabLeave Application` WHERE docstatus=1
UNION ALL SELECT 'PHẢI CÒN: LA draft',            COUNT(*) FROM `tabLeave Application` WHERE docstatus=0
UNION ALL SELECT 'LA submitted KHÔNG có ledger (phải 0)', COUNT(*) FROM `tabLeave Application` la
  WHERE la.docstatus=1 AND NOT EXISTS (
    SELECT 1 FROM `tabLeave Ledger Entry` lle
    WHERE lle.transaction_type='Leave Application' AND lle.transaction_name=la.name);

SET SQL_SAFE_UPDATES = 1;

-- =====================================================================================
-- Dựng lại bộ đếm tên Leave Application (`tabSeries`) từ chính các bản ghi đang có.
--
-- KHI NÀO CẦN CHẠY
--   Khi HR không tạo được đơn nghỉ mới và log báo:
--       DuplicateEntryError: ('Leave Application', 'LA-2026-03-00001', ...)
--
-- VÌ SAO XẢY RA
--   `autoname()` (overrides/leave_application/leave_application.py) phát số qua
--   `make_autoname("LA-YYYY-MM-.#####")`. Số kế tiếp nằm ở `tabSeries.current` cho tiền tố
--   `LA-YYYY-MM-`. Nếu dòng đó MẤT, `getseries()` coi như chưa từng phát số và bắt đầu lại
--   từ 00001 — đụng ngay tên đã tồn tại. Đơn cũ vẫn nguyên, nhưng KHÔNG tạo được đơn mới.
--
--   Hai đường làm mất dòng đếm:
--     1. Xoá hết đơn của một tháng: `revert_series_if_last()` lùi bộ đếm, về 0 thì xoá dòng.
--        `scripts/reset_leave_all.sql` xoá bằng SQL nên KHÔNG gây ra chuyện này, nhưng xoá
--        qua UI/ORM thì có.
--     2. Script dọn dẹp `delete from tabSeries where name like 'LA-%'` — đã từng nằm trong
--        phần teardown của `test_leave_application_naming.py` (kèm `commit()`), mỗi lần chạy
--        test là xoá sạch bộ đếm production. Đã bỏ; test giờ canh bằng PHẦN 5.
--
-- AN TOÀN
--   Idempotent. Chỉ NÂNG bộ đếm, không bao giờ hạ (`GREATEST`), nên chạy nhầm cũng không phát
--   lại số đã dùng. Không đụng vào một bản ghi Leave Application nào.
--   Lấy tiền tố từ CHÍNH tên bản ghi (`LEFT(name,11)`), không suy từ `from_date` — có đơn được
--   tạo/sửa lệch tháng so với tên của nó.
-- =====================================================================================

INSERT INTO `tabSeries` (name, current)
SELECT LEFT(name, 11) AS pfx,
       MAX(CAST(RIGHT(name, 5) AS UNSIGNED)) AS cur
  FROM `tabLeave Application`
 WHERE name REGEXP '^LA-[0-9]{4}-[0-9]{2}-[0-9]{5}$'
 GROUP BY 1
ON DUPLICATE KEY UPDATE current = GREATEST(`tabSeries`.current, VALUES(current));

-- Kiểm chứng: phải trả về 0 dòng. Mỗi dòng = một tháng bộ đếm còn thấp hơn số đang dùng.
SELECT t.pfx, t.mx AS so_lon_nhat_dang_dung,
       IFNULL((SELECT s.current FROM `tabSeries` s WHERE s.name = t.pfx), 0) AS bo_dem
  FROM (SELECT LEFT(name, 11) pfx, MAX(CAST(RIGHT(name, 5) AS UNSIGNED)) mx
          FROM `tabLeave Application`
         WHERE name REGEXP '^LA-[0-9]{4}-[0-9]{2}-[0-9]{5}$'
         GROUP BY 1) t
 WHERE t.mx > IFNULL((SELECT s.current FROM `tabSeries` s WHERE s.name = t.pfx), 0);

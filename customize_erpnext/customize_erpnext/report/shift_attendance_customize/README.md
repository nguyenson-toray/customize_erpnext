# Shift Attendance Customize

## Mô tả

Report tùy chỉnh từ "Shift Attendance" của HRMS v16, hiển thị chi tiết thông tin chấm công theo ca làm việc với các tính năng mở rộng.

## Đặc điểm chính

### So sánh với report gốc

| Tính năng | Shift Attendance (HRMS) | Shift Attendance Customize |
|-----------|------------------------|----------------------------|
| Hiển thị records | Chỉ Present | **Tất cả status** |
| Query performance | INNER JOIN (Checkin + Shift Type) | LEFT JOIN (chỉ Employee) |
| Prepared Report | Không | **Không** (realtime) |
| Overtime tracking | Không | **Có** (Actual, Approved, Final) |
| Working Day | Không | **Có** (= Working Hours / 8) |
| Group filter | Không | **Có** (custom doctype Group) |
| Join/Resign Date | Không | **Có** (optional, via filter) |
| Summary mode | Không | **Có** (aggregate by employee) |
| Chart | Có | **Không** |

### Các cột hiển thị

#### Detail Mode (mặc định)

1. **Attendance Date** - Ngày chấm công
2. **Shift** - Ca làm việc
3. **Employee** - Mã nhân viên
4. **Group** - Nhóm nhân viên (custom_group)
5. **Date of Joining** - Ngày vào làm _(chỉ hiển thị khi filter "Detail Join / Resign Date" = True)_
6. **Relieving Date** - Ngày nghỉ việc _(chỉ hiển thị khi filter "Detail Join / Resign Date" = True)_
7. **Status** - Trạng thái (có màu sắc: Present=xanh, Absent=đỏ, Maternity Leave=tím)
8. **In Time** - Giờ vào
9. **Out Time** - Giờ ra
10. **Total Working Hours** - Tổng giờ làm việc
11. **Working Day** - Số ngày công (= Total Working Hours / 8)
12. **Actual Overtime Duration** - Thời gian tăng ca thực tế
13. **Approved Overtime Duration** - Thời gian tăng ca được duyệt
14. **Final Overtime Duration** - Thời gian tăng ca cuối cùng
15. **Maternity Benefit** - Chế độ thai sản
16. **Late Entry** - Checkbox đi muộn
17. **Early Exit** - Checkbox về sớm
18. **Leave Application** - Đơn xin nghỉ
19. **Department** - Phòng ban
20. **Attendance ID** - Mã chấm công

#### Summary Mode (khi bật filter "Summary")

1. **Shift** - Ca làm việc
2. **Employee** - Mã nhân viên
3. **Group** - Nhóm nhân viên
4. **Date of Joining** - Ngày vào làm (tự động hiển thị)
5. **Relieving Date** - Ngày nghỉ việc (tự động hiển thị)
6. **Total Working Hours** - Tổng giờ làm việc (SUM)
7. **Total Working Day** - Tổng ngày công (SUM)
8. **Total Actual OT** - Tổng thời gian tăng ca thực tế (SUM)
9. **Total Approved OT** - Tổng thời gian tăng ca được duyệt (SUM)
10. **Total Final OT** - Tổng thời gian tăng ca cuối cùng (SUM)
11. **Department** - Phòng ban

### Bộ lọc

- **From Date** - Từ ngày (mặc định: ngày 26 tháng trước)
- **To Date** - Đến ngày (mặc định: ngày hiện tại)
- **Employee** - Lọc theo nhân viên
- **Shift Type** - Lọc theo ca làm việc
- **Department** - Lọc theo phòng ban
- **Status** - Lọc theo trạng thái (Present, Absent, Maternity Leave, On Leave, Half Day, Work From Home)
- **Group** - Lọc theo nhóm nhân viên (custom doctype Group)
- **Late Entry** - Checkbox chỉ hiển thị đi muộn (không áp dụng trong Summary mode)
- **Early Exit** - Checkbox chỉ hiển thị về sớm (không áp dụng trong Summary mode)
- **Detail Join / Resign Date** - Checkbox hiển thị thêm cột ngày vào làm & ngày nghỉ việc (mặc định: tắt)
- **Summary** - Checkbox tổng hợp dữ liệu theo nhân viên (mặc định: tắt)
  - Khi bật: tự động bật "Detail Join / Resign Date"
  - Hiển thị tổng số giờ làm việc, ngày công, overtime theo từng nhân viên
  - Ẩn các cột chi tiết: Date, Status, In/Out Time, Maternity Benefit, Late Entry, Early Exit, Leave Application, Attendance ID

### Report Summary

Hiển thị 5 chỉ số tổng hợp:

1. **Present Records** (xanh) - Số lần đi làm
2. **Maternity Leave Records** (xanh dương) - Số lần nghỉ thai sản
3. **Absent Records** (đỏ) - Số lần vắng mặt
4. **Late Entries** (đỏ) - Số lần đi muộn
5. **Early Exits** (đỏ) - Số lần về sớm

### Sắp xếp mặc định

Dữ liệu tự động sắp xếp tăng dần theo thứ tự:
1. Attendance Date
2. Shift
3. Group
4. Employee

## Cấu hình yêu cầu

### Custom Fields cần thiết

Report sử dụng các custom fields sau trong DocType **Attendance**:

- `actual_overtime_duration` (Float) - Thời gian tăng ca thực tế
- `custom_approved_overtime_duration` (Float) - Thời gian tăng ca được duyệt
- `custom_final_overtime_duration` (Float) - Thời gian tăng ca cuối cùng
- `custom_maternity_benefit` (Data) - Chế độ thai sản

Trong DocType **Employee**:

- `custom_group` (Link: Group) - Nhóm nhân viên (custom doctype)

## Performance

Report được tối ưu cho performance:

- ✅ Query đơn giản (chỉ 1 LEFT JOIN với Employee)
- ✅ Không có INNER JOIN với Employee Checkin hay Shift Type
- ✅ Không có GROUP BY
- ✅ Không tính toán phức tạp (late entry/early exit duration)
- ✅ Realtime query (không prepared report)
- ✅ Không có chart (giảm load time)

## Cài đặt

1. Copy toàn bộ thư mục vào module `customize_erpnext`
2. Chạy migrate:
   ```bash
   bench --site [site-name] migrate
   ```
3. Clear cache:
   ```bash
   bench --site [site-name] clear-cache
   ```

## Sử dụng

Truy cập: **Báo cáo > Shift Attendance Customize**

---

**Version:** 1.0
**Author:** TIQN
**Date:** 2025-12-26
**Based on:** HRMS v16 Shift Attendance Report

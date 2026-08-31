# Shift Attendance Customize

> **Mục đích:** Report tùy chỉnh từ "Shift Attendance" của HRMS v16, hiển thị chi tiết thông tin chấm công theo ca làm việc với các tính năng mở rộng.
> **Phạm vi:** Report tự phát triển
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-07-13

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
15. **-1h** (`custom_hour_reduction`) - Giảm 1 giờ làm việc (mang thai hoặc con dưới 12 tháng)
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
  - Ẩn các cột chi tiết: Date, Status, In/Out Time, -1h, Late Entry, Early Exit, Leave Application, Attendance ID

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
- `custom_hour_reduction` (Check) - Giảm 1 giờ làm việc (mang thai hoặc con dưới 12 tháng)

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

## Export Excel - C&B Template

### 3 Sheet trong file Excel

1. **Timesheet** - Bảng chấm công
2. **Overtime** - Bảng tổng hợp làm thêm giờ
3. **Quy định nghỉ phép** - Bảng quy định các loại nghỉ phép

### Quy tắc tính ngày công (Timesheet)

| Loại | Abbreviation | Ngày công |
|------|--------------|-----------|
| Phép năm, Hưởng lương | P, P/2, MC, HS, HL, HL/2 | 1 |
| Không lương, Nghỉ bù, BHXH | KL, NB, TS, DS, O, CO, OCO/2, OK/2, COK/2 | 0 |
| Ốm/Con ốm - Đi làm/Phép năm | O/2, CO/2, OP/2, COP/2 | 0.5 |
| Ốm/Con ốm - Đi trễ/về sớm ≤1h | OL/2, COL/2 | 0.4 |
| Khác | Theo working_hours | 1−(8−giờ)/8 |

### Hiển thị trên bảng công

- **KL & working_hours = 0**: Hiển thị "KL"
- **KL & working_hours > 0**: Hiển thị số giờ
- **Ngày CN & Lễ**: Ô trống + tô màu xám, không tính ngày công

### Tính OT (Overtime sheet)

| Cột | Nội dung |
|-----|----------|
| Ngày | `custom_final_overtime_duration` (giữ nguyên) |
| Total OT | Tổng `custom_final_overtime_duration` |
| Total OT x Multiplier | Tổng (OT × hệ số theo loại ngày) |

**Hệ số OT theo loại ngày:**
- Ngày thường: `standard_multiplier`
- Chủ nhật: `weekend_multiplier`
- Ngày lễ: `public_holiday_multiplier`

---

## Excel Export — 6 sheets y hệt app chuẩn + 1 sheet riêng TIQN (từ 2026-07-13)

Nút **Export Excel** trên report (`export_attendance_excel`) xuất workbook **đúng
format app Flutter chuẩn** (replica từ `flutter_app_chuẩn/timesheetFunctions.dart`,
code: `standard_export.py`). Tên file: `Timesheet_{yymmdd}_{yymmdd}_{timestamp}.xlsx`.

1. **Important Note** — bất thường: `[Resigned + Att]` (đã nghỉ việc còn chấm công), `[Ra 16-17h]` (nữ ca Day checkout 16-17h không có chế độ thai sản/con nhỏ tại ngày đó). Nguồn: `custom_note` của Attendance.
2. **Detail** — 1 dòng/(NV × ngày có ≥1 người chấm công), gồm cả NV vắng (giờ trống, số 0); 21 cột; notes tiếng Việt như app (`Vào trễ`, `Ra sớm`, `Chế độ mang thai`…) + bổ sung `Phép: {abbr}` từ Leave Application (app không có dữ liệu phép). Hai luật riêng của TIQN:
   - **Chủ Nhật và ngày lễ chỉ liệt kê người thực sự đi làm** (có First/Last hoặc có giờ/OT > 0). Ngày thường vẫn giữ nguyên cả người vắng. Đo CN 30/08/2026: 3 dòng thay vì 1.011.
   - Khi `With Leave Application = 0` thì **bỏ hẳn cột `Actual (hour)`** (còn 20 cột), vì ở chế độ đó `Working (hour)` đã chính là `custom_actual_working_hours` nên hai cột luôn bằng nhau.
3. **Summary** — 1 dòng/NV: 8 cột cố định (No, ID, Name, Joining, Resign, Group, Section, Position) + tổng giờ/công/3 loại OT (tổng công = Σ working_day từng ngày đã làm tròn).
4. **Timesheet** — ma trận NV × ngày (dd/mm, gồm CN — header CN tô xám) + Total; giá trị = công/ngày, chỉ ghi khi >0.
5. **Leave Application** *(riêng TIQN, app không có)* — 1 dòng/đơn nghỉ **giao nhau** với kỳ; 8 cột cố định + `Leave Type · Abbr · From · To · Total Days · Half Day Date · Status · Docstatus · Leave Application · Reason`. Cột From/To in **nguyên ngày của đơn**, không kẹp vào biên kỳ. Lấy cả đơn Draft khi `Attendance Calculation Setting.include_draft_leave_application` bật (hiện đang bật), vì engine cũng tính đơn Draft vào bảng công.
6. **Overtime** — ma trận như trên, giá trị = **OT Final**; chỉ NV có tổng OT > 0.
7. **Shift** — ma trận NV ca xoay (Shift 1 chữ cam, Shift 2 chữ xanh) × ngày (gồm CN); chỉ xuất hiện khi range có attendance Shift 1/2.

### Option `With Leave Application` (dialog Export Excel, mặc định BẬT)

| | =1 | =0 |
|---|---|---|
| Detail · Summary · Timesheet | `working_hours` (đã bị chặn theo đơn nghỉ) + in mã nghỉ `P`/`KL`/`O/2`… | `custom_actual_working_hours` **thay chỗ** `working_hours` cho mọi tính toán, **bỏ** mã nghỉ ⇒ ô Timesheet chỉ còn số |
| Cột `Actual (hour)` của Detail | có (21 cột) | **bỏ** (20 cột) — trùng hệt cột `Working (hour)` |
| Sheet `Leave Application` | **luôn xuất**, bỏ qua lựa chọn trong "Sheets to export" | theo checkbox trong "Sheets to export" |
| `Important Note` · `Overtime` · `Shift` | không đổi | không đổi |

⚠ Important Note miễn nhiễm vì `anomalies` được dựng **bên trong** `build_export_rows()`, trước khi phần swap chạy. Bỏ mã nghỉ khi =0 là bắt buộc: `timesheet_working_days("P", …)` trả 1,0 công **bất kể số giờ**, giữ mã lại thì giờ thực tế vô tác dụng đúng ở những ngày cần nó nhất.

### Ai bị loại khỏi file

Nhân viên **không có một bản ghi Attendance nào** trong kỳ bị loại hẳn (`load_export_universe`): bản chất là ở nhà cả kỳ — nghỉ thai sản, nghỉ dài ngày — không tính lương, mà để lại thì chiếm trọn một khối dòng số 0. Đo kỳ 08/2026: bỏ 29 người, cả 29 đều đang trong kỳ nghỉ thai sản. Chỉ cần **tồn tại** bản ghi là hiện, kể cả `On Leave`/`Absent` không có giờ check-in.

🔴 Luật này **không áp** khi bật option *Only employees who resigned in this period*: người nghỉ đúng ngày đầu kỳ thì cả kỳ không có bản ghi nào (ngày làm cuối = `relieving_date − 1`), áp vào là làm rỗng đúng danh sách HR cần để chốt lương. Đo tháng 6/2026: mất TIQN-1653 và TIQN-2144.

Sheet kiểu C&B cũ (Timesheet footer chữ ký, Overtime C&B, Quy định nghỉ phép) đã bỏ hẳn theo yêu cầu.

Lưu ý (từ 2026-07-06): export ≤45.000 records (NV × ngày ≈ 45 ngày full công ty) chạy **sync ngay** (~17s cho 1 tháng); lớn hơn → background job với progress bar, chống double-click (dedup theo user+range), khi xong có **thông báo chuông kèm link tải** (nhận được cả khi rời trang); file sync tự xóa sau 2 phút, file background giữ 30 phút.

---

**Version:** 1.2
**Author:** TIQN
**Date:** 2026-07-05
**Based on:** HRMS v16 Shift Attendance Report

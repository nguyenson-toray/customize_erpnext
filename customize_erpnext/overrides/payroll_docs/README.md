# payroll_docs — thư mục chính thức cho phần Lương

Nơi tập trung tài liệu tính lương của TIQN. Mọi tài liệu lương mới đặt ở đây.

## Tài liệu

| File | Nội dung |
|---|---|
| [`QUY_CHE_LUONG_2025.md`](QUY_CHE_LUONG_2025.md) | **Nguồn pháp lý nội bộ** — trích quy chế gốc `TIQN-2025-HR/GA-QĐ-0001` rev.3. Mức phụ cấp, điều kiện hưởng, quy tắc prorate, phúc lợi |
| [`PAYROLL_SETUP.md`](PAYROLL_SETUP.md) | **Tài liệu thi công** — công thức, kiến trúc, gotcha, danh sách kiểm, việc cần làm, dữ liệu gốc 9 phiếu lương |
| [`PLAN_PAYROLL_SETTINGS.md`](PLAN_PAYROLL_SETTINGS.md) | Thiết kế `TIQN Payroll Settings` + kiểm kê hằng số lương. ✅ đã triển khai |
| [`PLAN_EMPLOYEE_DEPENDENT.md`](PLAN_EMPLOYEE_DEPENDENT.md) | Thiết kế `Employee Dependent` + child table. ✅ đã triển khai — chờ dữ liệu từ HR |
| [`PLAN_ATTENDANCE_VS_QUYCHE.md`](PLAN_ATTENDANCE_VS_QUYCHE.md) | Đối chiếu module chấm công với quy chế + **bàn giao hai chiều** giữa phiên lương và phiên chấm công |

**Thứ tự đọc:** quy chế trước (biết *phải* làm gì) → `PAYROLL_SETUP.md` sau (biết *khai thế nào*).
Khi hai tài liệu mâu thuẫn, **quy chế thắng**.

## Code

| Đường dẫn | Vai trò |
|---|---|
| `overrides/payroll/vn_deductions.py` | BHXH/BHYT/BHTN · đoàn phí · thuế TNCN · mốc 14 ngày — qua hook `apply_regional_deductions` |
| `overrides/payroll/import_ssa.py` | Import lương HĐLĐ từ Excel/CSV → SSA; đồng bộ loại hợp đồng |
| `overrides/salary_slip/salary_slip.py` | Ngày công chuẩn · nạp giờ OT từ Attendance · tách OT vượt trần · đặt tên phiếu |
| `overrides/salary_structure_assignment/` | Tự tính `custom_si_base` + cảnh báo lệch |
| `customize_erpnext/doctype/tiqn_payroll_settings/` | Hằng số lương do HR quản lý (mức giảm trừ, biểu thuế, tỷ lệ BH, trần OT) |
| `customize_erpnext/doctype/employee_dependent/` | Người phụ thuộc — 1 hồ sơ / nhân viên, danh sách NPT ở child table `Employee Dependent Item` |
| `customize_erpnext/report/ot_compliance/` | Báo cáo vượt trần làm thêm giờ |
| `patches/seed_tiqn_payroll_settings.py` | Seed giá trị hiện hành, idempotent |

## Dữ liệu đối chiếu / hồi quy

| File | Nội dung |
|---|---|
| `Salary.xlsx` | Bảng lương HR kỳ **07/2026** — báo cáo đã định dạng, không import thẳng được |
| `salary_contract_202607.csv` | Bản **phẳng** trích ra: 16 NV × 15 cột, tiêu đề = tên field SSA, có BOM UTF-8 |

> ✅ CSV trùng khớp tuyệt đối Excel (0 ô lệch); tổng lương HĐLĐ 83.950.000 khớp dòng Total.
> ✅ Cột *"Salary for SI & HI"* khớp **16/16** với công thức căn cứ đóng BH (8 khoản).
>
> 🔴 File này **không dùng làm thước đo** đúng/sai của hệ thống — xem `PAYROLL_SETUP.md` mục 6.2.

Cách chạy import: `PAYROLL_SETUP.md` mục 5.

## ⚠ Quy ước bắt buộc khi in chứng từ

**Số tiền đọc bằng chữ phải là tiếng Việt.** `frappe.utils.money_in_words` và filter `in_words`
trả về **tiếng Anh** — không dùng được cho phiếu lương, hợp đồng, bảng kê.

```jinja
{{ so_tien_bang_chu(doc.net_pay) }}   {# Mười bảy triệu bốn trăm ba mươi nghìn không trăm bốn mươi lăm đồng #}
{{ format_vnd(doc.net_pay) }}         {# 17.430.045 ₫ #}
```

Code: `customize_erpnext/api/vn_number_words.py` — thuần stdlib, không import `frappe`, nên
`tests/test_vn_number_words.py` chạy được không cần bench/site. Đã đăng ký Jinja trong `hooks.py`.

> 🔴 **Đừng dùng `frappe.format` cho tiền trên chứng từ.**
> `System Settings.number_format = "# ###,##"` (dấu cách) → ra `17 430 045`; chứng từ VN cần dấu chấm.

## Trạng thái

Logic tính lương **đã xong và kiểm chứng khớp phiếu lương thật**.
Còn chặn ở **dữ liệu**: chấm công, nghỉ phép, người phụ thuộc, lương HĐLĐ toàn công ty.

Chi tiết: `PAYROLL_SETUP.md` mục 0 (trạng thái) và mục 7 (việc cần làm).

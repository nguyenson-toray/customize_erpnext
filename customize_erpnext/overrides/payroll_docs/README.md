# payroll_docs — thư mục chính thức cho phần Lương

Nơi tập trung **tài liệu + code** liên quan tính lương của TIQN.
Mọi tài liệu lương mới đặt ở đây, không rải ra thư mục gốc của app.

## Tài liệu

| File | Nội dung |
|---|---|
| [`QUY_CHE_LUONG_2025.md`](QUY_CHE_LUONG_2025.md) | **Nguồn pháp lý nội bộ.** Trích từ quy chế gốc `TIQN-2025-HR/GA-QĐ-0001` rev.3 (02/01/2025). Mức phụ cấp, điều kiện hưởng, quy tắc prorate, phúc lợi. Kèm mục đối chiếu với phiếu lương thật và các khoản còn lệch |
| [`PAYROLL_SETUP.md`](PAYROLL_SETUP.md) | **Tài liệu thi công.** Công thức đã dò ngược + kiểm chứng từ 9 phiếu lương 07/2026, cách khai trên ERPNext, các gotcha đã gặp, dữ liệu gốc 9 phiếu (mục 7) |
| [`PLAN_PAYROLL_SETTINGS.md`](PLAN_PAYROLL_SETTINGS.md) | **Plan** gom hằng số lương (mức giảm trừ, biểu thuế, tỷ lệ BH, trần OT…) vào 1 Single doctype. Chưa code |
| [`PLAN_EMPLOYEE_DEPENDENT.md`](PLAN_EMPLOYEE_DEPENDENT.md) | **Plan** doctype quản lý người phụ thuộc — điều kiện để tự động hoá thuế TNCN. Chưa code |

**Thứ tự đọc:** quy chế trước (biết *phải* làm gì) → setup sau (biết *khai thế nào*).
Khi hai tài liệu mâu thuẫn, **quy chế thắng** — `PAYROLL_SETUP.md` có phần suy đoán từ trước khi
có quy chế, chỗ nào đã bị thay thế đều được đánh dấu.

## ⚠ Quy ước BẮT BUỘC khi in ấn (phiếu lương, hợp đồng, bảng kê)

### Số tiền đọc bằng chữ PHẢI là tiếng Việt
`frappe.utils.money_in_words` và filter `in_words` của Frappe trả về **tiếng Anh**
(*"Seventeen Million Four Hundred Thirty Thousand..."*) — **không được dùng** cho chứng từ VNĐ.

Dùng helper của app, đã đăng ký sẵn làm Jinja method trong `hooks.py`:

```jinja
{{ so_tien_bang_chu(doc.net_pay) }}   {# Mười bảy triệu bốn trăm ba mươi nghìn không trăm bốn mươi lăm đồng #}
{{ money_in_words_vi(doc.net_pay) }}  {# alias, cùng một hàm #}
{{ format_vnd(doc.net_pay) }}         {# 17.430.045 ₫ #}
```

| | |
|---|---|
| **Code** | `customize_erpnext/api/vn_number_words.py` |
| **Test** | `tests/test_vn_number_words.py` — chạy được **không cần bench/site** (module thuần stdlib, không import `frappe`) |
| **Nguồn** | phái sinh từ `so_tien_bang_chu` của `github.com/mrhuychien/erpnextvn`, đã sửa: số âm · số > 10¹² · input không phải số |

Đã xử lý đúng các trường hợp tiếng Việt hay sai: `mốt` (21) · `tư` (24) · `lăm` (25, 15) ·
`lẻ` (105) · `không trăm` ở nhóm không đứng đầu · `nghìn tỷ` / `triệu tỷ`.
Cờ `USE_TU_FOR_FOUR` đổi giữa *"hai mươi tư"* và *"hai mươi bốn"* nếu kế toán muốn.

> 🔴 **Đừng dùng `frappe.format` cho tiền trên chứng từ.**
> `System Settings.number_format = "# ###,##"` (dấu cách) → ra `17 430 045`.
> Chứng từ VN cần dấu chấm ⇒ dùng `format_vnd()`.

## Code liên quan (đang nằm ngoài thư mục này)

| Đường dẫn | Vai trò |
|---|---|
| `overrides/salary_slip/salary_slip.py` | Ngày công chuẩn chỉ trừ Chủ Nhật, không trừ ngày lễ |
| `overrides/salary_structure_assignment/` | Tự tính `custom_si_base` (căn cứ đóng BH) + cảnh báo lệch |
| `public/js/custom_scripts/salary_structure_assignment.js` | Tính `custom_si_base` ngay trên form |

> Code lương **viết mới** thì đặt trong thư mục này.

## Trạng thái

Đang ở giai đoạn **chuẩn hoá logic, chưa code**. Danh sách việc phải làm trước khi chạy được
kỳ lương đầu tiên: xem `PAYROLL_SETUP.md` mục 4 (thứ tự setup) và mục 5 (điểm còn chặn).

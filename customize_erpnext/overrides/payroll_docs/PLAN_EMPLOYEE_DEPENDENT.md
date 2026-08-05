# Plan — DocType quản lý Người phụ thuộc (`Employee Dependent`)

> Mục tiêu: có dữ liệu **người phụ thuộc (NPT) theo tháng** để tính thuế TNCN tự động,
> thay cho cách nhập tay hiện nay. Xem bối cảnh ở [`PAYROLL_SETUP.md`](PAYROLL_SETUP.md) mục 5d.
>
> **Trạng thái: mới là plan, chưa code.**

---

## 1. Vì sao phải làm

| | |
|---|---|
| **Hiện tại** | `6.5 PIT` nhập tay qua `Additional Salary` cho từng người, từng tháng |
| **Chặn** | Không có dữ liệu NPT ⇒ không tính được thu nhập tính thuế ⇒ không tự động hoá được |
| **Bằng chứng** | TIQN-0002 và TIQN-0044 có PIT = 0 dù lương cao. Chỉ giải thích được nếu có **≥ 4** và **≥ 5** NPT. xác nhận "có nhiều NPT" nhưng **chưa có con số** |

Mỗi NPT giảm trừ **6.200.000đ/tháng** (Nghị quyết 110/2025, từ kỳ tính thuế 2026) — sai 1 người
là sai thuế **74,4 triệu/năm** trên thu nhập tính thuế.

## 2. Vì sao KHÔNG dùng doctype có sẵn của HRMS

`Employee Tax Exemption Declaration` + `Employee Tax Exemption Category` (site đang có **0 record**,
tức chưa dùng) không phù hợp:

| HRMS | Việt Nam cần |
|---|---|
| Khai theo **năm** (payroll period) | Giảm trừ tính theo **tháng** phát sinh nghĩa vụ nuôi dưỡng |
| Khai theo **số tiền** miễn thuế | Khai theo **số người** × mức cố định |
| Không có khái niệm định danh NPT | Bắt buộc có **số định danh/khai sinh**, chống trùng giữa các NNT |

→ Xây doctype riêng. Không đụng vào doctype HRMS.

## 3. Mô hình dữ liệu

### 3.1. DocType `Employee Dependent`

- Đường dẫn: `customize_erpnext/customize_erpnext/doctype/employee_dependent/`
- Module: **Customize Erpnext** (cùng chỗ `labor_contract`)
- `naming_series`: `DEP-.####`
- **Không submittable** — là hồ sơ nền, sửa nhiều lần; bật `track_changes = 1` để có lịch sử thay đổi
- Permission: `HR Manager` + `HR User` full; **Employee không xem được của người khác**

| Field | Type | Bắt buộc | Ghi chú |
|---|---|:---:|---|
| `employee` | Link → Employee | ✅ | |
| `employee_name` | Data (fetch, read-only) | | |
| `dependent_name` | Data | ✅ | Họ tên NPT |
| `relationship` | Select | ✅ | Con · Vợ/Chồng · Cha mẹ đẻ · Cha mẹ vợ/chồng · Cha nuôi/Mẹ kế · Anh chị em ruột · Ông bà · Cô/dì/chú/bác/cậu · Cháu ruột |
| `date_of_birth` | Date | ✅ | Bắt buộc trên tờ khai thuế + kiểm điều kiện tuổi |
| `id_type` | Select | ✅ | `Căn cước công dân` · `Giấy khai sinh` |
| `id_number` | Data | ✅ | **Khoá chống trùng** |
| `dependent_tax_code` | Data | ❌ | MST NPT — **chỉ có nếu đã được cấp** |
| `from_date` | Date | ✅ | Tháng bắt đầu giảm trừ — **ép về ngày 01** |
| `to_date` | Date | ❌ | Trống = còn hiệu lực |
| `disabled_or_incapacitated` | Check | | Điều kiện nhóm 2/3 |
| `is_studying` | Check | | Con ≥ 18 đang học ĐH/CĐ/TC/nghề |
| `note` | Small Text | | |

> **Vì sao khoá chống trùng là `id_number` chứ không phải MST:** MST NPT chỉ có *nếu đã từng
> được cấp*. Trẻ đăng ký lần đầu chưa có MST → bắt buộc MST thì không nhập được ai.

### 3.2. Mức giảm trừ — nằm trong `TIQN Payroll Settings`

Không hardcode: mức 11tr/4,4tr (đến kỳ 2025) đã đổi thành 15,5tr/6,2tr (từ kỳ 2026), sẽ còn đổi.
Child table `TIQN Tax Deduction Rate`: `from_date` · `personal_deduction` · `dependent_deduction`,
seed 2 mốc `2020-07-01 → 11.000.000 / 4.400.000` và `2026-01-01 → 15.500.000 / 6.200.000`.

→ **Thiết kế đầy đủ + kiểm kê toàn bộ hằng số lương: [`PLAN_PAYROLL_SETTINGS.md`](PLAN_PAYROLL_SETTINGS.md).**
Doctype đó là **điều kiện tiên quyết** của giai đoạn tính PIT tự động ở mục 7.

## 4. Quy tắc validate

| # | Quy tắc | Lý do |
|---|---|---|
| 1 | `id_number` **không trùng** với bản ghi còn hiệu lực của **nhân viên khác** trong cùng năm tính thuế | Luật: mỗi NPT chỉ tính cho **01** NNT trong cùng năm |
| 2 | `dependent_tax_code` nếu điền cũng phải unique | |
| 3 | `from_date` luôn là **ngày 01** của tháng | Giảm trừ tính trọn tháng, không tính lẻ ngày |
| 4 | `to_date >= from_date` | |
| 5 | Một `id_number` không được có **2 khoảng thời gian chồng nhau** trên cùng NNT | |
| 6 | Cảnh báo (không chặn) khi `relationship = Con`, tuổi ≥ 18, mà không tick `disabled_or_incapacitated` lẫn `is_studying` | Điều kiện luật |
| 7 | Cảnh báo khi `Employee.custom_tax_code` trống | Không đăng ký NPT được nếu NNT chưa có MST |

> Quy tắc 1 là quy tắc **cross-employee** — phải query toàn bảng, không chỉ trong hồ sơ đang mở.

## 5. Cách PIT tiêu thụ dữ liệu

### 5.1. API đếm

```python
def get_dependent_count(employee: str, as_on: date) -> int
    # dem ban ghi co from_date <= as_on AND (to_date IS NULL OR to_date >= as_on)
```

**`as_on` lấy `end_date` của Salary Slip.** Kỳ lương 26/06→25/07 là **tháng 7** ⇒ `as_on = 25/07`.
Ghi rõ vì đây là chỗ dễ hiểu nhầm sang `start_date` (26/06 → ra tháng 6, sai một tháng).

### 5.2. 🔴 KHÔNG dùng `Income Tax Slab` của ERPNext

HRMS tính thuế theo mô hình **thu nhập cả năm** rồi chia đều cho số kỳ còn lại
(`calculate_tax_by_tax_slab` chạy trên `get_taxable_earnings` của cả payroll period).
Việt Nam khấu trừ theo **biểu luỹ tiến THÁNG**, quyết toán lại cuối năm.
Hai cách chỉ trùng nhau khi thu nhập đều tất cả các tháng — phiếu lương TIQN dùng biểu tháng.

→ **Tự tính trong hook `apply_regional_deductions`** — HRMS có sẵn điểm móc này
(`salary_slip.py:877`, decorator `@hrms.allow_regional`), đăng ký qua `regional_overrides` cho
region `"Vietnam"`. Đây là cách `frappe/india-payroll` làm cho BHXH/thuế Ấn Độ.
Chi tiết ở [`PLAN_PAYROLL_SETTINGS.md`](PLAN_PAYROLL_SETTINGS.md) mục 2.
**Không** cần override `CustomSalarySlip` cho việc này.

⚠ Hook chạy **sau** khi `gross_pay` đã chốt ⇒ chỉ inject được **deduction**. PIT là deduction nên
hợp lệ; dòng `7.6` (earning) vẫn phải ở lại Salary Structure.

Công thức trong hook:

```
thu_nhap_chiu_thue = tổng earnings có is_tax_applicable = 1
thu_nhap_tinh_thue = thu_nhap_chiu_thue − (BHXH+BHYT+BHTN)
                     − personal_deduction − dependents × dependent_deduction
PIT = biểu 7 bậc luỹ tiến (5/10/15/20/25/30/35%) với số trừ nhanh
```

Cờ `is_tax_applicable` đã khai đúng ở cấp Salary Component (`PAYROLL_SETUP.md` mục 5b8.1) nên
**không cần liệt kê tên khoản trong code** — cứ đọc cờ. Đây là lý do phải sửa cờ cho đúng trước.

Công thức trên **đã kiểm chứng khớp đến từng đồng** với TIQN-0148: `15.923` (mục 5d.1).

### 5.3. Thay `6.5 PIT` từ Additional Salary → dòng trong Salary Structure
Khi tự động hoá xong thì bỏ cách nhập tay. Giữ `Additional Salary` cho
`7.3 Quyết toán thuế` (1 lần/năm) và các trường hợp điều chỉnh.

## 6. Nhập liệu ban đầu

### 6.1. Chặn cứng phải xử lý trước: MST bẩn
Khảo sát 05/08/2026: chỉ **28%** NV Active có MST · **18 cặp trùng** giữa 2 nhân viên khác nhau ·
16 ô ghi chữ (`"Chưa CC"`, `"Không trả lương"`) · 42 ô sai độ dài.
→ Xuất Excel danh sách cho HR rà **trước**, vì không có MST thì không đăng ký NPT được.
*(Việc này làm được ngay, không phụ thuộc doctype.)*

### 6.2. Thu thập
Tờ khai NPT cần: họ tên · ngày sinh · số định danh/khai sinh · MST (nếu có) · quan hệ ·
tháng bắt đầu giảm trừ. Không cần quốc tịch (HR điền tay khi làm thủ tục với cơ quan thuế).

### 6.3. Import
Excel → **Data Import** (doctype không submittable nên đơn giản).
⚠ Phải tắt `site_config.developer_mode` trước, nếu không import chạy inline và treo
(`data_import.py:123`) — cùng bẫy với import SSA.

### 6.4. Dọn field chết trên Employee
`custom_number_of_childrens` · `custom_name_of_child_1/2` · `custom_dob_of_child_1/2` —
**độ phủ 0%**, không ai dùng. Sau khi có doctype mới thì xoá để khỏi có 2 nguồn sự thật.

## 7. Thứ tự triển khai

| GĐ | Việc | Phụ thuộc |
|:--:|---|---|
| **0** | Xuất Excel MST bẩn cho HR rà | – (làm ngay được) |
| **1** | `TIQN Payroll Settings` — xem [`PLAN_PAYROLL_SETTINGS.md`](PLAN_PAYROLL_SETTINGS.md) | – |
| **2** | DocType `Employee Dependent` + validate 1→7 + `get_dependent_count()` | GĐ 1 |
| **3** | Import dữ liệu NPT từ HR | GĐ 2 + GĐ 0 |
| **4** | Tính PIT tự động trong hook `apply_regional_deductions` | GĐ 3 |
| **5** | Bỏ `6.5 PIT` khỏi Additional Salary, đưa lại vào Salary Structure | GĐ 4 |
| **6** | Xoá 5 field chết trên Employee | GĐ 3 |

GĐ 1–2 làm được ngay và không đụng dữ liệu đang chạy. GĐ 4 **không khởi động được** nếu HR
chưa trả dữ liệu NPT — đó là đường tới hạn.

## 8. Kiểm chứng

- Đối chiếu lại **9 phiếu lương** mục 7 `PAYROLL_SETUP.md`: 7 phiếu phải ra đúng PIT với 0 NPT,
  TIQN-0148 phải ra đúng **15.923**
- TIQN-0002 / TIQN-0044: sau khi có số NPT thật, PIT phải ra **0** — nếu không thì giả thuyết sai
- Test đổi tháng: NPT đăng ký `from_date = 01/09` thì kỳ lương tháng 8 **không** được trừ, tháng 9 có
- Test chống trùng: cùng `id_number` cho 2 nhân viên trong cùng năm → phải chặn

## 9. Ràng buộc dự án (vi phạm là hỏng việc)

- ❌ **Không gửi email**, không tạo Notification. Đã có sự cố 154 mail thật bay đi
- ❌ **Không `frappe.db.commit()` trong hàm `@frappe.whitelist()`** — đã làm rò 59 Employee giả
  ra production. Chỉ commit trong background job/scheduler
- ✅ Dùng `business_today()` (`labor_contract.py`), **không** `frappe.utils.today()` —
  `System Settings.time_zone` từng nhiều lần tự nhảy về Asia/Kolkata
- ✅ UI **English-first**, bọc `__()` / `_()`, dịch qua `translations/vi.csv`
- ✅ File Excel tải về thêm hậu tố `YYMMDD HHMMSS`
- ✅ Chỉ commit git **sau khi user test OK trên UI thật**

## 10. Việc KHÔNG làm

- Không tự động lấy NPT từ nguồn ngoài (VNeID, cơ quan thuế) — không có API, và là dữ liệu nhạy cảm
- Không tự sinh MST NPT — do cơ quan thuế cấp
- Không cho Employee tự khai NPT qua portal ở giai đoạn này — cần quy trình duyệt của HR trước
- Không đụng vào các doctype thuế của HRMS

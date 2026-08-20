# Plan — DocType quản lý Người phụ thuộc (`Employee Dependent`)

> **Mục đích:** Mục tiêu: có dữ liệu **người phụ thuộc (NPT) theo tháng** để tính thuế TNCN tự động,
> **Phạm vi:** Override HRMS/ERPNext
> **Trạng thái:** Kế hoạch · **Cập nhật:** 2026-08-10

> Mục tiêu: có dữ liệu **người phụ thuộc (NPT) theo tháng** để tính thuế TNCN tự động,
> thay cho cách nhập tay hiện nay. Xem bối cảnh ở [`PAYROLL_SETUP.md`](PAYROLL_SETUP.md) mục 2.8.
>
> **Trạng thái: ✅ ĐÃ TRIỂN KHAI.** DocType + validate + tính thuế đều xong.
> Còn thiếu **dữ liệu NPT thực tế từ HR** — chưa có thì thuế tính với 0 người phụ thuộc,
> nhóm lương cao bị tính thừa thuế.

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

### 3.1. Một hồ sơ / nhân viên + child table

**Phạm vi dữ liệu — chốt 07/08/2026:** HR vẫn kê khai với cơ quan thuế bằng **phần mềm riêng**,
chi tiết hơn ERP. Nên ERP chỉ lưu **vừa đủ để tính lương**, không nhân bản tờ khai thuế:
đã bỏ `taxpayer_tax_code`, `dependent_tax_code`, `id_type`, `disabled_or_incapacitated`,
`is_studying`.

`id_number` **được giữ** dù thuộc phần khai báo: nhà máy có nhiều gia đình cùng làm, hai anh em
cùng khai một người mẹ làm **sai tiền lương thật** — phần mềm kia không nhìn thấy nội bộ ERP.

#### `Employee Dependent` (cha)

- `customize_erpnext/customize_erpnext/doctype/employee_dependent/`
- `autoname = field:employee` ⇒ **docname chính là mã nhân viên**. Đây là cách bảo đảm
  *một nhân viên một hồ sơ* — không cần validate, primary key lo. Cũng nhờ vậy
  `Employee Dependent Item.parent` = mã NV, đếm NPT chỉ cần **một query trên child table**,
  không phải join
- **Không submittable** — hồ sơ nền, sửa nhiều lần; `track_changes = 1` để có lịch sử
- Permission: `HR Manager` + `HR User` full; Employee không xem được của người khác

| Field | Type | Bắt buộc |
|---|---|:---:|
| `employee` | Link → Employee | ✅ |
| `employee_name` | Data (fetch, read-only) | |
| `company` | Link → Company | |
| `dependents` | **Table → Employee Dependent Item** | ✅ |
| `note` | Small Text | |

#### `Employee Dependent Item` (con)

| Field | Type | Bắt buộc | Ghi chú |
|---|---|:---:|---|
| `dependent_name` | Data | ✅ | |
| `relationship` | Select | ✅ | Con · Vợ/Chồng · Cha mẹ đẻ · Cha mẹ vợ/chồng · Cha nuôi/Mẹ kế · Anh chị em ruột · Ông bà · Cô/dì/chú/bác/cậu · Cháu ruột |
| `date_of_birth` | Date | ✅ *nếu* `relationship = Child` | Chỉ để cảnh báo quá 18 tuổi |
| `id_number` | Data | ✅ | **Khoá chống trùng** — CCCD, hoặc số giấy khai sinh với trẻ chưa có CCCD |
| `from_date` | Date | ✅ | Tháng bắt đầu giảm trừ — **ép về ngày 01** |
| `to_date` | Date | ❌ | Trống = còn hiệu lực |

> **Vì sao khoá chống trùng là `id_number` chứ không phải MST:** MST NPT chỉ có *nếu đã từng
> được cấp*. Trẻ đăng ký lần đầu chưa có MST → bắt buộc MST thì không nhập được ai.
> ERP nay cũng không lưu MST NPT nữa.

### 3.2. Mức giảm trừ — nằm trong `TIQN Payroll Settings`

Không hardcode: mức 11tr/4,4tr (đến kỳ 2025) đã đổi thành 15,5tr/6,2tr (từ kỳ 2026), sẽ còn đổi.
Child table `TIQN Tax Deduction Rate`: `from_date` · `personal_deduction` · `dependent_deduction`,
seed 2 mốc `2020-07-01 → 11.000.000 / 4.400.000` và `2026-01-01 → 15.500.000 / 6.200.000`.

→ **Thiết kế đầy đủ + kiểm kê toàn bộ hằng số lương: [`PLAN_PAYROLL_SETTINGS.md`](PLAN_PAYROLL_SETTINGS.md).**
Doctype đó là **điều kiện tiên quyết** của giai đoạn tính PIT tự động ở mục 7.

## 4. Quy tắc validate

| # | Quy tắc | Tầng | Lý do |
|---|---|---|---|
| 1 | Một nhân viên **một** hồ sơ | primary key | `autoname = field:employee` |
| 2 | `id_number` **không trùng** với hồ sơ của **nhân viên khác** trong cùng năm tính thuế — **trừ khi hai hồ sơ cùng MST** | chặn | Luật: mỗi NPT chỉ tính cho **01** NNT trong cùng năm. Ngoại lệ MST: xem ghi chú dưới |
| 3 | `from_date` luôn là **ngày 01** của tháng | tự sửa | Giảm trừ tính trọn tháng, không tính lẻ ngày |
| 4 | `to_date >= from_date` | chặn | |
| 5 | Một `id_number` không có **2 dòng chồng thời gian** trong cùng hồ sơ | chặn | Hai dòng rời nhau (ngừng rồi khai lại) vẫn hợp lệ |
| 6 | `relationship = Con`, đã đủ 18 tuổi mà **`to_date` trống** | cảnh báo | Quên `to_date` ⇒ trừ thừa 6,2tr/tháng **mãi mãi**. Điều kiện "đang học"/"khuyết tật" nằm ở phần mềm kê khai của HR, ERP không lưu nên không tự phán được |

> Quy tắc 2 là quy tắc **cross-employee** — query toàn bộ child table, không chỉ hồ sơ đang mở.

> 🔴 **Ngoại lệ tái tuyển (HR xác nhận 05/08/2026):** NLĐ nghỉ việc rồi vào lại được tạo hồ sơ
> `Employee` **mới**, nên **cùng một người có 2 mã NV**. Đó cũng là lý do có 18 cặp MST trùng
> trong dữ liệu — không phải lỗi nhập liệu.
>
> Nếu chặn theo mã NV thì HR **không khai được** NPT trên hồ sơ mới. Cách nhận diện duy nhất là
> **MST**: hai hồ sơ cùng MST = cùng người nộp thuế ⇒ bỏ qua kiểm tra trùng.
> Đã test với cặp thật `TIQN-0061` / `TIQN-0063` (cùng MST `8088766587`): cho qua;
> khai sang `TIQN-0019` (người khác) vẫn bị chặn.

## 5. Cách PIT tiêu thụ dữ liệu

### 5.1. API đếm

```python
def get_dependent_count(employee: str, as_on: date) -> int
    # dem dong child co from_date <= as_on AND (to_date IS NULL OR to_date >= as_on)
    # parent == employee (autoname field:employee) -> khong can join sang doctype cha
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

Cờ `is_tax_applicable` đã khai đúng ở cấp Salary Component (`PAYROLL_SETUP.md` mục 4.1) nên
**không cần liệt kê tên khoản trong code** — cứ đọc cờ. Đây là lý do phải sửa cờ cho đúng trước.

Công thức trên **đã kiểm chứng khớp đến từng đồng** với TIQN-0148: `15.923` (mục 2.8).

### 5.3. Thay `6.5 PIT` từ Additional Salary → dòng trong Salary Structure
Khi tự động hoá xong thì bỏ cách nhập tay. Giữ `Additional Salary` cho
`7.3 Quyết toán thuế` (1 lần/năm) và các trường hợp điều chỉnh.

## 6. Nhập liệu ban đầu

### 6.1. MST — độ phủ thấp nhưng KHÔNG chặn

Khảo sát 05/08/2026 trên NV Active: chỉ **28%** có MST · 18 cặp trùng · 16 ô ghi chữ
(`"Chưa CC"`, `"Không trả lương"`) · 42 ô sai độ dài.

- **18 cặp trùng: KHÔNG phải lỗi** — là NLĐ tái tuyển có 2 hồ sơ (xem ghi chú mục 4)
- Thiếu MST **không chặn** việc khai NPT — chỉ cảnh báo cam, vì HR có thể nhập hồ sơ trước
  rồi bổ sung MST sau khi đăng ký với cơ quan thuế

> ❌ **Đã bỏ:** báo cáo "MST bẩn" cho HR rà — HR cho biết không cần.

### 6.2. Thu thập
ERP chỉ cần: **họ tên · quan hệ · ngày sinh (nếu là con) · số định danh/khai sinh ·
tháng bắt đầu giảm trừ**. MST NPT, loại giấy tờ, hồ sơ chứng minh điều kiện → để ở phần mềm
kê khai thuế của HR, không nhập vào ERP.

### 6.3. Import
Excel → **Data Import**, chọn doctype con `Employee Dependent Item` với cột `parent` = mã NV
(đây là lợi thế của `autoname = field:employee`: người nhập không phải tra docname cha).
⚠ Phải tắt `site_config.developer_mode` trước, nếu không import chạy inline và treo
(`data_import.py:123`) — cùng bẫy với import SSA.
⚠ Data Import **không chạy `validate()` của cha** khi ghi thẳng vào child table ⇒ luật chống
trùng không được áp. Sau khi import phải mở/lưu lại hồ sơ, hoặc chạy một lượt rà trùng riêng.

### 6.4. ❌ KHÔNG dọn 5 field con nhỏ trên Employee

`custom_number_of_childrens` · `custom_name_of_child_1/2` · `custom_dob_of_child_1/2`.

Bản plan đầu đề xuất xoá vì tưởng độ phủ 0%. **Sai** — khảo sát ban đầu đếm
`custom_number_of_childrens > 0` nên bỏ sót bản ghi để 0; thực tế **2.397 bản ghi** có giá trị.
HR xác nhận các field này **dùng cho mục đích khác** ⇒ giữ nguyên.

> Bài học: kiểm "field có chết không" phải dùng `ifnull(f,'') <> ''`, không phải `f > 0`.

## 7. Thứ tự triển khai — trạng thái

| GĐ | Việc | Trạng thái |
|:--:|---|---|
| 0 | Excel MST bẩn cho HR rà | ❌ HR không cần |
| 1 | `TIQN Payroll Settings` | ✅ xong, đã seed |
| 2 | `Employee Dependent` (cha + child table) + validate + `get_dependent_count()` | ✅ xong, test 5/5 |
| 3 | **Import dữ liệu NPT từ HR** | 🔴 **chưa có dữ liệu — đường tới hạn** |
| 4 | Tính PIT tự động | ✅ xong (hook `apply_regional_deductions`) |
| 5 | Bỏ `6.5 PIT` khỏi Additional Salary | ✅ xong — nay tính trong hook |
| 6 | Xoá 5 field con nhỏ trên Employee | ❌ không làm — dùng cho mục đích khác |

> ⚠ Thuế TNCN **đang chạy với 0 người phụ thuộc** cho mọi nhân viên. Với phần lớn công nhân
> kết quả vẫn đúng (thu nhập dưới mức giảm trừ bản thân 15,5tr), nhưng nhóm lương cao sẽ bị
> **tính thừa thuế** cho tới khi có dữ liệu NPT.

## 8. Kiểm chứng

- Đối chiếu lại **9 phiếu lương** mục 7 `PAYROLL_SETUP.md`: 7 phiếu phải ra đúng PIT với 0 NPT,
  TIQN-0148 phải ra đúng **15.923**
- TIQN-0002 / TIQN-0044: sau khi có số NPT thật, PIT phải ra **0** — nếu không thì giả thuyết sai
- Test đổi tháng: NPT đăng ký `from_date = 01/09` thì kỳ lương tháng 8 **không** được trừ, tháng 9 có
- Test chống trùng: cùng `id_number` cho 2 nhân viên trong cùng năm → phải chặn;
  khác năm tính thuế → phải cho qua

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

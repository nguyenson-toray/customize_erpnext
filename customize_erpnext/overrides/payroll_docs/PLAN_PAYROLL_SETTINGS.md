# Plan — `TIQN Payroll Settings`: gom hằng số lương vào một chỗ

> **Mục đích:** Mục tiêu: bỏ hardcode các con số do **pháp luật** và **quy chế công ty** quy định, để khi văn bản
> **Phạm vi:** Override HRMS/ERPNext
> **Trạng thái:** Kế hoạch · **Cập nhật:** 2026-08-10

> Mục tiêu: bỏ hardcode các con số do **pháp luật** và **quy chế công ty** quy định, để khi văn bản
> thay đổi thì sửa cấu hình chứ không phải sửa code/deploy.
>
> **Trạng thái: ✅ ĐÃ TRIỂN KHAI 05/08/2026.** Xem kết quả ở `PAYROLL_SETUP.md` mục 3.

---

## 1. 🔴 Ràng buộc quyết định kiến trúc

Formula trong Salary Structure **KHÔNG đọc được Settings**. Context eval bị giới hạn cứng:

```python
# hrms/payroll/utils.py:34
COMPONENT_EVAL_GLOBALS = {"int", "float", "long", "round", "rounded",
                          "date", "getdate", "get_first_day", "get_last_day",
                          "ceil", "floor", "min", "max"}
```

Không có `frappe`, không truy cập DB, không gọi hàm tự viết. Dữ liệu duy nhất formula thấy được là
field của **SSA**, **Employee**, và abbr của các component khác.

→ Không thể "một Settings, mọi nơi đọc". Phải chia **3 tầng** theo *ai tiêu thụ hằng số*.

## 2. Hook `apply_regional_deductions` của HRMS

Giải bài toán "công thức không đọc được Settings" bằng cách **không dùng công thức**.
Cách làm học từ **`frappe/india-payroll`** — app thống kê chính thức của Frappe cho luật Ấn Độ.

```python
# hrms/payroll/doctype/salary_slip/salary_slip.py:877
@hrms.allow_regional
def apply_regional_deductions(self):
    "Hook point for region-specific salary slip deductions."
    pass
```

Được gọi ở dòng **869**, đúng vị trí cần:

```
calculate_component_amounts("earnings")
set_gross_pay_and_base_gross_pay()        <-- gross_pay chot o day
calculate_component_amounts("deductions")
set_loan_repayment()
apply_regional_deductions()               <-- HOOK: Python thuan, doc duoc moi thu
set_precision_for_component_amounts()
set_net_pay()                             <-- total_deduction + net_pay tinh sau
```

Đăng ký trong `hooks.py`:

```python
regional_overrides = {
    "Vietnam": {
        "hrms.payroll.doctype.salary_slip.salary_slip.apply_regional_deductions":
            "customize_erpnext.overrides.payroll.vn_deductions.apply_regional_deductions",
    }
}
```

✅ **Đã xác minh chạy được trên site này:** `Company.country = "Vietnam"` ⇒ `erpnext.get_region()`
trả `"Vietnam"` ⇒ hook khớp. Không cần override `CustomSalarySlip` cho phần này.

### Ý nghĩa

Trong hook là **Python thuần** — đọc được Settings, DB, số NPT, biểu thuế.

Tính bằng Python: `6.1/6.2/6.3` BHXH·BHYT·BHTN (tỷ lệ từ Settings theo ngày hiệu lực) ·
`6.4` đoàn phí · `6.5` PIT (biểu thuế + NPT + giảm trừ) · mốc 14 ngày ·
danh sách Employment Type thử việc khai **một chỗ** thay vì lặp 6 chỗ trong formula.

### ⚠ Giới hạn của hook — chỉ inject được DEDUCTION

`gross_pay` đã chốt **trước** khi hook chạy. Append vào `doc.earnings` trong hook thì
**không vào `gross_pay`** ⇒ sai tổng.

→ Dòng **`7.6` hoàn 21,5% cho NV thử việc là EARNING** nên **phải giữ trong Salary Structure**
dưới dạng formula + condition như hiện nay. Đây là ngoại lệ duy nhất.

## 3. Kiểm kê toàn bộ hằng số

### 3.1. TẦNG A — Python đọc trực tiếp Settings

| # | Hằng số | Giá trị hiện tại | Căn cứ | Hiệu lực theo ngày? |
|:--:|---|---|---|:--:|
| A1 | Giảm trừ bản thân | **15.500.000**/tháng | NQ 110/2025 (trước: 11.000.000) | ✅ **bắt buộc** |
| A2 | Giảm trừ mỗi NPT | **6.200.000**/tháng | NQ 110/2025 (trước: 4.400.000) | ✅ **bắt buộc** |
| A3 | Biểu thuế luỹ tiến **7 bậc** | 5/10/15/20/25/30/35% + ngưỡng + số trừ nhanh | Luật TNCN | ✅ **bắt buộc** |
| A4 | **Thử việc: thuế suất cố định · thu nhập tối thiểu** | **10%** · **2.000.000** | TT 111/2013 Đ.25 | ➖ |
| A5 | Trần OT ngày · tháng · năm | **4h · 40h · 300h** | BLLĐ Đ.107 + NĐ 145/2020 | ➖ (chỉ cảnh báo) |
| A6 | Khung giờ ban đêm | **22:00 – 06:00** | BLLĐ Đ.106 | ➖ |
| A7 | Phụ cấp đêm · OT đêm cộng thêm | **30%** · **20%** | BLLĐ Đ.98 kh.2, kh.3 | ✅ (chưa dùng) |
| A8 | Áp trần đóng BH? · lương cơ sở | **KHÔNG áp** · 2.340.000 | TIQN không áp trần (mục 2.6) | ✅ |
| A9 | Phép năm | **14 ngày** / 12 tháng | Quy chế mục 2 | ➖ |
| A10 | Ngưỡng cảnh báo lệch SI Base | **1.000đ** | nội bộ | ➖ |

> A1–A3 là nhóm quan trọng nhất: đây chính là chỗ `PLAN_EMPLOYEE_DEPENDENT.md` cần.
> Sai một con số là sai thuế toàn nhà máy.

### 3.2. Hằng số đang nằm cứng trong formula Salary Structure

| # | Hằng số | Giá trị | Xuất hiện ở | Hiệu lực theo ngày? |
|:--:|---|---|---|:--:|
| B1 | Giờ làm việc chuẩn / ngày | **8** | đơn giá OT (3 dòng) | ➖ |
| B2 | Hệ số OT thường · cuối tuần · lễ | **1.5 · 2.0 · 3.0** | dòng 2.1 / 2.2 / 2.3 | ✅ |
| B3 | Ngưỡng ngày công hưởng nguyên mức | **8** ngày | dòng 3.3, 3.7, 3.8, 3.9 | ➖ |
| B4 | Ngưỡng ngày công phụ cấp nhà ở | **14** ngày | dòng 3.4 | ➖ |
| B5 | Tỷ lệ nhà ở khi dưới ngưỡng | **0.5** (½ tháng) | dòng 3.4 | ➖ |
| B6 | Hệ số hỗ trợ làm ca | **20%** | dòng 4.5 | ➖ |
| B7 | Hỗ trợ tiền cơm · ngưỡng giờ OT CN | **50.000** · **> 4h** | dòng 7.1 | ➖ |
| B8 | Hoàn phần công ty đóng khi thử việc | **21,5%** | dòng 7.6 | ✅ |
| B9 | Tỷ lệ BHXH · BHYT · BHTN (NLĐ) | **8% · 1,5% · 1%** | dòng 6.1 / 6.2 / 6.3 | ✅ **bắt buộc** |
| B10 | Phí công đoàn | **38.948** | dòng 6.4 (`amount`) | ✅ |
| B11 | Danh sách Employment Type = thử việc | `["30 Days...", "60 Days..."]` | **6 chỗ** (4 condition + 2 formula) | ➖ |

| **Chuyển sang Python (hook)** | B8 (một phần), **B9, B10, B11** |
| **Ở lại formula** (tầng B′) | B1–B7, và B8 vì `7.6` là **earning** — xem giới hạn hook ở mục 2 |

> **B11 là món nợ lớn nhất về bảo trì.** Chuỗi lặp 6 lần; thêm một loại HĐ thử việc mới
> (ví dụ *"45 Days Probationary Contract"*) phải sửa đúng 6 chỗ, sót một chỗ thì **âm thầm
> trừ sai bảo hiểm**. Sau khi B9/B10 chuyển sang hook thì chỉ còn **2 chỗ** trong formula
> (`3.9` và `4.2`) — khai `probation_employment_types` trong Settings và Python đọc thẳng.

### 3.3. TẦNG C — KHÔNG đưa vào Settings

| Nhóm | Vì sao |
|---|---|
| Mức phụ cấp **theo từng người**: chức vụ 7tr/5tr/500k–3tr · kỹ thuật ≤10tr · nhà ở 2,3–5tr · trách nhiệm 500k–2tr | Đã nằm trên **SSA per person**. Đưa vào Settings = **hai nguồn sự thật** |
| Mức **đồng nhất** nhưng vẫn per-person: PCCC 772.000 · ATVS 20.000 · xăng xe 300.000 · điện thoại 200.000 | Có thể để Settings làm **giá trị mặc định khi tạo SSA**, **không** phải nguồn tính toán — vẫn cho phép ngoại lệ từng người |
| Bậc thưởng chuyên cần (800k/500k/0 và 900k/800k/700k/600k), max 1.300.000 | Chưa tự động hoá được (cần đếm số lần nghỉ/đi trễ). Khi làm thì mới đưa vào |
| Quà cưới 1.000.000 · phúng viếng 500k+2tr · bồi dưỡng 13.000/suất · bữa ăn ≤20.000 | Trả qua **Additional Salary**, HR nhập số tiền theo từng vụ việc |
| Chu kỳ lương 26→25 · hạn trả ngày 05 · ca 06–14/14–22 · xem xét lương tháng 4 | Nằm ở Payroll Entry / Shift Type / quy trình, không phải hằng số tính toán |
| `SI_BASE_FIELDS` — 8 khoản cấu thành căn cứ BH | Là **tên field**, không phải số. Đổi = đổi code. Giữ trong `salary_structure_assignment.py` |

---

## 4. Thiết kế DocType

### 4.1. ✅ CHỐT — tạo Single riêng `TIQN Payroll Settings`

**Lý do chính là phân vai người dùng, không phải kỹ thuật:**

| DocType | Ai set | Tần suất | Nội dung |
|---|---|---|---|
| `Payroll Settings` (HRMS) | **IT Admin** | **1 lần**, lúc dựng hệ thống | Hành vi Payroll Entry, "Consider Unmarked Attendance As", đánh số phiếu… |
| **`TIQN Payroll Settings`** | **HR** | Mỗi khi có văn bản mới | Mức giảm trừ, biểu thuế, tỷ lệ BH, trần OT, ngưỡng ngày công… |

Trộn hai nhóm này vào một form là bắt HR phải đi qua các cấu hình kỹ thuật họ không được phép
đụng, và ngược lại. Tách ra thì phân quyền sạch: HR có `write` trên `TIQN Payroll Settings`,
**không** có trên `Payroll Settings`.

Lý do kỹ thuật đi kèm:
- Child table **vẫn phải là doctype của app ta** dù đặt ở đâu ⇒ nhét vào `Payroll Settings`
  qua Custom Field không tiết kiệm được gì, chỉ rối thêm
- `Payroll Settings` là doctype của HRMS — mỗi bản nâng cấp có thể thêm field/đổi layout,
  `insert_after` của ta trôi theo. Doctype riêng thì bất biến
- Bật `track_changes = 1` để có lịch sử: đổi mức giảm trừ là việc phải truy được ai sửa, lúc nào

**Không** làm link qua lại giữa hai doctype, **không** tách theo company (chỉ có 1 công ty).

> ⚠ **Thứ tự vận hành khi tạo doctype:** cần `developer_mode = 1` để Frappe ghi JSON ra app
> (có version control). Nhưng chính cờ đó làm **Data Import chạy inline** và treo với >1000 dòng
> (`data_import.py:123`). ⇒ **Bật dev mode → tạo doctype → tắt dev mode → import dữ liệu.**

### 4.2. Cấu trúc

```
TIQN Payroll Settings (Single)
├─ [Thuế TNCN]
│   ├─ table: TIQN Tax Deduction Rate   (from_date, personal_deduction, dependent_deduction)
│   └─ table: TIQN Tax Bracket          (from_date, level, from_amount, to_amount,
│                                        rate_percent, quick_deduction)
├─ [Bảo hiểm]
│   ├─ table: TIQN Insurance Rate       (from_date, si_pct, hi_pct, ui_pct,
│   │                                    employer_refund_pct)      # 8 / 1.5 / 1 / 21.5
│   ├─ apply_si_ceiling (Check)  ·  base_salary (Currency)         # hien: KHONG ap tran
│   └─ union_fee_amount (Currency)                                  # 38.948
├─ [Làm thêm giờ]
│   ├─ standard_hours_per_day (Float = 8)
│   ├─ ot_rate_normal / weekend / holiday  (Percent = 150 / 200 / 300)
│   ├─ ot_cap_per_day / per_month / per_year  (4 / 40 / 300)
│   └─ night_start (22:00) · night_end (06:00)
│       night_premium_pct (30) · night_ot_extra_pct (20)
├─ [Chính sách công ty]
│   ├─ min_days_for_full_allowance (Int = 8)
│   ├─ min_days_for_full_accommodation (Int = 14)
│   ├─ accommodation_partial_ratio (Float = 0.5)
│   ├─ shift_support_pct (Percent = 20)
│   ├─ meal_support_amount (Currency = 50.000)
│   ├─ meal_support_ot_threshold_hours (Float = 4)
│   ├─ annual_leave_days_per_year (Float = 14)
│   └─ probation_employment_types  → Table MultiSelect → Employment Type
├─ [Miễn thuế]
│   └─ meal_tax_exempt_monthly (Currency = 730.000)
└─ [Bật/tắt tính tự động]
    ├─ enable_insurance_auto (Check)   # BHXH/BHYT/BHTN + phí công đoàn qua hook
    └─ enable_pit_auto (Check)         # TẮT khi dữ liệu NPT chưa đủ
```

### 4.3. Hàm tra cứu theo ngày hiệu lực

```python
def get_rate(table: str, as_on: date) -> frappe._dict
    # lay dong co from_date lon nhat ma <= as_on
```

Dùng cho 3 bảng có hiệu lực. `as_on` = **`end_date` của Salary Slip** (cùng quy ước với đếm NPT —
xem `PLAN_EMPLOYEE_DEPENDENT.md` mục 5.1).

## 4b. Điểm kỹ thuật ÁP DỤNG ĐƯỢC từ `frappe/india-payroll`

Repo tham khảo (không cài): `github.com/frappe/india-payroll`.
Dưới đây là những thứ dùng lại được, kèm chỗ áp dụng cụ thể.

### 4b.1. Khung chuẩn của một hàm inject deduction

Thứ tự guard của họ giống nhau ở cả 4 module (EPF/ESI/LWF/PT) — dùng làm **template**:

```python
def apply_vn_insurance(doc, method=None) -> None:
    # 1. Co bat tinh nang khong
    if not frappe.db.get_single_value("TIQN Payroll Settings", "enable_insurance_auto"):
        return
    # 2. Co salary structure khong (slip nhap tay thi bo qua)
    if not doc.salary_structure:
        return
    # 3. Component co ton tai khong -> CANH BAO, khong throw
    if not frappe.db.exists("Salary Component", SI_COMPONENT):
        frappe.msgprint(_("Thiếu Salary Component {0}").format(SI_COMPONENT),
                        indicator="orange", alert=True)
        return
    # 4. Doc tham so hieu luc theo ngay
    rate = get_rate("insurance", doc.end_date)
    # 5. Tinh
    amount = flt(si_base * rate.si_pct / 100, 0)
    # 6. XOA dong cu -> roi moi append   (xem 4b.2)
    _upsert(doc, SI_COMPONENT, amount)
```

> **Điểm 3 quan trọng:** thiếu component thì **cảnh báo**, không `throw`. Nếu throw, một
> component bị xoá nhầm sẽ làm **gãy cả kỳ lương 1000 người** thay vì chỉ sai một dòng.

### 4b.2. 🔴 Idempotent — bắt buộc

```python
def _upsert(doc, component, amount):
    doc.deductions = [d for d in doc.deductions if d.salary_component != component]
    if amount > 0:
        doc.append("deductions", {"salary_component": component, "amount": amount})
```

Salary Slip được tính lại nhiều lần (save, đổi ngày công, Payroll Entry chạy lại).
**Không xoá dòng cũ trước khi append là nhân đôi khấu trừ** — và sẽ không ai phát hiện
cho tới khi NLĐ thắc mắc.

Kể cả khi số tiền = 0 vẫn phải xoá: NV chuyển từ chính thức sang thử việc mà không xoá
thì dòng BHXH cũ **vẫn nằm lại trên phiếu**.

### 4b.3. Tra tham số theo ngày hiệu lực — dùng `doc.end_date`

`india_payroll/utils.py` tra SSA bằng `on_date = doc.end_date`.
✅ **Trùng đúng quy ước ta đã chọn** cho việc đếm NPT — xác nhận độc lập rằng
kỳ 26/06→25/07 phải quy về **tháng 7**.

### 4b.4. Tách "ngưỡng bao phủ" khỏi "số tiền tính"

ESI kiểm tra có thuộc diện đóng hay không bằng gross **chưa prorate**:

```python
def _full_gross(doc):
    return sum(flt(e.default_amount) for e in doc.earnings if not e.do_not_include_in_total)
```

nhưng **tính tiền** trên `doc.gross_pay` (đã prorate).

→ Áp dụng khi nào TIQN áp trần đóng BH (hiện **không** áp — mục 2.6). Nếu dùng chung một số,
người lương cao nghỉ nhiều ngày sẽ **lọt vào diện đóng** sai.
Lưu ý `default_amount` = giá trị đầy đủ chưa prorate, `amount` = đã prorate — cặp field này
cũng hữu ích cho báo cáo.

### 4b.5. Khoản chỉ phát sinh ở tháng nhất định

LWF có `frequency: monthly | half-yearly | annual` + tập tháng áp dụng:

```python
_HALF_YEARLY_MONTHS = frozenset({6, 12})
_ANNUAL_MONTHS = frozenset({12})
```

→ Áp dụng thẳng cho **phụ cấp kinh nguyệt** (quy chế: trả **1 lần/năm cùng lương tháng 12**)
và **thưởng Tết** (trả cùng lương tháng trước Tết). Hiện hai khoản này đi qua Additional Salary
nhập tay; nếu muốn tự động thì đây là mẫu.

### 4b.6. Cờ bật/tắt từng chế độ

`enable_esic` · `enable_epf` · `enable_lwf` · `enable_professional_tax` · `enable_tds_filing`.

→ Ta cần ít nhất: **`enable_pit_auto`** (bật tính thuế tự động — để **tắt** khi dữ liệu NPT
chưa đủ, thay vì tính ra số sai) và **`enable_insurance_auto`** (để chuyển dần từ formula
trong Salary Structure sang hook mà không phải làm một phát ăn ngay).

### 4b.7. Field đặc thù đặt trên SSA, không phải Employee

`is_person_with_disability` · `epf_applicable` · `lwf_exempted` · `employment_state` —
tất cả nằm trên **Salary Structure Assignment**, không phải Employee.

Lý do: SSA có `from_date` ⇒ **tự có lịch sử**. Đổi diện đóng từ tháng nào thì tạo SSA mới từ
tháng đó, phiếu lương cũ giữ nguyên. ✅ Trùng cách ta đã làm với `custom_si_base_override`.

### 4b.8. Test cho từng chế độ, không test cả kỳ lương

`test_epf.py` (16 KB) · `test_esi.py` (13 KB) · `test_lwf.py` (11 KB) · `test_professional_tax.py`.
Mỗi chế độ một file, test thẳng hàm `apply_*` với doc dựng sẵn — không phải chạy cả Payroll Entry.

→ Rất hợp với ta: **9 phiếu lương thật ở `PAYROLL_SETUP.md` mục 7 là bộ test case sẵn có.**
Viết `test_vn_deductions.py` chạy 9 case đó qua hook và so với số thật.

> ⚠ Nhắc lại rule dự án: **không `frappe.db.commit()` trong test/whitelist** — đã có sự cố
> 59 Employee giả lọt production.

### 🔴 Điểm họ làm KHÁC ta — và đáng cân nhắc

**`india-payroll` HARDCODE toàn bộ tỷ lệ/biểu thuế trong Python**, không đưa vào Settings:

```python
ESI_RATE = 0.04
ESI_WAGE_CEILING = 21_000
STATE_PT_CONFIG = {"Karnataka": {"frequency": "monthly", "slabs": [...]}, ...}
```

Trong `Payroll Settings` họ **chỉ** để: cờ bật/tắt · số đăng ký (mã số ESIC, EPF) · khoá API.

**Lý lẽ của cách đó:** tỷ lệ luật hiếm đổi; đổi thì phải qua PR + test + review. Một con số sai
trong file cấu hình thì **âm thầm**, còn sai trong code thì có test bắt.

**Vì sao ta vẫn nên khác họ ở nhóm A1–A3:** Việt Nam **vừa đổi** mức giảm trừ (11tr→15,5tr,
4,4tr→6,2tr) ngay trong phạm vi dữ liệu ta phải xử lý, và **phiếu lương cũ phải tính lại ra số cũ**
⇒ bắt buộc có **ngày hiệu lực**, thứ mà hằng số Python không diễn đạt được.

→ **Chốt: nhóm luật có tiền + cần lịch sử (A1–A3, tỷ lệ BH, phí công đoàn) → Settings có ngày
hiệu lực. Nhóm còn lại → hằng số Python có comment dẫn văn bản**, giống india-payroll.

## 5. Trạng thái triển khai

| Việc | |
|---|---|
| `TIQN Payroll Settings` + 3 child table có ngày hiệu lực + seed | ✅ |
| `overrides/payroll/vn_deductions.py` + `regional_overrides` cho `"Vietnam"` | ✅ |
| Gỡ `6.1–6.4` khỏi Salary Structure — structure còn thuần lương/phụ cấp | ✅ |
| PIT trong hook (biểu luỹ tiến · thử việc 10% · đếm NPT) | ✅ |
| Mốc 14 ngày đóng BH | ✅ |

Hai cờ `enable_insurance_auto` / `enable_pit_auto` đang **bật**.

## 6. Cái được

| | |
|---|---|
| **Đổi luật** | Sửa 1 dòng trong Settings + bấm Áp dụng, không deploy |
| **Truy vết** | Có ngày hiệu lực ⇒ tính lại kỳ lương cũ vẫn ra đúng số cũ |
| **Giảm lỗi im lặng** | B11 (danh sách HĐ thử việc lặp 6 chỗ) về còn 1 chỗ |
| **Tài liệu sống** | Toàn bộ hằng số nằm một nơi, đọc được trên UI thay vì phải đọc code |

## 7. Cái KHÔNG giải quyết được

- Formula vẫn phải chứa **con số cụ thể** — Settings chỉ là nguồn để sinh ra chúng.
  Ai sửa formula thẳng trên Salary Structure vẫn làm lệch khỏi Settings.
  → Nên có **báo cáo đối chiếu** Settings ↔ formula thực tế, chạy định kỳ.
- Đổi **cấu trúc** biểu thuế (ví dụ rút từ 7 bậc xuống 5 bậc) thì child table chịu được,
  nhưng đổi **cách tính** (ví dụ bỏ số trừ nhanh) vẫn phải sửa code.

# Labor Contract

> **Mục đích:** Quản lý hạn hợp đồng lao động và cảnh báo tái ký.
> **Phạm vi:** DocType tự phát triển
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-20

Quản lý hạn hợp đồng lao động và cảnh báo tái ký. Mỗi record = **1 lần ký hợp đồng**
(không gộp nhiều giai đoạn vào 1 record), nên lịch sử hợp đồng của một nhân viên là
một chuỗi nhiều record nối tiếp nhau.

> **Phạm vi:** chỉ theo dõi hạn hợp đồng. Không in hợp đồng, không mail merge, không lương.

---

## 1. Chuỗi hợp đồng

Thứ tự cố định, **không nhảy cóc, không hở ngày**:

```
[30 ngày thử việc]  ─┐
                     ├──►  HĐLĐ 1 năm  ──►  HĐLĐ 3 năm  ──►  Không xác định thời hạn (điểm dừng)
[60 ngày thử việc]  ─┘
```

Nhân viên chỉ đi qua **một trong hai** loại thử việc (30 hoặc 60 ngày, tuỳ chức danh),
không đi qua cả hai. Vì vậy giai đoạn kế tiếp **không** suy được bằng `SEQUENCE[i+1]` —
phải tra bảng `NEXT_CONTRACT_TYPE`.

`Indefinite-term` là điểm dừng: không có `end_date`, không có giai đoạn kế tiếp.

---

## 2. Data model

### 2.1. Employment Type (doctype có sẵn — chỉ thêm custom field)

| Field | Type | Ý nghĩa |
|---|---|---|
| `custom_period` | Int | Số ngày hiệu lực. **0/trống** với Indefinite-term |
| `custom_warning_before` | Int | Cảnh báo trước bao nhiêu ngày. **0/trống** với Indefinite-term |

Giá trị chuẩn (patch `setup_labor_contract` tự tạo/sửa cho khớp):

| Employment Type | period | warning_before |
|---|---:|---:|
| 30 Days Probationary Contract | 30 | 7 |
| 60 Days Probationary Contract | 60 | 14 |
| 1 Year Employment Contract | 365 | 30 |
| 3 Year Employment Contract | 1095 | 30 |
| Indefinite-term Employment Contract | 0 | 0 |

### 2.2. Employee (có sẵn, không sửa)

- `Designation.custom_probation_days` (Select 30/60) → chức danh áp dụng thử việc bao lâu
- `Employee.custom_probation_days` — fetch từ Designation, dùng để suy loại HĐ thử việc đầu tiên
- `Employee.employment_type` — **được module này ghi tự động**, xem mục 5

### 2.3. Labor Contract (doctype mới)

| Field | Type | Ghi chú |
|---|---|---|
| `employee` | Link → Employee | reqd |
| `employee_name`, `designation`, `department` | fetch, read-only | Từ Employee |
| `custom_section`, `custom_group` | Link | fetch từ Employee, sửa tay được |
| `contract_type` | Link → Employment Type | reqd — loại của **chính giai đoạn này** |
| `start_date` | Date | reqd |
| `end_date` | Date, read-only | **Derived** — trống nếu Indefinite-term |
| `next_contract_type` | Link, read-only | **Derived** — trống nếu Indefinite-term |
| `next_sign_date` | Date, read-only | **Derived** = `end_date + 1` |
| `status` | Select | `Upcoming` / `Signed` / `Overdue` — default `Upcoming` |
| `next_stage_created` | Check, **ẩn** | Cờ chống tạo trùng giai đoạn kế tiếp |
| `manager_email` | Data, **ẩn**, read-only | Tự suy từ `employee.reports_to.user_id`. Hiện chưa dùng — để sẵn cho Notification sau này |

Autoname: `format:LC-{employee}-{#####}`

---

## 3. Công thức tính ngày

Ba field derived được **tính lại mỗi lần save** (kể cả khi HR sửa tay), nên không bao giờ
lệch so với cấu hình Employment Type hiện tại:

```python
period    = Employment Type[contract_type].custom_period
end_date  = start_date + period - 1        # -1 để bao trọn đủ số ngày, không dư 1 ngày
            None nếu period = 0            # Indefinite-term
next_type = NEXT_CONTRACT_TYPE[contract_type]
next_sign_date = end_date + 1              # chỉ khi có cả end_date lẫn next_type
```

> Ví dụ: thử việc 60 ngày từ `2021-11-01` → `end_date = 2021-12-30` (không phải 12-31).

---

## 4. Vòng đời & các đường tạo record

### 4.1. Trigger A — Nhân viên mới (tự động)

`hooks.py` → `doc_events["Employee"]["after_insert"]`
→ `create_initial_contract_on_employee_insert`

- Bỏ qua hoàn toàn khi `frappe.flags.in_import` (import hàng loạt NV cũ)
- `custom_probation_days` = 30/60 → tạo HĐ thử việc tương ứng, `start_date = date_of_joining`, `status = Upcoming`
- `= 0` → **không tạo**, báo alert "tạo tay" (xem mục 6)
- rỗng → **không tạo**, báo alert

### 4.2. Trigger B — Job daily 00:00

`hooks.py` → `scheduler_events["cron"]["0 0 * * *"]` → `process_labor_contracts_daily`

Chạy **đúng thứ tự** 2 bước (đảo thứ tự sẽ đánh Overdue oan record vừa tạo trong ngày):

1. **Materialize** — với HĐ `Signed`, `next_stage_created = 0`, có `next_contract_type`,
   NV còn `Active`, và `end_date - today <= custom_warning_before`:
   tạo HĐ giai đoạn kế tiếp (`start_date = end_date + 1`, `Upcoming`), rồi set cờ
   `next_stage_created = 1` trên HĐ cũ. Giới hạn 500 record/lượt.
2. **Overdue** — `Upcoming` mà `start_date < today` → chuyển `Overdue`.

### 4.3. Các nút trên List View

| Nút | Ai dùng được | Tác dụng |
|---|---|---|
| **Create Probation Contracts** | có quyền create | Tạo HĐ thử việc đầu tiên cho **một đợt nhận việc** (chọn 1 ngày vào làm cụ thể), hoặc chọn tay vài NV. Có bảng liệt kê từng NV kèm lý do bỏ qua trước khi bấm |
| **Review Expiring Contracts** | có quyền create | Rà HĐ hết hạn trong khoảng ngày (mặc định ngày 1 → cuối tháng), bấm tạo hàng loạt HĐ kế tiếp ở trạng thái `Upcoming`. Tối đa 500/lượt |
| **Mark as Signed** | có quyền write | Đánh dấu đã ký hàng loạt. Có tick sẵn dòng thì chạy luôn; không tick thì mở bảng chọn (lọc theo nhiều NV) |
| **Seed Contract History** *(menu ⋯)* | **chỉ Administrator** | Dựng **toàn bộ chuỗi lịch sử** từ ngày vào làm đến hôm nay cho NV có sẵn. Chạy 1 lần lúc go-live |

**Seeding** khác Create Probation Contracts ở chỗ: nó đi hết chuỗi để NV cũ đáp đúng
giai đoạn hiện tại. Mọi giai đoạn đều ghi `Signed` (là sự thật trên giấy tờ), tất cả
trừ giai đoạn cuối được set `next_stage_created = 1` để job daily không tạo trùng;
giai đoạn cuối để mở cho job tiếp quản.

---

## 5. Employee.employment_type — gương của HĐ hiện hành

`on_update` và `after_delete` của Labor Contract gọi `sync_employee_employment_type()`.

Giá trị được **tính lại từ cả chuỗi**, không copy từ record vừa save:

> HĐ hiện hành = HĐ `Signed` **mới nhất đã tới ngày bắt đầu**.

Lý do quan trọng: sau khi seeding, mỗi NV có tới 4 HĐ đều `Signed`. Nếu copy từ record
vừa save thì chỉ cần ai đó mở lại HĐ thử việc năm 2020 bấm save là `employment_type`
tụt về "30 Days Probationary" — sai hoàn toàn. HĐ đã ký nhưng **chưa tới ngày bắt đầu**
cũng không được tính.

Backfill 1 lần: `resync_all_employment_types()` (**Administrator-only** — nó ghi đè lên
mọi NV và mang tính áp đặt: NV không có HĐ Signed hợp lệ sẽ bị **xoá trắng** field này).

---

## 6. Probation Days = 0 — trường hợp đặc biệt

`0` nghĩa là tuyển vào **không qua thử việc** (hiếm). Giai đoạn đầu là gì (1 năm? 3 năm?)
là quyết định nghiệp vụ nên hệ thống **không đoán** — HR tự tạo hợp đồng tay.

Hệ thống tách `0` thành lý do bỏ qua **riêng**, khác hẳn với rỗng, để HR nhìn bảng kết quả
là biết ngay phải làm gì:

| Giá trị | Lý do hiển thị | Hành động của HR |
|---|---|---|
| `0` | *No probation period (0) — create the contract manually* | Tạo hợp đồng tay |
| rỗng | *Probation Days is not set* | Bổ sung Probation Days cho Designation |

---

## 7. Report

**Labor Contract Report** (Script Report) — cột giống hệt view "Labor Contract Report 1".

Filter: `Next Sign Date` từ/đến · `Start Date` từ/đến · Status · Contract Type ·
Employee · Section · Group · Employee Status (mặc định `Active`).

Sắp xếp theo `next_sign_date` để việc cần làm sớm nhất nằm trên. Status được tô màu
xanh/cam/đỏ.

---

## 8. Những điểm dễ sai (đọc trước khi sửa code)

### 8.1. Email — KHÔNG được tự ý bật
Module **cố ý không có** bất kỳ Notification / `frappe.sendmail` nào. Bản đầu tiên của
patch từng tạo Notification `enabled = 1` với `receiver_by_role = "HR Manager"`; role đó
nở ra **11 tài khoản thật** và một lần bulk-create 14 hợp đồng đã bắn **154 email thật**
trong khi nội dung mail chưa được duyệt.

Khi nào cần cảnh báo mail: tạo Notification ở trạng thái **tắt**, **recipients rỗng**,
để Admin tự điền người nhận và tự bật. Xem RULE #1 trong `.claude/skills/erpnext-frappe/SKILL.md`.

### 8.2. `business_today()` — một nguồn ngày duy nhất
Mọi so sánh ngày (SQL lẫn Python) đều đi qua hàm này, đọc `CURDATE()` từ DB.

Lý do: `System Settings.time_zone` trên site này **từng nhiều lần tự nhảy về Asia/Kolkata**
(UTC+5:30) trong khi DB server chạy giờ Việt Nam (UTC+7). Khi đó `frappe.utils.today()`
chậm hơn `CURDATE()` một ngày trong khung 00:00–01:30 — **đúng lúc job daily chạy**.
Đừng thay bằng `frappe.utils.today()`.

### 8.3. `after_delete`, không phải `on_trash`
`on_trash` chạy **trước** khi row bị xoá khỏi bảng, nên cả `sync_employee_employment_type`
lẫn `release_predecessor` đều sẽ vẫn nhìn thấy chính record đang xoá → kết quả sai.

### 8.4. Xoá HĐ con phải gỡ cờ HĐ cha
`release_predecessor()` xoá cờ `next_stage_created` trên HĐ liền trước (nhận diện qua
`end_date = start_date - 1`). Thiếu bước này, HR xoá nhầm HĐ kế tiếp là HĐ cha **kẹt cờ
vĩnh viễn**: job daily lẫn nút rà soát đều bỏ qua nó mãi mãi, không có đường sửa trên UI
vì đó là field ẩn.

### 8.5. Không `frappe.db.commit()` trong hàm `@whitelist`
Frappe tự commit cuối request thành công. Commit trong hàm whitelist làm **rò dữ liệu test
ra DB production** (test gọi thẳng hàm đó, commit thoát khỏi rollback). Sự cố thật:
59 Employee giả + 70 hợp đồng giả nằm lại DB, kéo theo 1174 bản ghi Attendance rác do job
chấm công tự sinh cho các NV giả đang `Active`.

Chỉ commit trong **background job** và **scheduler task**.

---

## 9. File liên quan

```
customize_erpnext/customize_erpnext/doctype/labor_contract/
├── labor_contract.py            # controller + toàn bộ API
├── labor_contract.json          # schema
├── labor_contract_list.js       # 3 nút + menu Seed
├── test_labor_contract.py       # 51 test
└── labor_contract.md

customize_erpnext/customize_erpnext/report/labor_contract_report/
customize_erpnext/patches/setup_labor_contract.py   # custom field + 5 Employment Type
```

hooks.py: `doc_events["Employee"]["after_insert"]` · `scheduler_events["cron"]["0 0 * * *"]`
· fixtures Custom Field cho `Employment Type`

Chạy test: `bench --site {site} run-tests --module customize_erpnext.customize_erpnext.doctype.labor_contract.test_labor_contract`

---

## 10. Roadmap — In hợp đồng ra PDF (chưa làm)

Mục tiêu: in hợp đồng hàng loạt ra PDF, trên đó có thông tin cá nhân + **thông tin lương khác nhau
theo nhóm người lao động**.

### 10.1. Điều kiện tiên quyết: phải chạy phần lương trước

Hệ thống hiện **chưa có dữ liệu lương** — `Salary Structure Assignment` = 0 record, `Salary Slip` = 0,
`Payroll Entry` = 0; mới chỉ khai 50 `Salary Component`. Lương thật đang nằm trong Excel của HR.

**Chốt: dùng `Salary Structure` + `Salary Structure Assignment` của ERPNext**, KHÔNG dựng model lương
riêng cho hợp đồng. Lý do: sau này chạy payroll dùng lại được ngay, không phải nhập/đồng bộ 2 nơi;
và `SSA.from_date` đã giải quyết sẵn bài toán lương thay đổi theo thời gian.

| Hạng mục | Chốt |
|---|---|
| Số Salary Structure | **16** = top-15 Designation + 1 fallback. Structure chỉ quy định *có những phụ cấp gì*; mức lương chính nằm ở `SSA.base` per nhân viên, nên không cần 68 structure cho 68 chức danh |
| `SSA.base` | Đa số theo chức danh, có ngoại lệ theo thâm niên / người cũ được tăng lương → set hàng loạt theo designation rồi sửa tay ngoại lệ |
| `SSA.from_date` | **Một mốc chung cho cả lô** (xem lý do bên dưới) — KHÔNG phải ngày vào làm từng người |

**Vì sao `from_date` dùng một mốc chung, không dùng `date_of_joining`:** tool `Bulk Salary Structure
Assignment` chỉ nhận **một `from_date` cho cả lô**, và chỉ liệt kê NV có `date_of_joining <= from_date`.
Đặt `from_date` riêng từng người sẽ buộc phải tự viết tool — mà **không đem lại lợi ích gì**, vì:
- Đã chốt **không backfill lương cho 2615 HĐ đã Signed** (không biết lương thời điểm đó)
- 105 HĐ Upcoming đều có `start_date` từ **04/08/2026 trở đi** → chỉ cần lương hiệu lực từ hôm nay

Số đo thực tế khi chọn mốc: `from_date = 2026-08-04` → tool hiện **1038/1038** NV Active;
`2026-08-01` → 1024/1038; `2026-01-01` → chỉ 663/1038 (sót 375 người vào làm trong 2026).
→ Chọn mốc **= ngày chạy** để phủ 100%. NV vào làm sau đó: chạy lại tool với mốc mới (quy trình
thường kỳ), tool tự loại người đã có SSA nên không tạo trùng.

⚠ **Không dùng lại Salary Structure "Salary Structure All"**: 16 dòng của nó là shape *bảng tính lương*
(Overtime, Monthly Salary c=a+b, Incentive, PIT Finalization, Net Salary) — dòng tính khi trả lương,
không phải điều khoản hợp đồng. Hợp đồng chỉ ghi mức lương chính + phụ cấp cố định.

⚠ **Không thêm component tính thuế** (`variable_based_on_taxable_salary`) vào structure — sẽ ép SSA
phải có `Income Tax Slab`, mà site đang có **0 record**.

**Gán SSA hàng loạt — dùng tool có sẵn của HRMS, KHÔNG cần viết code**

Từ **HRMS v16.15.0** có doctype `Bulk Salary Structure Assignment` (Single, mở như một trang công cụ)
làm đúng việc này:
- Lọc NV theo company / branch / department / **designation** / employment_type / grade + advanced filter
- Tự **loại bỏ NV đã có SSA** tại `from_date` đó → chạy lại nhiều lần vẫn an toàn
- Hiện bảng NV với cột **`base` và `variable` sửa được từng dòng**
- `base` mồi sẵn từ **`Employee Grade.default_base_pay`**
- Nút **Update → Base**: tick nhiều dòng, nhập 1 số, áp cho cả nhóm
- Cảnh báo nếu `base = 0`; ≤30 NV chạy inline, >30 tự `frappe.enqueue` kèm `publish_progress`

**Quy trình đề xuất** (SSA là submittable → sai phải cancel+amend, nên làm đúng thứ tự):
1. Set `default_base_pay` cho 6 Employee Grade (Worker 881 · Staff 81 · Sub Leader 44 · Leader 26 ·
   Manager 5 · Factory Manager 0 — **hiện tất cả đang = 0**) để mồi sẵn con số nền
2. Mở tool, đặt `from_date` = ngày chạy, lọc **từng designation một**
3. Tick tất cả → **Update → Base** = mức chuẩn của chức danh đó
4. **Sửa tay các ngoại lệ ngay trên bảng** (thâm niên, người cũ đã tăng lương) *trước khi* bấm Assign
5. Assign → tool tự bỏ qua người đã có SSA nên chạy lại an toàn

⚠ **Không import SSA bằng Data Import**: `site_config.developer_mode = 1` khiến Data Import chạy
inline → treo *"Request Timed Out"* với ~1000 dòng (bẫy đã ghi trong memory dự án).

→ Chỉ viết script import riêng **nếu** Excel của HR thật sự có ~1000 mức lương khác nhau từng người
(gõ tay vào datatable không khả thi). Nếu lương gom về vài mức theo chức danh thì tool có sẵn là đủ.

### 10.2. Ý chính phần in hợp đồng

- **Lấy lương**: tra SSA `docstatus=1`, `from_date <= contract.start_date`, lấy bản `from_date` lớn
  nhất → `base` + earnings của structure tương ứng.
- **Vẫn phải snapshot lương vào hợp đồng khi ký** (child table + thời điểm chụp): SSA là submittable,
  có thể bị cancel/amend về sau làm đổi "sự thật lịch sử"; hợp đồng là văn bản pháp lý nên bất biến.
  Khoá không cho sửa khi `status = Signed`. **Không backfill** 2615 hợp đồng đã Signed — không biết
  lương thời điểm đó, bịa số vào văn bản pháp lý là sai.
- **Template**: doctype `Labor Contract Template` chứa Jinja HTML (field kiểu `Code`) để HR sửa câu
  chữ trên UI, không cần lập trình viên. Phân giải 3 bậc: `contract_type` + `designation` → chỉ
  `contract_type` → fallback. Câu chữ pháp lý khác nhau chủ yếu theo `contract_type` nên chỉ cần 3–5
  template; `designation` là chiều ghi đè tuỳ chọn. `validate()` phải dry-render để bắt lỗi Jinja
  ngay lúc save.
- **Sinh PDF**: tái dụng `api/employee/employee_utils.py:456 generate_employee_cards_pdf()` (đã có bộ
  options wkhtmltopdf chuẩn). Render **từng hợp đồng rồi merge bằng `pypdf`** — không gộp HTML in 1
  lần vì "Trang X/Y" sẽ đếm xuyên cả lô, sai trên văn bản pháp lý. Mặc định 2 bản/hợp đồng.
- **Logo**: dùng `/assets/customize_erpnext/images/logo_500.jpg` (print format `overtime_registration_v2`
  đang dùng). Không dùng `Letter Head` (record duy nhất đang `disabled=1`, `image=NULL`) và không dùng
  `/files/icon-logo.ico`.
- **Không dùng `frappe.format` cho tiền**: `System Settings.number_format` là `# ###,##` (dấu cách),
  hợp đồng VN cần dấu chấm → viết helper riêng. Đọc số bằng chữ cũng phải tự viết, `money_in_words`
  ra tiếng Anh.
- **Dữ liệu thiếu**: hộ khẩu thường trú / quê quán / dân tộc đều 0%, không có field nơi sinh. BLLĐ
  2019 Điều 21 chỉ yêu cầu **"nơi cư trú"** → `custom_current_address_full` (89.8%) là đủ, không cần
  mở dự án nhập liệu. Thêm bước preflight chặn in khi thiếu field bắt buộc.
- **Tuyệt đối không gửi email** trong tính năng in (xem mục 8.1).

### 10.3. HR cần chốt trước khi làm

Số hợp đồng theo quy ước nào (`name` hiện tại là ID nội bộ, không in lên hợp đồng được) · người đại
diện bên A + số văn bản uỷ quyền · song ngữ hay thuần Việt · lương thử việc 85% hay 100% · danh sách
phụ cấp in lên hợp đồng · có in số tài khoản ngân hàng không (`bank_ac_no` đã có sẵn 90%).

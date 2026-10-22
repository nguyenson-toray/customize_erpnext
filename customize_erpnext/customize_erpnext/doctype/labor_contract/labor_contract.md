# Labor Contract

> **Mục đích:** Quản lý hợp đồng lao động (HĐ) và phụ lục (PL), cảnh báo tái ký.
> **Phạm vi:** DocType tự phát triển
> **Trạng thái:** Đang chạy (v3 từ 22/10/2026) · **Cập nhật:** 2026-10-22

**Mỗi record = 1 văn bản giấy** — một HĐ (một giai đoạn của chuỗi) hoặc một PL. Tên record
**chính là số văn bản** HR in trên giấy:

| Văn bản | Tên record |
|---|---|
| HĐ thử việc (30/60 ngày) | `{NV}-HD` |
| HĐ 1 năm | `{NV}-HD1` |
| HĐ 3 năm | `{NV}-HD2` |
| HĐ không thời hạn | `{NV}-HD3` |
| Phụ lục | `PL-{NV}-{YYMM của ngày hiệu lực}` |

Trùng số (ký lại cùng giai đoạn, 2 PL cùng tháng) → thêm hậu tố `-2`, `-3` (VD `PL-TIQN-0001-2610-2`).

**DocType chỉ giữ thông tin của văn bản.** Thông tin NV (chức danh, bộ phận, CCCD, địa chỉ…)
do report / Export tự kéo từ Employee; chức danh **tại một ngày** lấy từ Internal Work History
(`positions_at()`).

> **Không làm:** lương (PENDING), in HĐ ra PDF (mục 10). Mail merge = file Export (mục 7).

**Dữ liệu trước 22/10/2026** (tên cũ `LC-{NV}-{NN}`): 3.014 HĐ đã chép sang DocType này (bảng đối
chiếu tên cũ → mới: `private/backups/20261022_labor_contract_v3_mapping.csv`). DocType tạm
`Labor Contract Legacy` đã **xoá hẳn** ngày 22/10/2026 (user yêu cầu); bản lưu: dump bảng cũ
`private/backups/20261022_labor_contract_before_v3.sql.gz` + `20261022_labor_contract_legacy_archive.json.gz`
(3.014 HĐ + 228 Version + 3.048 Comment).

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

### 2.3. Labor Contract

| Field | Type | Ghi chú |
|---|---|---|
| `employee` | Link → Employee | reqd, đặt 1 lần |
| `employee_name`, `employee_status`, `relieving_date` | fetch | Từ Employee (lọc nhanh trên List View) |
| `document_type` | Select | **Contract** / **Appendix**, đặt 1 lần |
| `contract_type` | Link → Employment Type | Contract: loại của **chính giai đoạn này**, đặt 1 lần (số HĐ theo nó). Appendix: trống |
| `parent_contract` | Link → Labor Contract, read-only | Appendix: HĐ đang hiệu lực tại ngày hiệu lực — **tự điền mỗi lần save** |
| `start_date` | Date | reqd. Appendix: **ngày hiệu lực** (form đổi nhãn) |
| `end_date`, `next_contract_type`, `next_sign_date` | read-only | **Derived**, chỉ Contract |
| `status` | Select | `Upcoming` / `Signed` / `Overdue` |
| `signed_on` | Date | Ngày ký thực tế. Đổi sang Signed mà trống → hôm nay. Đổi khỏi Signed → xoá trống. Record **tạo mới** ở trạng thái Signed (dữ liệu lịch sử, HĐ chuyển từ bản cũ) → để trống, không bịa |
| `change_type` | Select | Appendix: **L** = lương · **C** = chức vụ · **LC** = cả hai (cột "Thay đổi" của HR) |
| `reference_doctype`, `reference_name` | Dynamic Link, read-only | Appendix: phiếu Employee Promotion / Transfer sinh ra nó |
| `scan` | Attach | Bản scan văn bản đã ký — **tên file phải bắt đầu bằng số văn bản**, file private (mục 4.5) |
| `next_stage_created` | Check, **ẩn** | Cờ chống tạo trùng giai đoạn kế tiếp |

Đã bỏ (22/10/2026): `designation`, `department`, `custom_section`, `custom_group` (fetch lúc tạo
record → 132 HĐ ghi chức danh hiện tại thay vì lúc ký) và `manager_email` (không ai đọc).

Autoname: `autoname()` trong controller (`document_number()` + hậu tố trùng). Kiểm `contract_type`
/ ngày hiệu lực ngay trong `autoname()` vì nó chạy **trước** `validate`. PL đã tạo **không đổi
được sang tháng khác** (số PL chứa YYMM) — phải xoá tạo lại.

---

## 3. Công thức tính ngày

Ba field derived được **tính lại mỗi lần save** (`compute_end_date()`), user chốt 22/10/2026:

```python
thử việc 30/60:  end_date = start_date + custom_period - 1     # theo ngày
HĐ 1 năm / 3 năm: end_date = cùng ngày 1 / 3 năm sau - 1        # theo năm dương lịch
                  (start 29/02 coi như 01/03 → kết thúc 28/02)
không thời hạn:   end_date = None
next_type        = NEXT_CONTRACT_TYPE[contract_type]
next_sign_date   = end_date + 1                                 # khi có cả end_date lẫn next_type
```

> Ví dụ: HĐ 3 năm từ `31/12/2022` → `30/12/2025`. Thử việc 60 ngày từ `2021-11-01` → `2021-12-30`.

`custom_period` 365/1095 của 2 loại HĐ năm **không còn dùng để tính ngày** (chỉ còn `custom_warning_before`).
Đổi công thức 22/10/2026 làm 943/3.014 HĐ lệch 1–2 ngày so với trước, 0 NV đổi `employment_type`.

---

## 4. Vòng đời & các đường tạo record

### 4.1. Trigger A — Nhân viên mới (tự động)

`hooks.py` → `doc_events["Employee"]["after_insert"]`
→ `create_initial_contract_on_employee_insert` (bật lại 21/10/2026)

- Chạy **cả khi tạo NV bằng Data Import** — đường nhận việc thực tế ở TIQN (trước 21/10/2026 hook
  bỏ qua `in_import`); khi import thì không hiện alert, NV lỗi sẽ nằm trong danh sách của
  nút Create Probation Contracts
- `custom_probation_days` = 30/60 → tạo HĐ thử việc tương ứng, `start_date = date_of_joining`, `status = Upcoming`
- `= 0` → **không tạo**, báo alert "tạo tay" (xem mục 6)
- rỗng → **không tạo, im lặng** (chức danh đặc biệt, không theo dõi hợp đồng)
- HĐ tạo ra ở trạng thái Upcoming → `employment_type` do file import điền được **giữ nguyên** (mục 5)

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
| **Create Probation Contracts** | có quyền create | Liệt kê NV Active chưa có HĐ nào (bỏ qua NV Probation Days trống) và tạo HĐ thử việc; hoặc chọn tay vài NV |
| **Review Expiring Contracts** | có quyền create | Rà HĐ hết hạn trong khoảng ngày (mặc định ngày 1 → cuối tháng), bấm tạo hàng loạt HĐ kế tiếp `Upcoming`. Tối đa 500/lượt |
| **Mark as Signed** | có quyền write | Đánh dấu đã ký hàng loạt **cả HĐ lẫn PL**, có ô **Signed On** (ngày ký thực tế, mặc định hôm nay). Có tick sẵn dòng thì hỏi ngày rồi chạy; không tick thì mở bảng chọn. Kết quả liệt kê dòng bị bỏ qua + lý do |
| **Upload Signed Scans** (menu ⋯) | có quyền write | Chọn nhiều file scan → xem trước file nào vào văn bản nào → upload; tuỳ chọn đánh Signed luôn (mặc định bật, ô Signed On). Mục 4.5 |
| **Download Signed Scans** (menu ⋯) | có quyền create (HR) | ZIP các scan của dòng đã tick, không tick = mọi văn bản theo bộ lọc hiện tại (tối đa 3.000). Tên trong ZIP = số văn bản; văn bản chưa có scan liệt kê trong `_missing_scans.txt` |

Công cụ Seed Contract History (go-live 21/10) đã bỏ ở v3.

### 4.4. Phụ lục (Appendix)

- **Từ Employee Promotion / Employee Transfer**: tick **Create Contract Appendix** trước khi Submit
  → Submit tạo PL `Upcoming`, `change_type = C`, link ngược về phiếu (sau khi dựng lại Internal Work
  History). NV không có HĐ hiệu lực tại ngày đó → **chặn Submit**.
  Quên tick → phiếu đã Submit có nút **Create Contract Appendix** (có rồi thì nút *View → Contract Appendix*).
- **Cancel phiếu**: PL chưa ký → xoá theo; PL đã ký → **chặn Cancel** (phải xoá PL trước).
- **Tạo tay** trên form (VD đổi lương): chọn Document Type = Appendix, nhập ngày hiệu lực.
- PL **không** ảnh hưởng `employment_type`. Job 00:00 đánh `Overdue` cho cả PL quá ngày hiệu lực.
- Code: `create_appendix_on_submit` / `remove_appendix_on_cancel` trong `labor_contract.py`, gọi từ
  `overrides/employee_property/employee_{promotion,transfer}.py`; nút ở
  `public/js/custom_scripts/employee_property_update_override.js`.

### 4.5. Bản scan đã ký (`scan`)

User yêu cầu 22/10/2026: **tên file bắt đầu bằng số văn bản** (= name của record).
- Khớp tên: số văn bản **dài nhất** mà tên file bắt đầu bằng, và phải hết ở ranh giới từ (sau đó
  là hết tên, dấu cách, `_`, `-`, `.`…). `TIQN-2548-HD1.pdf` → HD1 (không phải HD);
  `TIQN-2548-HD1-2.pdf` → HD1-2 nếu record đó có; `TIQN-2548-HD1 ky.pdf` được; không phân biệt hoa thường.
- Lưu ở thư mục riêng **`private/files/labor_contract_scans/`** (giống ảnh NV ở `files/employee_photos/`), do bản vá
  `overrides/lms_file_storage/lms_file_storage.py` (`_save_labor_contract_scan`; xoá đúng file trong thư mục con —
  hàm gốc Frappe chỉ lấy basename nên sẽ xoá nhầm file cùng tên ở `private/files/`). Form có nút **Download Signed Scan**.
- Chỉ PDF / JPG / PNG, luôn **private** (có CCCD, lương). Văn bản đã có scan → phải Clear trên form
  rồi mới upload lại. Cùng 1 file (content hash) cho 2 văn bản → chặn.
- Upload đi qua `upload_file` với `method = upload_scan`: kiểm tên **trước khi** tạo File (Frappe
  đổi tên file trùng trên đĩa thành `TIQN-2548-HD1a3f9c2.pdf`, và upload sai tên sẽ để lại
  attachment rác). Form: field Scan dùng cùng method, xong thì reload form và hỏi Mark as Signed.
- `validate_scan()` chặn các đường khác (Data Import, API): file public hoặc tên không khớp → lỗi;
  chịu được hậu tố 6 ký tự content hash của Frappe.

### 4.6. Email thứ Hai hằng tuần

`Labor Contract Settings` (Single): bật/tắt + danh sách người nhận (mặc định **son.nt@tiqn.com.vn**, user
yêu cầu 22/10/2026). Cron `0 8 * * 1` → `labor_contract_settings.send_weekly_contract_email`:
- **HĐ hết hạn trong tuần** (End Date thứ Hai → Chủ nhật, NV còn làm sau ngày hết hạn) + HĐ kế tiếp đã tạo chưa / trạng thái.
- **Đã tạo nhưng chưa ký** (Upcoming/Overdue, cả PL; bỏ văn bản bắt đầu từ ngày nghỉ việc trở đi); tô đỏ khi quá 30 ngày.
- Nút **Send Weekly Email Now** trên Settings (gửi ngay tới người nhận đã lưu). Bảng HTML dùng `bgcolor` để forward Outlook không vỡ.
- 🔴 Cron mới → phải `bench migrate` (restart không đủ).

---

## 5. Employee.employment_type — gương của HĐ hiện hành

`on_update` và `after_delete` của Labor Contract gọi `sync_employee_employment_type()`.

Giá trị được **tính lại từ cả chuỗi**, không copy từ record vừa save:

> HĐ hiện hành = HĐ `Signed` **mới nhất đã tới ngày bắt đầu**.

Lý do quan trọng: sau khi seeding, mỗi NV có tới 4 HĐ đều `Signed`. Nếu copy từ record
vừa save thì chỉ cần ai đó mở lại HĐ thử việc năm 2020 bấm save là `employment_type`
tụt về "30 Days Probationary" — sai hoàn toàn. HĐ đã ký nhưng **chưa tới ngày bắt đầu**
cũng không được tính.

Backfill 1 lần: `resync_all_employment_types()` (**Administrator-only**).

**Chưa có HĐ Signed nào đã bắt đầu → GIỮ NGUYÊN `employment_type`** (sửa 21/10/2026). Lý do: hook
`after_insert` tạo HĐ thử việc ở trạng thái Upcoming khi import NV mới; nếu xoá trắng thì giá trị
"Probationary" do file import điền bị mất và payroll (đọc field này để biết thử việc) tính sai
cho tới khi HR bấm ký.

---

## 5b. Nhân viên nghỉ trước ngày ký hợp đồng kế tiếp

`relieving_date` ở TIQN là **ngày đầu tiên nghỉ** (ngày làm cuối = relieving_date − 1).
Nếu `relieving_date <= next_sign_date` thì tới ngày hợp đồng mới bắt đầu, NV đã nghỉ, nên
**không tạo, không ký hợp đồng kế tiếp**. Kiểm bằng `leaves_before(relieving_date, start)`:

| Chỗ | Xử lý |
|---|---|
| Job daily `_materialize_next_stage` | Bỏ qua, không tạo giai đoạn kế tiếp |
| Review Expiring Contracts | Dòng bị chặn, lý do *"Leaves on {date} — no next contract"* |
| `_mark_overdue` | HĐ Upcoming bắt đầu từ ngày nghỉ trở đi **không** bị đánh Overdue |
| Mark as Signed | Bảng chọn không liệt kê HĐ đó; tick tay thì bị bỏ qua kèm lý do |
| Labor Contract Report | Có cột Relieving Date; Next Sign Date / Next Contract Type bị gạch mờ |

HĐ Upcoming đã lỡ tạo trước khi NV báo nghỉ **không tự xoá**: HR tự xoá nếu muốn.

## 6. Probation Days = 0 — trường hợp đặc biệt

`0` nghĩa là tuyển vào **không qua thử việc** (hiếm). Giai đoạn đầu là gì (1 năm? 3 năm?)
là quyết định nghiệp vụ nên hệ thống **không đoán** — HR tự tạo hợp đồng tay.

Hệ thống tách `0` thành lý do bỏ qua **riêng**, khác hẳn với rỗng, để HR nhìn bảng kết quả
là biết ngay phải làm gì:

| Giá trị | Lý do hiển thị | Hành động của HR |
|---|---|---|
| `0` | *No probation period (0) — create the contract manually* | Tạo hợp đồng tay |
| rỗng | *No Probation Days — no contract needed* | Không làm gì — xem dưới |

**Rỗng = chức danh đặc biệt, KHÔNG theo dõi hợp đồng** (user chốt 21/10/2026). Chỉ một số
chức danh như giám đốc, trưởng chi nhánh để trống Probation Days; người mang các chức
danh đó không thử việc và bỏ qua hẳn phần hợp đồng. Vì vậy chế độ mặc định của nút
**Create Probation Contracts** ("All Employees Missing a Contract") không liệt kê họ.
Giá trị cần xét là `Employee.custom_probation_days` (chốt theo chức danh **lúc tuyển**,
`set_only_once`), không phải chức danh hiện tại.

> Lưu ý: Designation chỉ có lựa chọn trống/30/60, nên giá trị `0` hiện không thể nhập được.

---

## 7. Report

### 7.1. Labor Contract Report (mỗi văn bản 1 dòng)

| Filter | Ý nghĩa |
|---|---|
| **Current Contract Only** (mặc định BẬT) | Chỉ **HĐ** đang hiệu lực hôm nay của NV **còn làm** (`relieving_date` trống hoặc sau hôm nay) — mỗi NV 1 dòng. Bỏ tick = xem cả lịch sử và PL |
| **Expiring** | Theo **End Date**: This Week / Next Week / This Month / Next Month / Next 30 Days / Next 60 Days / Custom |
| Document Type · Status · Contract Type · Employee | Lọc thẳng trên dòng |

- Designation / Section / Group = **tại ngày bắt đầu văn bản** (Internal Work History), không phải
  hiện tại. Server vẫn nhận filter Section/Group (lọc sau khi tính) — 2 ô này đang comment trong JS.
**Expiring ≠ Overdue** (tách nghĩa 22/10/2026):

| | Expiring — *sắp hết hạn* | Overdue — *trễ ký* |
|---|---|---|
| Nói về | HĐ **đang hiệu lực** | Văn bản **mới** chưa ký |
| Tính theo | End Date (tương lai) | Ngày lẽ ra có hiệu lực (quá khứ) |
| Cột | **Days Left** | **Days Overdue** |

- **Days Left** = End Date − hôm nay, luôn hiện khi HĐ còn hạn; sau khi hết hạn chỉ hiện (âm) khi
  **chưa có HĐ kế tiếp**. Trống khi NV đã nghỉ. Đỏ < 0, cam ≤ `custom_warning_before`.
  (Trước đây trống ngay khi HĐ kế tiếp được tạo → trong Expiring 32/45 dòng mất số.)
- **Next Contract Status**: trạng thái HĐ kế tiếp (HĐ đầu tiên bắt đầu sau HĐ này — không so đúng
  ngày, để HĐ sửa tay ngày không bị tưởng là thiếu). *Not Created* chỉ hiện khi **đã tới hạn**
  (trong khoảng cảnh báo hoặc đã hết hạn); chưa tới hạn → trống.
- **Days Overdue** gồm 2 trường hợp: (1) văn bản chưa ký đã qua ngày hiệu lực → tính từ ngày bắt đầu;
  (2) HĐ đã hết hạn mà **chưa tạo** HĐ kế tiếp → tính từ Next Sign Date. NV đã nghỉ không tính.
  Cam ≤ 30, **đỏ ⚠ > 30**. Bộ lọc **Overdue > 30 Days** + 2 thẻ tóm tắt (tổng / trong đó HĐ 3 năm
  hoặc không thời hạn = nối tiếp HĐ xác định thời hạn). Cơ sở: BLLĐ 2019 Điều 20 khoản 2 — HĐ xác
  định thời hạn hết hạn mà NV vẫn làm, quá 30 ngày không ký HĐ mới thì thành HĐ không xác định thời
  hạn (`OVERDUE_LEGAL_DAYS`, `RENEWS_FIXED_TERM`). Logic ở `_add_signing_state()`.
- **Current Contract Only** = HĐ **mới nhất đã bắt đầu** của mỗi NV còn làm — tức HĐ đang hiệu lực,
  hoặc HĐ đã hết hạn mà không có HĐ nối tiếp (để ca quên tái ký vẫn hiện ở màn mặc định).

**Nút Export Contract Data** (chỉ HR Manager / HR User / System Manager — kiểm cả ở server): **1 sheet,
1 dòng / văn bản (HĐ + PL)**, đúng **88 cột** theo file theo dõi HĐ/PL của HR (bỏ cột "Đc cũ") —
tiêu đề chép nguyên văn (kể cả xuống dòng trong tên cột phụ cấp) vì Word mail merge bám theo tên cột.

| Cột | Cách lấy |
|---|---|
| Số PL/HĐ gần nhất · Mã hợp đồng · Thời gian HĐ (tháng) | HD → trống · HD1 → 1/1/12 · HD2 → 2/2/36 · HD3 → 3/3/trống · PL → YYMM, mã + thời gian của HĐ cha |
| Ngày ×3 dạng | ngày thật · `dd/mm/yyyy` ("use", "V", "TV") · `dd Month yyyy` ("E", "DOB use", "From use", "Issued") |
| F/M, Ông/bà, Mr/Ms, Giới tính, Gender | suy từ `gender` |
| At | 2 cơ quan cấp CCCD dịch cố định (`PLACE_OF_ISSUE_EN`), còn lại giữ nguyên |
| Address / Địa chỉ | `Employee.permanent_address` (tiếng Anh tự sinh) / `custom_permanent_address_full` |
| Position currently / Vị trí HT | HĐ: chức danh tại ngày bắt đầu · PL: ngày trước hiệu lực; tiếng Việt từ `Designation.custom_designation_vn` |
| New position / Vị trí mới | PL: chức danh tại ngày hiệu lực, chỉ khi khác |
| Kỳ lương | kỳ 26 → 25, đặt tên theo tháng kết thúc: hiệu lực từ ngày 26 → tháng sau (`PAYROLL_PERIOD_START_DAY`) |
| Thâm niên | `X năm Y tháng Z ngày` từ ngày vào làm tới ngày hiệu lực |
| Số HD tham chiếu + 3 cột ngày | HĐ cha của PL và ngày bắt đầu của nó |
| Lương (32 cột), Tình trạng thông tin, Đợt, Ngày pv | **để trống** (lương PENDING; 3 cột kia ERP không có) |

### 7.2. Labor Contract Timeline (mỗi NV 1 dòng)

HD · HD1 · HD2 · HD3 (từ – đến – trạng thái) · số PL / PL chưa ký · **Next Sign Date** (văn bản chưa
ký sớm nhất, hoặc giai đoạn kế tiếp nếu chưa tạo) · Next Document · Days Left. Lọc: Active Employees
Only (mặc định), Needs Signing (chỉ NV còn văn bản chưa ký, sắp theo ngày), Section, Group (hiện tại).

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

### 8.4b. Tạo tay HĐ kế tiếp phải bật cờ HĐ cha
`claim_predecessor()` (after_insert) bật `next_stage_created` trên HĐ kết thúc ngày liền trước —
thiếu nó, HR tạo tay HD1 thì job 00:00 vẫn tạo thêm `HD1-2`. Job + nút rà soát còn kiểm thêm
"đã có HĐ bắt đầu sau" cho trường hợp ngày bị sửa lệch.

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
├── labor_contract.py            # controller + toàn bộ API (HĐ, PL, job, positions_at)
├── labor_contract.json          # schema
├── labor_contract.js            # nhãn Effective Date cho PL + upload scan trên form
├── labor_contract_list.js       # 5 nút
├── test_labor_contract.py
└── labor_contract.md
customize_erpnext/customize_erpnext/doctype/labor_contract_settings/ # email thứ Hai
customize_erpnext/overrides/lms_file_storage/lms_file_storage.py     # scan -> private/files/labor_contract_scans/
customize_erpnext/customize_erpnext/report/labor_contract_report/     # + Export 88 cột
customize_erpnext/customize_erpnext/report/labor_contract_timeline/
customize_erpnext/overrides/employee_property/employee_{promotion,transfer}.py   # PL khi Submit/Cancel
customize_erpnext/public/js/custom_scripts/employee_property_update_override.js  # nút PL
customize_erpnext/patches/setup_labor_contract.py   # custom field + 5 Employment Type
```

hooks.py: `doc_events["Employee"]["after_insert"]` · `scheduler_events["cron"]["0 0 * * *"]` + `["0 8 * * 1"]` (email)
· fixtures Custom Field cho `Employment Type`, `Employee Promotion`, `Employee Transfer`
(`custom_create_contract_appendix`).

Chạy test (site có `allow_tests`, **không** chạy trên production — test tạo Employee):
`bench --site {site} run-tests --module customize_erpnext.customize_erpnext.doctype.labor_contract.test_labor_contract`

---

## 10. Roadmap — In hợp đồng ra PDF (chưa làm)

> ⚠ Đã thay bằng `.claude/plans/labor_contract_print_pdf.md` (22/10/2026: lưu 2 phương án A/B, tạm hoãn).

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

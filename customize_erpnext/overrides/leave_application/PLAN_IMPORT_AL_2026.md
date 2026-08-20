# Plan — Import dữ liệu nghỉ phép 2026 của HR (`AL_data.xlsx`)

> **Mục đích:** Kế hoạch nhập dữ liệu nghỉ phép 2026 từ file AL_data.xlsx mà HR đang dùng vào hệ thống.
> **Phạm vi:** Override HRMS/ERPNext
> **Trạng thái:** Kế hoạch · **Cập nhật:** 2026-08-12

> Nguồn: `AL_data.xlsx` — file quản lý nghỉ phép HR đang chạy **thủ công bằng Excel** để ghi nhận
> phép và tính lương. Đặt cùng thư mục này.
>
> 🔴 **Chạy SAU KHI xong** [`PLAN_LEAVE_OVERRIDE.md`](PLAN_LEAVE_OVERRIDE.md) — lý do định lượng ở
> mục 8, không phải chỉ cho gọn.
>
> Quy tắc nghiệp vụ: [`QUY_DINH_NGHI_PHEP_2025.md`](QUY_DINH_NGHI_PHEP_2025.md).
> **Trạng thái: ✅ ĐÃ IMPORT 10/08/2026 — 7.097 Leave Application, `status = Approved`,
> `docstatus = 0` (chưa submit).** Chưa sinh Attendance, chưa đụng sổ phép. Xem mục 12.

---

## 1. File có gì

Một sheet, **header 2 dòng** (dòng 1 = nhóm, dòng 2 = cột con), dữ liệu từ **dòng 3**.
**9.745** dòng có mã nhân viên, khoảng ngày **25/04/2025 → 25/08/2026**.

Mỗi dòng = **một nhân viên, một ngày**. Không có dòng nào trùng (nhân viên, ngày) — **0/9.745**.

| Cột | Nội dung | Dùng để |
|---|---|---|
| 1 `STT` | mã đơn nghỉ của HR (vd `26010189`) | **khoá gộp** — nhiều ngày cùng một đơn |
| 2 `Mã nhân viên` | `TIQN-xxxx` | `employee` |
| 5–29 | 25 cột đánh dấu loại nghỉ (đúng phân nhóm của quy định) | đối chiếu chéo với cột 32 |
| 30, 31 | hai cột ngày — **giống nhau 9.745/9.745** | `from_date` / `to_date` |
| **32 `Chấm công`** | **mã quy định** (`P` `P/2` `O` `KL` …) | **nguồn chính suy ra Leave Type** |
| 33 `Hưởng chế độ BH` | `SL` (2.726) / `0` (7.019) | cờ có hưởng BHXH |
| 34 `Ghi chú` | lý do bằng tiếng Việt | `description` |

Cột 32 **khớp trực tiếp** cột *"Thể hiện trên bảng công"* của quy định ⇒ dùng làm nguồn suy luận,
25 cột đánh dấu chỉ dùng để **kiểm chéo**.

## 2. Phân loại 9.745 dòng

| Loại | Số dòng | Xử lý |
|---|---:|---|
| **Nghỉ phép** — mã ∈ quy định | **9.390** | → Leave Application |
| **Đi trễ / Về sớm** — mã là **số** (`0.9` `0.8` `0.5` …) | **355** | ❌ **không** phải đơn nghỉ — xem mục 4.2 |

Phân bố mã nghỉ phép:

| Mã | Dòng | Mã | Dòng | Mã | Dòng |
|---|---:|---|---:|---|---:|
| `P` | 3.627 | `TS` | 383 | `O/2` | 14 |
| `O` | 1.864 | `DS` | 156 | `CO/2` | 3 |
| **`P/2`** | **1.723** | `HS` | 48 | `HL/2` | 2 |
| `KL` | 1.024 | `NB` | 45 | `HL` | 1 |
| `CO` | 477 | `MC` | 23 | | |

### 🔴 Phát hiện: dual leave KHÔNG TỒN TẠI trong 16 tháng dữ liệu thật

9 cột dành cho nghỉ ghép của quy định **rỗng hoàn toàn**:
`Ốm-Đi trễ/Sớm` · `Ốm-Phép năm` · `Ốm-KL` · `Ốm-Con ốm` · `Con ốm-Đi trễ/Sớm` · `Con ốm-Phép năm` ·
`Con ốm-KL` · `TrừLương/Ốm`.

⇒ **0/9.745** dòng cần `OP/2` `COP/2` `OCO/2` `OK/2` `COK/2` `OL/2` `COL/2`.
Chỉ có `O/2` (14) và `CO/2` (3) — nửa ngày BHXH + nửa còn lại **đi làm**, một đơn duy nhất.

Hệ quả cho [`PLAN_LEAVE_OVERRIDE.md`](PLAN_LEAVE_OVERRIDE.md): **vấn đề 7 (dual leave) đúng là
tiềm ẩn** — không chỉ DB ERP trống, mà cả sổ tay HR 16 tháng cũng chưa từng phát sinh. Vẫn phải
sửa (nó sai tới 1 ngày lương và không tất định), nhưng **không chặn** việc import.

Ngược lại `P/2` **1.723 dòng** là nhóm nửa ngày lớn nhất — và đúng là ca code đang sai.

## 3. Đối chiếu file HR ↔ ERP

> ⚠ HR chạy Excel thủ công, tách rời ERP. File này là **nguồn dữ liệu duy nhất** về nghỉ phép,
> **không phải** thước đo đúng/sai của ERP — giống hệt kết luận đã ghi cho `Salary.xlsx`
> (`payroll_docs/PAYROLL_SETUP.md` mục 6.2).

| Kiểm | Kết quả |
|---|---|
| Mã nhân viên không có trong ERP | **0** ✅ |
| Trạng thái nhân viên | 929 `Active` + **275 `Left`** |
| Leave Period | `HR-LPR-2026-00001` = **26/12/2025 → 25/12/2026** — trùng khít kỳ lương ✅ |
| Dòng ngoài Leave Period | **1** (25/04/2025) |
| Dòng ngoài khoảng làm việc (HRMS chặn) | **1** — `TIQN-1414` nghỉ 04/08/2026, đã thôi việc 01/08/2026 |
| `include_holiday` | chỉ `TS` = 1, còn lại 0 → đoạn nhiều ngày nhảy qua Chủ Nhật hoạt động đúng ✅ |

### Quota phép năm — lệch theo từng người, nhưng KHÔNG chặn

| | Ngày | Nhân viên |
|---|---:|---:|
| File HR **đã dùng** | 4.488,5 | 1.070 |
| ERP **đã cấp** (Leave Allocation) | 6.433,0 | 931 |

Tổng thì ERP cấp nhiều hơn, nhưng **theo từng người thì lệch**:

- **268/1.070 nhân viên dùng vượt quota ERP**, tổng vượt **450,5 ngày**
- **177 nhân viên** có nghỉ phép trong file mà ERP **chưa cấp ngày nào**

✅ **Không chặn gì cả — và đó là đúng nghiệp vụ.** Phép năm vẫn **14 ngày/năm** theo quy định,
nhưng **công ty cho phép ứng trước**, và ERP đã khai đúng điều đó:

| `Leave Type` = Phép năm | |
|---|---|
| `allow_negative` | **1** |
| `allow_over_allocation` | **1** |
| `is_earned_leave` · `earned_leave_frequency` | 1 · **Monthly** |
| `max_leaves_allowed` | **14** |
| `is_carry_forward` | 1 |

`allow_negative = 1` làm `validate_dates_across_allocation()` (`leave_application.py:208`) return
ngay, và thiếu số dư chỉ còn là **cảnh báo** `msgprint` (`leave_application.py:439`), không `throw`.

Phép năm **tích luỹ theo tháng** (14/12 ≈ 1,17 ngày/tháng) nên giữa năm đã dùng hết 14 ngày là
**bình thường** — đó chính là ứng trước. Số dư âm là kết quả **đúng**, không phải lỗi dữ liệu.

## 4. Việc cần chốt trước khi code

### 4.1. ✅ Quota phép năm — không còn là quyết định

Xem mục 3: `allow_negative = 1`, phép năm là earned leave theo tháng, công ty cho phép ứng trước.
**Không cấp bù Leave Allocation cho khớp mức đã dùng, không bỏ qua validate.** Cứ import; số dư âm
là đúng.

⚠ Việc còn lại là **177 nhân viên ERP chưa cấp ngày phép nào**. ERP có 931 `Leave Policy Assignment`
trên 1.204 nhân viên trong file ⇒ thiếu assignment thì `is_earned_leave` **không có gì để tích luỹ
lên**, và số dư sẽ âm **toàn bộ** thay vì âm đúng phần ứng trước. Đây là **cấp allocation còn
thiếu** — khác hẳn việc cấp bù cho khớp con số HR đã dùng.

### 4.2. 355 dòng Đi trễ / Về sớm — không phải đơn nghỉ

Mã là **ngày công phân số** (`0.9` `0.8` `0.5` `0.4` …) = `1 − giờ nghỉ/8` của quy định.
`Attendance.status` không biểu diễn được (chỉ `1 / 0,5 / 0`) — đúng **vấn đề 8** của plan override.

**Đề xuất:** không nhồi vào Leave Application. Xuất riêng thành CSV để không mất dữ liệu, chờ chốt
cách tính thưởng chuyên cần (`payroll_docs/PLAN_ATTENDANCE_VS_QUYCHE.md` mục A4 + S5).

⚠ Trong 355 dòng này có **rác rõ ràng**: 36 dòng giá trị `1.25e-06`, 30 dòng `0.0001` → cột 32 ra
`1` (nghĩa là tính đủ công). Phải hỏi HR, đừng tự suy.

## 5. Gộp thành Leave Application — HR ghi 3 ngày = 3 dòng, ERP là 1 phiếu

Đây là khác biệt cấu trúc lớn nhất giữa hai bên. Không thể 1 đơn / 1 dòng, cũng không thể
1 đơn / 1 STT:

| Cách | Số đơn | Vấn đề |
|---|---:|---|
| A — 1 đơn mỗi dòng | 9.390 | mất cấu trúc đơn của HR; và **rơi vào ngày nghỉ thì HRMS từ chối** (xem 5.3) |
| B — gộp `(STT, nhân viên)` | 6.797 | ❌ **99 nhóm trộn nhiều mã**; ❌ **27 nhóm nhiều ngày lẫn nửa ngày** mà HRMS chỉ cho **một** `half_day_date`/đơn |
| **C — `(STT, nhân viên, mã)` → đoạn ngày liên tục; nửa ngày đứng riêng** | **6.921** | ✅ giữ được đơn của HR, hợp ràng buộc HRMS |

**Chọn C.** Đã mô phỏng trên dữ liệu thật: **9.390 dòng → 6.921 đơn** (giảm 2.469 phiếu),
trong đó **884 đơn nhiều ngày**, dài nhất **33 ngày**.

```
1. Bỏ 355 dòng đi trễ/về sớm.
2. Nhóm theo (STT, employee, mã).
3. Mã kết thúc "/2"  -> mỗi dòng = 1 đơn 1 ngày, half_day=1, half_day_date = ngày đó.
4. Mã trọn ngày      -> cắt thành đoạn ngày liên tục; ĐƯỢC nhảy qua ngày trong Holiday List
                        (gồm Chủ Nhật); khoảng trống là ngày làm việc -> cắt đơn mới.
5. Giữ STT vào description để truy ngược file HR.
```

### 5.1. Vì sao gộp không làm sai số ngày phép

`get_number_of_leave_days()` (`leave_application.py:904`) tính `date_diff + 1` rồi **trừ số ngày
nghỉ** khi `Leave Type.include_holiday = 0`. Nên một đơn 26/12 → 29/12 có Chủ Nhật 28/12 ở giữa
vẫn ra đúng **3** ngày.

Hai điều đã kiểm để chắc chắn dùng được:

- **Holiday List đồng nhất toàn công ty:** 7 `Holiday List Assignment` cấp Company theo từng năm,
  và **0 nhân viên** tự đặt `Employee.holiday_list`. Không có chuyện mỗi người một lịch nghỉ.
- **Đơn vắt qua hai năm vẫn đúng:** `get_holiday_dates_between_range()`
  (`hrms/utils/holiday_list.py:35`) tự tách tại `to_holiday_list.from_date` khi hai đầu range
  thuộc hai list khác nhau. Quan trọng vì kỳ lương TIQN vắt qua **26/12**.

### 5.2. 🔴 Guard bắt buộc: 30 đơn gộp ra SAI số ngày

Mô phỏng cho thấy **30/6.921** đơn có số ngày HRMS tính ≠ số dòng HR:

| Loại | Vì sao |
|---|---|
| `TS` (thai sản) — 81 đơn nhiều ngày | `include_holiday = **1**` ⇒ HRMS đếm **mọi ngày lịch**, kể cả Chủ Nhật; HR chỉ ghi ngày làm việc thành dòng. VD `TIQN-0381` HR 6 dòng, gộp 09/02→25/02 ra **17** ngày |
| `DS` (dưỡng sức) | HR ghi **nhiều dòng hơn** HRMS đếm — tức HR tính cả ngày nghỉ là ngày DS. VD `TIQN-0242` 29/12→04/01 HR 7 dòng, HRMS **5** |

**Quy tắc chốt:** chỉ gộp khi số ngày HRMS tính ra **bằng đúng** số dòng nguồn; ngược lại
**tách về 1 đơn / 1 dòng**. Như vậy sổ phép luôn khớp file HR, không phụ thuộc `include_holiday`.

⚠ Riêng `TS` cần HR xác nhận: nghỉ thai sản theo luật là **liên tục 6 tháng**, nên đếm cả Chủ Nhật
mới đúng luật — nhưng khác cách HR ghi sổ. `TS` là `is_lwp = 1` (0 ngày công) nên **không ảnh
hưởng tiền lương**, chỉ lệch sổ phép.

### 5.3. 18 dòng rơi vào ngày trong Holiday List

| Mã | Chủ Nhật | Ngày lễ | Hệ quả |
|---|---:|---:|---|
| `DS` | 13 | 2 | 🔴 `include_holiday = 0` ⇒ đơn 1 ngày ra **0 ngày** → HRMS `throw` *"…are holidays. You need not apply for leave."* |
| `KL` | 2 | – | 🔴 như trên |
| `TS` | – | 1 | ✅ `include_holiday = 1` nên vẫn vào được |

⇒ **17 dòng không tạo được Leave Application.** Không được im lặng bỏ qua — đưa vào danh sách
bất thường mục 9 để HR xác nhận (nhiều khả năng là nghỉ dưỡng sức kéo dài vắt qua Chủ Nhật).

### 5.4. Ánh xạ mã → Leave Type

Bảng ở `QUY_DINH_NGHI_PHEP_2025.md` mục 5.1. `Nghỉ trừ phép/Ốm` và `Nghỉ trừ phép/Con ốm`
(11 dòng) HR ghi mã `P` / `P/2` — **nghỉ ốm nhưng trừ vào quota phép năm** ⇒ Leave Type =
**Phép năm**, không phải Ốm. Ghi lý do vào `description`.

### 5.5. `P/2` — nửa còn lại đã đi làm

HR ghi mã `P/2` nghĩa là **nửa còn lại có đi làm** (quy định: tính công 1 ngày). ERP suy ra
`half_day_status` từ checkin, và **1.709/1.723** dòng đã có checkin nên tự ra `Present` đúng.
14 dòng còn lại ERP có Attendance nhưng 0 giờ ⇒ sẽ ra `Absent`. Import tool phải **báo cáo** 14
dòng này chứ không tự ghi đè theo file HR — xem mục 8.

## 6. Điều kiện tiên quyết

| | Trạng thái |
|---|---|
| **Email**: `Email Account` = **0 bản ghi**, `HR Settings.send_leave_notification = 0`, không có Email Template | ✅ **an toàn 3 lớp** — không có đường nào bắn mail |
| `notify_approval_status()` (`hrms/mixins/pwa_notifications.py:10`) **không bị chặn** bởi `send_leave_notification` | ⚠ sẽ sinh ~9.390 bản **PWA Notification** (in-app, không phải email). Chỉ 108/2.401 nhân viên có `user_id` ⇒ phần lớn là bản ghi rỗng `to_user`. **Chặn bằng `flags`**, đừng để rác |
| `site_config.developer_mode` | ⚠ phải **tắt** — bật thì Data Import chạy inline và treo (`data_import.py:123`) |
| Leave Allocation cho phép năm | ✅ `allow_negative` đã bật — không chặn. Còn 177 NV thiếu allocation, xem mục 4.1 |

## 7. Quy trình import

Không dùng Data Import (9.390 dòng + cần gộp + cần suy luận). Viết tool riêng:
`overrides/payroll/import_leave.py` — tái dụng khung của `import_ssa.py`.

1. **Dry-run bắt buộc** — bảng xem trước: bao nhiêu đơn / loại nghỉ, ai bị chặn vì quota, ai ngoài
   khoảng làm việc, dòng nào mã lệch cột đánh dấu. HR duyệt rồi mới chạy thật.
2. **Background job** (`frappe.enqueue`, queue `long`), commit theo lô, `publish_realtime` khi xong.
   ❌ Không `frappe.db.commit()` trong hàm `@frappe.whitelist()` — đã có sự cố rò 59 Employee giả.
3. Insert + **submit** LA (submittable). Idempotent: bỏ qua nếu đã có LA trùng
   (nhân viên, loại nghỉ, khoảng ngày).
4. Sau import: chạy lại `bulk_update_attendance_optimized` cho toàn khoảng để engine sinh
   Attendance khớp — **engine luôn ghi sau cùng**, đây là bước bắt buộc, không phải tuỳ chọn.

## 8. Vì sao xong plan override trước — đã đo lại

Bản plan đầu ước tính mất *"~861 ngày lương"* nếu import trước khi sửa. **Sai hai bậc độ lớn** —
ước tính đó giả định ERP không có dữ liệu checkin cho các ngày `P/2`. Đo thật:

| 1.723 dòng `P/2` | Số dòng | `half_day_status` sẽ ra |
|---|---:|---|
| ERP có Attendance, `working_hours > 0` | **1.709** | `Present` ✅ đúng |
| ERP có Attendance nhưng 0 giờ | 14 | `Absent` → mất 0,5 ngày |
| ERP không có Attendance ngày đó | 0 | – |

⇒ Thiệt hại thực tế nếu import trước khi sửa: **14 dòng ≈ 7 ngày lương**, không phải 861.

Thứ tự "override trước, import sau" **vẫn giữ**, nhưng lý do đúng là **tính đúng đắn**, không phải
quy mô tiền:

- Trước khi sửa, `half_day_status` do ba nơi quyết định theo ba kiểu khác nhau ⇒ mỗi FULL run của
  engine lại ghi đè kết quả của luồng Leave Application. Import vào giữa tình trạng đó thì
  **không kiểm chứng được gì** — chạy lại hai lần ra hai kết quả.
- Dual leave ghi `On Leave` trọn ngày và phụ thuộc thứ tự query. File HR **không có** dòng dual
  leave nào, nên rủi ro này không kích hoạt lúc import — nhưng cũng vì thế mà **sẽ không ai phát
  hiện** cho tới khi đơn dual leave thật đầu tiên xuất hiện.

> ✅ Các sửa đổi này **đã xong** (10/08/2026) — xem `PLAN_LEAVE_OVERRIDE.md` mục 4.
> 14 dòng `P/2` có Attendance 0 giờ vẫn cần HR xác nhận: hôm đó thực sự có đi làm nửa buổi không?
> Nếu có thì đó là lỗ hổng dữ liệu checkin, không phải lỗi quy tắc.

## 9. Dữ liệu bất thường — cần HR xác nhận

| # | Hiện tượng | Số dòng |
|---|---|---:|
| 1 | Không đánh dấu cột loại nghỉ nào | 33 |
| 2 | Cột 32 = `0` (không tính công mà không rõ loại) | 37 |
| 3 | Đi trễ/Về sớm giá trị `1.25e-06` / `0.0001` → mã `1` | 66 |
| 4 | Mã lệch cột đánh dấu: `Ốm 1 ngày` → mã `P/2`; `Con ốm 1 ngày` → mã `KL`; `TrừLương/Khác` → mã `0.2`; `TrừPhép/Khác` → mã `0.6` | 4 |
| 5 | Nghỉ sau ngày thôi việc — `TIQN-1414`, 04/08/2026 | 1 |
| 6 | Ngoài Leave Period — 25/04/2025 | 1 |

Tổng ~142 dòng (1,5%). **Không tự đoán** — xuất Excel cho HR rà, kèm hậu tố `YYMMDD HHMMSS`
theo quy ước.

## 10. Nghiệm thu

- Số LA tạo ra khớp dry-run; **0** đơn ở trạng thái khác `Approved` + `docstatus = 1`
- Tổng ngày nghỉ theo từng loại **khớp** file HR (ngưỡng **0,01** — không dùng `> 1`, ngưỡng lỏng
  từng che mất chênh lệch 0,5 ngày)
- Với mỗi mã của quy định, lấy mẫu 1 nhân viên → `payment_days` của Salary Slip đúng cột
  *"Thời gian tính công"*. `P/2` phải ra **1**, `O/2` ra **0,5**
- Sổ phép: `Leave Ledger Entry` khớp số ngày đã dùng. **Số dư âm là hợp lệ** (ứng trước) — chỉ
  kiểm không ai âm quá phần chưa tích luỹ
- Chạy `bulk_update_attendance_optimized` **hai lần liên tiếp** — lần hai phải **0 thay đổi**
  (chứng minh LA hook và engine đã đồng thuận, hết churn)

## 11. Việc KHÔNG làm

- **Không** bật gửi email / tạo Notification cho luồng nghỉ phép — Admin tự chọn người nhận
- **Không** coi file HR là thước đo đúng/sai của ERP; nó là **nguồn dữ liệu**
- **Không** tự sửa 142 dòng bất thường — chờ HR
- **Không** import 355 dòng đi trễ/về sớm thành Leave Application
- **Không** import trước khi xong plan override (mục 8)


---

## 12. Kết quả import 10/08/2026

Tool: [`import_leave.py`](import_leave.py).

```bash
bench --site erp.tiqn.local execute \
  customize_erpnext.overrides.leave_application.import_leave.run --kwargs "{'dry_run': 1}"   # xem trước
bench --site erp.tiqn.local execute \
  customize_erpnext.overrides.leave_application.import_leave.run --kwargs "{'dry_run': 0}"   # tạo draft
bench --site erp.tiqn.local execute \
  customize_erpnext.overrides.leave_application.import_leave.verify                          # đối chiếu
```

| | |
|---|---:|
| Dòng đọc được | 9.745 |
| Dòng không phải nghỉ phép (đi trễ/về sớm + rác) | 355 |
| **Leave Application tạo được (draft)** | **7.097** |
| trong đó nhiều ngày | 861 |
| Lỗi | **2** |

### 12.1. Hai lần chạy

Lần 1 tạo 7.100, **45 lỗi**. Chẩn đoán rồi sửa cấu hình Leave Type
(`QUY_DINH_NGHI_PHEP_2025.md` mục 5.1), xoá sạch và chạy lại:

| Lỗi lần 1 | Nguyên nhân | Xử lý | Còn lại |
|---|---|---|---:|
| 28 × *Application period cannot be outside leave allocation period* | `HS`/`MC`/`HL` là nghỉ **phát sinh**, không có quota năm nên không có Leave Allocation; mà `allow_negative = 0` | đặt `allow_negative = 1` | **0** ✅ |
| 15 × *…are holidays* (`DS`) | Dưỡng sức rơi vào Chủ Nhật/lễ; `include_holiday = 0` ⇒ HRMS tính 0 ngày | đặt `include_holiday = 1` (đúng Luật BHXH) | **0** ✅ |
| 2 × *…are holidays* (`KL`) | Nghỉ không lương rơi vào Chủ Nhật | **chấp nhận** — `KL` đã là 0 ngày công, không ảnh hưởng lương | 2 |

### 12.2. Đối chiếu số ngày với file HR

| Mã | HR (ngày) | ERP draft | Lệch |
|---|---:|---:|---:|
| `P` | 4.488,5 | 4.488,5 | **0** ✅ |
| `O` | 1.871,0 | 1.871,0 | **0** ✅ |
| `KL` | 1.024,0 | 1.022,0 | −2 *(chấp nhận)* |
| `CO` | 478,5 | 478,5 | **0** ✅ |
| `TS` | 383,0 | 383,0 | **0** ✅ |
| `DS` | 156,0 | 156,0 | **0** ✅ |
| `HS` | 48,0 | 48,0 | **0** ✅ |
| `NB` | 45,0 | 45,0 | **0** ✅ |
| `MC` | 23,0 | 23,0 | **0** ✅ |
| `HL` | 2,0 | 2,0 | **0** ✅ |
| **TỔNG** | **8.519,0** | **8.517,0** | **−2** |

**9/10 mã khớp tuyệt đối.** Toàn bộ chênh lệch là 2 dòng `KL` đã chấp nhận bỏ.

### 12.3. Kiểm chứng — không có tác dụng phụ

| Kiểm | Kết quả |
|---|---|
| `docstatus` | **7.097 / 7.097 = 0 (draft)**; submit: 0; cancel: 0 ✅ |
| Attendance trỏ tới Leave Application | **0** ✅ |
| `Leave Ledger Entry` từ Leave Application | **0** ✅ |
| PWA Notification | **0** ✅ — nhờ đặt `status = "Open"` thay vì `"Approved"` |
| Email | **0** — không có `Email Account` nào, `send_leave_notification = 0`, `Enable Outgoing = 0` ✅ |
| Engine có thấy draft không | **Không** — engine lọc `status = 'Approved' AND docstatus = 1` ✅ |

### 12.4. ⚠ Sự cố khi dọn dữ liệu — đã ghi nhận

Lúc xoá draft lần 1 bằng `frappe.delete_doc()`, **một** Leave Application **không thuộc import**
bị xoá kèm: `HR-LAP-2026-02878` (TIQN-0148, *"Nghỉ bù OT chủ nhật"*, 25/07/2026). Bản ghi đó
**đã ở trạng thái Cancelled** (`docstatus = 2`) từ trước nên không phải dữ liệu sống.
Khôi phục được từ `Deleted Document` tên `aopntsqrdj`.

Hai bài học cho lần sau:

- `frappe.delete_doc()` **enqueue một background job mỗi bản ghi** (`delete_dynamic_links`) →
  tràn queue ở ~1.000 bản (*"Too many queued background jobs (550)"*). Với hàng nghìn draft
  phải xoá bằng SQL trực tiếp.
- Xoá hàng loạt phải kiểm **trước và sau** bằng đếm tổng, không chỉ đếm số bản ghi khớp bộ lọc.

### 12.5. Bước tiếp theo

1. HR rà 7.097 draft trên UI
2. Xác nhận 2 dòng `KL` rơi vào Chủ Nhật (`TIQN-1018` 17/05, `TIQN-1641` 10/05)
3. `submit_imported()` — 🔴 submit **sinh Attendance + ghi sổ phép**, rollback không lấy lại được
4. Chạy `bulk_update_attendance_optimized` cho toàn khoảng ngày
5. Chạy lần hai → phải **0 thay đổi**


---

## 13. Trạng thái cuối ngày 10/08/2026

| | |
|---|---|
| Leave Application | **7.097** · `Approved` · `docstatus = 0` |
| `follow_via_email` | **0** trên toàn bộ — chặn `frappe.sendmail()` ở `leave_application.py:709` |
| Leave Allocation | đã **xoá sạch** rồi HR tự assign lại; đang ~1.490 bản |
| Leave Policy · Leave Period | giữ nguyên (`HR-LPOL-2026-00001` · 26/12/2025 → 25/12/2026) |
| Salary Slip | 4 bản của `TIQN-0148` (kỳ 04–07/2026), draft trừ 202607 đã submit |

### Đổi trạng thái hàng loạt — dùng SQL, KHÔNG dùng `doc.save()`

`on_update` gọi `notify_approval_status()` (`hrms/mixins/pwa_notifications.py:10`) — hàm này chạy
khi status đổi sang `Approved`/`Rejected` và **không** bị `HR Settings.send_leave_notification`
chặn. `save()` 7.096 bản sẽ đẻ ngần ấy PWA Notification rác. Đã đổi bằng một câu `UPDATE`;
kiểm sau đó: PWA Notification, Leave Ledger Entry, Attendance đều **không đổi**.

Đánh đổi: `validate()` không chạy nên `leave_balance` trên draft là số cũ — sẽ tự tính lại khi submit.

### Xoá hàng loạt — `delete_doc()` tràn queue

`frappe.delete_doc()` enqueue **một background job mỗi bản ghi** (`delete_dynamic_links`) → chết ở
~1.000 bản với *"Too many queued background jobs (550)"*. Với hàng nghìn bản phải xoá bằng SQL,
và **kiểm tổng số trước/sau**, không chỉ đếm bản ghi khớp bộ lọc — lần trước một Leave Application
ngoài phạm vi đã bị xoá kèm (đã khôi phục được từ `Deleted Document`).

### 🔴 Chưa làm — bước tiếp theo

1. **`bench restart`** — 4 thay đổi code đang chờ, xem `PLAN_LEAVE_OVERRIDE.md` mục 4e
2. HR rà 7.097 draft trên UI
3. Xác nhận 2 dòng `KL` rơi vào Chủ Nhật (`TIQN-1018` 17/05, `TIQN-1641` 10/05)
4. `submit_imported()` — 🔴 sinh Attendance + ghi sổ phép, **rollback không lấy lại được**
5. Chạy `bulk_update_attendance_optimized` toàn khoảng, rồi chạy **lần hai** → phải **0 thay đổi**
6. Dịch `vi.csv` · commit

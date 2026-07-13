# Timesheet Algorithm — `timesheetFunctions.dart`

> Tài liệu này mô tả toàn bộ thuật toán tính timesheet theo code hiện tại.  
> Cập nhật: 2026-06-29

---

## 1. Tổng quan

Hàm chính: `TimesheetFunctions.createTimesheets()`

**Đầu vào:**
| Tham số | Kiểu | Mô tả |
|---|---|---|
| `employees` | `List<Employee>` | Danh sách nhân viên |
| `attLogs` | `List<AttLog>` | Bản ghi chấm công |
| `shiftRegisters` | `List<ShiftRegister>` | Đăng ký ca làm việc |
| `otRegisters` | `List<OtRegister>` | Đăng ký OT |
| `dateRange` | `List<DateTime>` | `[fromDate, toDate]` |

**Đầu ra:** `TimesheetResult`
- `data`: `List<TimeSheetDate>` — một record cho mỗi cặp (nhân viên × ngày)
- `anomalies`: `List<String>` — danh sách cảnh báo bất thường

**Model `TimeSheetDate`:**
| Field | Kiểu | Mô tả |
|---|---|---|
| `date` | `DateTime` | Ngày |
| `empId` | `String` | Mã nhân viên |
| `attFingerId` | `int` | Finger ID |
| `name` | `String` | Tên |
| `department`, `section`, `group` | `String` | Phân bổ tổ chức |
| `shift` | `String` | Ca làm việc |
| `firstIn`, `lastOut` | `DateTime?` | Giờ vào / ra |
| `normalHours` | `double` | Giờ làm bình thường (đã làm tròn 2 chữ số) |
| `normalDays` | `double` | Số công = normalHours / 8 (đã làm tròn 2 chữ số) |
| `otHours` | `double` | OT thực tế (đã làm tròn 1 chữ số) |
| `otHoursApproved` | `double` | OT được duyệt (đã làm tròn 1 chữ số) |
| `otHoursFinal` | `double` | OT cuối = min(otActual, otApproved) (đã làm tròn 1 chữ số) |
| `attNote2` | `String` | Ghi chú chấm công, cảnh báo, chế độ |
| `attNote3` | `String` | Ghi chú Chủ nhật |

---

## 2. Ca làm việc — Tham số & Nguồn dữ liệu

### 2.1 Load từ DB (`colShift`)

Shift params được load từ MongoDB collection `colShift`, model `ShiftParam`:

| Field DB | Ý nghĩa |
|---|---|
| `shift` | Tên ca (e.g. `'Day'`, `'Canteen'`, `'Canteen_new'`, `'Shift 1'`, `'Shift 2'`) |
| `begin` | Giờ bắt đầu `'HH:mm'` |
| `end` | Giờ kết thúc `'HH:mm'` |
| `restHour` | Số giờ nghỉ trưa (thường 0 hoặc 1) |
| `effectiveFrom` | Ngày hiệu lực từ (default 2022-01-01) |
| `effectiveTo` | Ngày hiệu lực đến (default 2099-12-31) |

**Lookup:** `_getShiftParam(shiftName, date)` — tìm record khớp tên ca VÀ `date` trong khoảng `[effectiveFrom, effectiveTo]`. Nếu không tìm thấy, dùng fallback mặc định bên dưới.

**Fallback mặc định (khi DB không có record):**
| Ca | Bắt đầu | Kết thúc | restHour |
|---|---|---|---|
| `Day` | 08:00 | 17:00 | 1 |
| `Canteen` | 07:00 | 16:00 | 1 |
| `Shift 1` | 06:00 | 14:00 | 0 |
| `Shift 2` | 14:00 | 22:00 | 0 |

### 2.2 Resolve ca theo nhóm — `_resolveGroupShift(keyword, date)`

Dùng cho nhân viên nhóm **Canteen**: tìm record DB có `name.contains(keyword)` và `date` trong khoảng hiệu lực. Trả về tên ca đó (e.g. `'Canteen_new'`). Fallback về `keyword` nếu không tìm thấy.

> Ví dụ: từ 2026-06-22, ca `'Canteen'` đổi tên thành `'Canteen_new'` với khung giờ mới. `_resolveGroupShift('Canteen', date)` tự động trả về `'Canteen_new'` cho ngày đó.

### 2.3 Cửa sổ nghỉ giữa ca (restBegin / restEnd)

```
Weekdays:  restBegin = shiftBegin + 4h
           restEnd   = restBegin + restHour

Sunday:    restBegin = 12:00  (cố định, bất kể giờ OT register)
           restEnd   = 13:00
```

---

## 2b. Cài đặt Timesheet (`TimesheetSettings`)

Lưu trong DB (`colTimesheetSettings`), load vào `App.gValue.timesheetSettings`:

| Setting | Field | Default | Mô tả |
|---|---|---|---|
| **Min OT Minute** | `minOtMinute` | 30 | Ngưỡng tối thiểu (phút) để tính OT |
| **OT Block Minute** | `otBlockMinute` | 30 | Block làm tròn OT. VD: 45' → 30', 89' → 60' |
| **Working Block Minute** | `workingBlockMinute` | 1 | Block làm tròn giờ làm. Mặc định 1 = không làm tròn |
| **Allow OT In Rest Time** | `allowOtInRestTime` | false | Cho phép tính OT giờ nghỉ trưa |
| **Exclude Emp IDs** | `excludeEmpIds` | `[]` | Danh sách mã NV bị loại khỏi tính timesheet |

**`_floorToBlock(hours)`:**
```
totalMin = floor(hours × 60)
if totalMin < minOtMinute → return 0
return floor(totalMin / otBlockMinute) × otBlockMinute / 60
```

**`_floorWorkingToBlock(hours)`:**
```
if workingBlockMinute <= 1 → return hours   ← không làm tròn
totalMin = floor(hours × 60)
return floor(totalMin / workingBlockMinute) × workingBlockMinute / 60
```

---

## 3. Pre-indexing & Vòng lặp chính

### 3.1 Pre-index dữ liệu (O(1) lookup)

```
// AttLogs → Map<dayKey, Map<empId, List<AttLog>>>
logIndex[dk][empId].add(log)

// ShiftRegisters → Map<dayKey, Map<shiftName, Set<empId>>>
for d in [sr.fromDate .. sr.toDate]:
    shiftIndex[dk][sr.shift].add(sr.empId)

// OtRegisters → Map<dayKey, Map<empId, List<OtRegister>>>
otIndex[dk][empId].add(ot)
```

### 3.2 Lọc nhân viên trước vòng lặp

```
// Loại NV đã nghỉ việc mà không có ngày nghỉ hợp lệ
employees.removeWhere: workStatus.contains('Resigned') AND resignOn == null OR resignOn.year >= 2099

// Loại NV theo danh sách exclude
employees.removeWhere: empId in excludeEmpIds
```

### 3.3 Vòng lặp chính

```
for date in [fromDate .. toDate]:
    dayLogMap = logIndex[dayKey]
    if dayLogMap is empty → skip date (ngày không ai chấm công)

    for employee in employees:
        bỏ qua nếu date < employee.joiningDate
        bỏ qua nếu Resigned + không có log + date >= resignOn
        → tính record TimeSheetDate
```

---

## 4. Xác định ca làm việc

Thứ tự ưu tiên (sau cùng thắng):

1. Mặc định: `'Day'`
2. Nếu `employee.group == 'Canteen'` → `_resolveGroupShift('Canteen', date)` (có thể ra `'Canteen_new'` v.v.)
3. Nếu `empId` có trong `shift1Ids` → `'Shift 1'`
4. Nếu `empId` có trong `shift2Ids` → `'Shift 2'`
5. Nếu là **Chủ nhật** → luôn về `'Day'` (dùng làm base params)

> Shift 1/2 register ghi đè Canteen. Chủ nhật luôn lấy params ca Day làm cơ sở (nhưng giờ thực tế được override bởi OT register nếu có).

**Chủ nhật — override giờ từ OT register:**

Nếu nhân viên có OT register vào Chủ nhật, `shiftBegin`/`shiftEnd` được lấy từ `otTimeBegin`/`otTimeEnd` của record có **`id` lớn nhất** (nhất quán với logic dedup OT). Nếu không có OT register → giữ nguyên Day 08:00-17:00.

---

## 5. Nhân viên mang thai / nuôi con nhỏ

Chế độ được xác định **theo ngày làm việc** (không dùng `workStatus`).

| Giai đoạn | Điều kiện ngày | Flag |
|---|---|---|
| Mang thai (đi làm) | `maternityBegin ≤ date < (maternityLeaveBegin ?? maternityEnd)` | `isPregnant = true` |
| Đang nghỉ thai sản | `maternityLeaveBegin ≤ date < maternityLeaveEnd` | *(không đi làm — không tính)* |
| Nuôi con nhỏ (đi làm lại) | `maternityLeaveEnd ≤ date ≤ maternityEnd` | `isYoungChild = true` |

> `isYoungChild` chỉ true khi `isPregnant = false`. Hai chế độ loại trừ nhau.
>
> Default các field maternity là `2099-12-31` hoặc null → coi như "chưa set".  
> Nếu chỉ có `maternityBegin` + `maternityEnd` (không có `maternityLeaveBegin`) → toàn bộ khoảng [Begin, End) là `isPregnant` (TH sẩy thai: tiếp tục đi làm đến maternityEnd).

**Thay đổi khi `isPregnant OR isYoungChild`:**

| Thay đổi | Giá trị |
|---|---|
| `shiftEnd` | Giảm 1 giờ so với ca gốc (`reducedShiftEnd`) |
| Tính buổi chiều | Dùng `_youngChildAfternoon` (xem mục 6.3) |
| So sánh Vào trễ / Ra sớm / Ra trễ ≥1h | Dùng `shiftEnd` **đã điều chỉnh** |

---

## 6. Tính giờ làm bình thường (normalHours)

### 6.1 Cấu trúc thời gian ca

```
shiftBegin ──── restBegin ──── restEnd ──── shiftEnd (reducedShiftEnd nếu có regime)
     |           (begin+4h)    (rest+Nh)       |
     |←─ Buổi sáng ──→|←── Nghỉ ──→|←─ Buổi chiều ──→|
```

### 6.2 Điều kiện tính

- Buổi sáng chỉ tính nếu `firstIn <= restBegin`
- Buổi chiều (bình thường): chỉ tính nếu `lastOut >= restEnd`
- Buổi chiều (regime): tính theo `_youngChildAfternoon` — không có điều kiện restEnd

### 6.3 Công thức

**Buổi sáng:**
```
start   = max(firstIn, shiftBegin)
end     = min(lastOut, restBegin)
morning = clamp(end − start, 0, ∞)
```

**Buổi chiều — nhân viên bình thường:**
```
start     = max(firstIn, restEnd)
end       = min(lastOut, shiftEnd)
afternoon = clamp(end − start, 0, ∞)
```

**Buổi chiều — mang thai / nuôi con nhỏ** (`shiftEnd` đã giảm 1h = `reducedShiftEnd`):

| Điều kiện `lastOut` | Kết quả `afternoon` |
|---|---|
| `lastOut >= reducedShiftEnd` | 4 h (credit đủ buổi chiều gốc) |
| `lastOut < reducedShiftEnd` | `clamp(4 − earlyBy, 0, 4)` trong đó `earlyBy = reducedShiftEnd − lastOut` |

> Kết hợp với buổi sáng (4h khi vào đúng giờ):  
> `normalHours = 8 − earlyBy` (về sớm bao nhiêu thì trừ bấy nhiêu, tối thiểu 0)  
> Nếu về đúng hoặc sau `reducedShiftEnd` → `normalHours = 8h = 1 công`

```
normalHours = _floorWorkingToBlock(morning + afternoon)
```

---

## 7. Tính OT

> **Unified OT block**: chạy cho **tất cả** số log chấm công (0 = vắng, 1 = 1 lần, ≥2 = bình thường).  
> Tách riêng trước ca và sau ca, tính independent, sum lại.  
> `otFinal` KHÔNG được tính bằng global `clamp(otActual, otApproved)` — thay vào đó mỗi nhánh tự tính đúng.

### 7.1 Base OT (trước khi tra OT register)

```
baseOtActual = _floorToBlock(max(lastOut − shiftEnd, 0))
otApproved   = 0
```

> `shiftEnd` là giờ ca đã điều chỉnh (có thể đã giảm 1h cho chế độ thai sản/con nhỏ).

### 7.2 Có đăng ký OT — tiền xử lý

1. **Deduplicate:** giữ record có `id` lớn nhất theo `uniqueKeyWithoutId`
2. **Tách OT nghỉ trưa (chỉ ngày thường):** Nếu `restHour > 0` AND không phải Chủ nhật AND tồn tại record thỏa `otTimeBegin.hour <= restBegin.hour` AND `otTimeEnd.hour >= restEnd.hour` → đánh dấu `otRestHour = true`, loại record đó ra khỏi danh sách
3. Xử lý OT records còn lại qua `_calcOtRecords`

> **Chủ nhật:** bước lọc OT nghỉ trưa bị bỏ qua hoàn toàn. OT full-day (08:00-17:00) sẽ trùm qua giờ nghỉ trưa và được xử lý trong `_calcOtRecords` với deduction 1h.

### 7.3 Phân loại OT records — `_calcOtRecords`

| Nhóm | Điều kiện | Mô tả |
|---|---|---|
| **Chủ nhật full-day** | Chủ nhật AND `beginHour < 12` AND `endHour > 13` | Span qua buổi trưa |
| **Trước ca** | `endHour <= shiftBegin.hour` | VD: 06:00–08:00 cho Day |
| **Sau ca** | `beginHour >= shiftEnd.hour` | VD: 17:00–19:00 cho Day |

### 7.4 Tính OT trước ca

```
earliestBegin = min(beginOT) của các records trước ca
latestEnd     = max(endOT) của các records trước ca
otApproved    = latestEnd − earliestBegin
earliestStart = shiftBegin − otApproved
rawActual     = if firstIn < earliestStart → otApproved
                else → max(shiftBegin − firstIn, 0)
otActual      = _floorToBlock(rawActual)
otFinal       = clamp(otActual, 0, otApproved)
```

### 7.5 Tính OT sau ca

```
earliestBegin = min(beginOT) của các records sau ca
latestEnd     = max(endOT) của các records sau ca
otApproved    = latestEnd − earliestBegin
rawActual     = if lastOut > shiftEnd → lastOut − shiftEnd   else 0   ← không cap bởi latestEnd
otActual      = _floorToBlock(rawActual)
otFinal       = clamp(otActual, 0, otApproved)
```

> **Lý do:** `otActual` phản ánh thời gian thực NV ở lại sau ca, không bị giới hạn bởi giờ kết thúc OT register.  
> `otFinal` mới chịu trách nhiệm cap theo `otApproved`.  
> Ví dụ: OT register 17:00–19:00, lastOut = 20:03 → `otActual = 3.0h`, `otApproved = 2.0h`, `otFinal = 2.0h`.

### 7.6 Chủ nhật full-day (trong `_calcOtRecords`)

```
otApproved = (endOT − beginOT) − 1h         [trừ giờ nghỉ trưa cố định]
otActual   = baseOtActual                     [time after shiftEnd]
otFinal    = clamp(otActual, 0, otApproved)
```

> Kết quả này sau đó bị ghi đè bởi **Sunday block** (mục 8).

### 7.7 Tổng hợp

```
totalActual   = otActual_before + otActual_after
totalApproved = otApproved_before + otApproved_after
totalFinal    = otFinal_before + otFinal_after
```

### 7.8 OT giờ nghỉ trưa

```
if otRestHour AND allowOtInRestTime:
    otActual   += restHour
    otApproved += restHour
    otFinal    += restHour    ← cộng riêng, không tính lại global clamp
    noteCheckin += 'OT giờ nghỉ trưa'
```

> Rest-hour OT luôn được duyệt 100%. Cộng vào từng biến riêng lẻ để không làm sai otFinal đã tính per-segment ở bước trên.

### 7.9 OT cho trường hợp 0 / 1 log — `_calcOtApproved`

Khi không có `lastOut` (vắng hoặc 1 lần chấm), `otActual = 0`. Nếu nhân viên có đăng ký OT:

```
otApproved = _calcOtApproved(date, otRecs, shiftBegin, shiftEnd)
otFinal    = 0    ← không có giờ thực tế
```

`_calcOtApproved` phân loại records (trước ca / sau ca / Sunday) theo cùng logic với `_calcOtRecords`, nhưng chỉ tính `otApproved` (không cần `firstIn`/`lastOut`).

### 7.10 Tổng kết otFinal

| Trường hợp | otFinal |
|---|---|
| `lastOut != null`, có OT records → `_calcOtRecords` | `Σ(otFinal per segment)` + restHour (nếu có) |
| `lastOut != null`, OT records rỗng sau filter | `clamp(otActual, 0, 0) = 0` |
| `lastOut != null`, không có đăng ký OT | `0` (otApproved = 0) |
| `lastOut == null` (0 hoặc 1 log) | `0` (otActual = 0) |

> **Không có global `clamp(otActual, otApproved)` sau cùng.**  
> Tổng per-segment finals có thể < `clamp(totalActual, totalApproved)` khi một segment thiếu actual và segment khác thừa — global clamp sẽ trả về kết quả sai cao hơn.

---

## 8. Xử lý ngày Chủ nhật

Áp dụng **sau** khi tính normalHours và OT (ghi đè):

```
if otApproved > 0:
    otApproved = shiftEnd − shiftBegin       [dùng shiftBegin/shiftEnd đã override từ OT register]
    if shiftBegin.hour < 12 AND shiftEnd.hour > 13:
        otApproved −= 1                      [trừ giờ nghỉ trưa]

otActual    = normalHours                    [toàn bộ giờ làm chuyển thành OT]
normalHours = 0
otFinal     = clamp(otActual, 0, otApproved)

if otActual > 0:
    noteSunday = 'OT ngày CN'
    if otActual > 4 AND firstIn < restBegin(12:00) AND lastOut > restEnd(13:00):
        noteSunday += 'Có phụ cấp cơm trưa'
```

> `restBegin/restEnd` cho Chủ nhật luôn là 12:00/13:00 (cố định).  
> `shiftBegin/shiftEnd` là từ OT register (nếu có), không phụ thuộc vào ca gốc.  
> Nếu nhân viên không có OT register → `otApproved = 0` → `otFinal = 0`.

---

## 9. Ghi chú tự động (Notes)

Nhiều ghi chú trong cùng 1 field ngăn cách bằng ` ; `.

### attNote2 (`noteCheckin`) — tất cả ghi chú liên quan chấm công & chế độ

| Điều kiện | Nội dung |
|---|---|
| Chỉ 1 lần chấm công | `Chỉ có 1 lần chấm công` |
| `lastOut ≤ shiftBegin` | `Không chấm công RA` |
| `firstIn ≥ shiftEnd` | `Không chấm công VÀO` |
| OT bao trùm giờ nghỉ trưa AND `allowOtInRestTime = true` | `OT giờ nghỉ trưa` |
| `firstIn > shiftBegin` | `Vào trễ` |
| `lastOut < shiftEnd` | `Ra sớm` |
| `shiftBegin − firstIn ≥ 60'` AND không có OT register trước ca | `Vào sớm ≥1h, không có ĐK OT trước ca` |
| `lastOut − shiftEnd ≥ 60'` AND không có OT register sau ca | `Ra trễ ≥1h, không có ĐK OT sau ca` |
| Chế độ mang thai (date-based) | `Chế độ mang thai` |
| Chế độ con nhỏ (date-based) | `Chế độ con nhỏ` |

> **Tất cả so sánh sớm/trễ** dùng `shiftEnd` hiện tại (đã điều chỉnh cho chế độ thai sản/con nhỏ).  
> **Kiểm tra "có OT register trước ca":** `otTimeEnd.hour <= shiftBegin.hour`  
> **Kiểm tra "có OT register sau ca":** `otTimeEnd.hour > shiftEnd.hour`  
> Không áp dụng cho Chủ nhật.

### attNote3 (`noteSunday`) — ghi chú Chủ nhật

| Điều kiện | Nội dung |
|---|---|
| Chủ nhật có giờ làm | `OT ngày CN` |
| + otActual > 4h AND span qua 12:00-13:00 | `OT ngày CN ; Có phụ cấp cơm trưa` |

---

## 10. Phát hiện dị thường (Anomalies → sheet "Important Note")

| Loại | Điều kiện |
|---|---|
| `[Resigned + Att]` | workStatus chứa `'Resigned'` AND có log chấm công vào/sau `resignOn` |
| `[Ra 16-17h]` | shift `== 'Day'` AND workStatus `== 'Working'` AND `!isYoungChild` AND `!isPregnant` AND không phải Chủ nhật AND `lastOut.hour == 16` |

> **[Ra 16-17h]** phát hiện nhân viên ca Day về lúc 16:xx mà không thuộc chế độ thai sản/con nhỏ — khả năng cao thiếu ngày tháng maternity trong DB. Canteen tự loại vì shift ≠ `'Day'`. Nhân viên đang hưởng chế độ được loại khỏi cảnh báo này.

---

## 11. Cột Working Day

```
normalDays = _r2(normalHours / 8)   ← tính & làm tròn ngay tại result.add()
```

- Nhân viên đủ công (8h) → 1.0 công
- Nhân viên mang thai/con nhỏ về đúng `reducedShiftEnd` → normalHours = 8h → 1.0 công
- Tổng Working Day trong Summary = `Σ(ts.normalDays)` — cộng giá trị đã làm tròn, **không** tính lại `Σ(hours) / 8` (tránh lệch do thứ tự phép tính)

---

## 12. Làm tròn số

### Bước 1 — Floor theo block (trong tính toán)

| Áp dụng cho | Hàm | Quy tắc |
|---|---|---|
| OT hours | `_floorToBlock(hours)` | Floor xuống `otBlockMinute`; bỏ qua nếu < `minOtMinute` |
| Giờ làm bình thường | `_floorWorkingToBlock(hours)` | Floor xuống `workingBlockMinute` (default 1 = không làm tròn) |

### Bước 2 — Làm tròn thập phân (tại `result.add`)

Áp dụng **ngay khi tạo `TimeSheetDate`**, trước khi lưu vào danh sách kết quả:

| Field | Hàm | Ví dụ |
|---|---|---|
| `normalHours` | `_r2(v)` — 2 chữ số, half-up | 1.235 → 1.24 |
| `normalDays` | `_r2(normalHours / 8)` | tính & làm tròn cùng lúc |
| `otHours` | `_r1(v)` — 1 chữ số, half-up | 1.25 → 1.3 |
| `otHoursApproved` | `_r1(v)` | |
| `otHoursFinal` | `_r1(v)` | |

```dart
_r1(v) = double.parse(v.toStringAsFixed(1))   // half-up, 1 decimal
_r2(v) = double.parse(v.toStringAsFixed(2))   // half-up, 2 decimals
```

### Bước 3 — Format Excel

| Cột Excel | numberFormat |
|---|---|
| Working (hour), Working (day) | `0.00` |
| OT Actual, OT Approved, OT Final | `0.0` |

---

## 13. Xuất Excel

File: `Timesheets_yyyyMMdd_HHmm.xlsx`

| Sheet | Các cột |
|---|---|
| **Important Note** | Type, Detail — danh sách anomalies |
| **Detail** | No, Date, Employee ID, Finger ID, Full name, Dept, Section, Group, Shift, First In (HH:mm:ss), Last Out (HH:mm:ss), Working (hour), Working (day), OT Actual, OT Approved, OT Final, Note Checkin, Note Sunday, Joining Date, Resign Date |
| **Summary** | No, Employee ID, Full name, Dept, Section, Group, Total Working (hours), Total Working (days), Total OT Actual, Total OT Approved, Total OT Final, Joining Date, Resign Date |

---

## 14. Sơ đồ quyết định tổng quát

```
── Settings ────────────────────────────────────────────────────────
minOtMinute       = 30    ← ngưỡng tối thiểu OT
otBlockMinute     = 30    ← block làm tròn OT
workingBlockMin   = 1     ← block làm tròn giờ làm
allowOtInRest     = false ← cho phép OT giờ nghỉ trưa
excludeEmpIds     = []    ← NV bị loại khỏi tính

── Shift params (App.gValue.shiftParams từ DB) ───────────────────
_getShiftParam(name, date)  → match tên + ngày hiệu lực → fallback default
_resolveGroupShift(keyword, date) → Canteen group → 'Canteen_new' v.v.

── Pre-index (1 lần) ───────────────────────────────────────────────
logIndex   → Map<dayKey, Map<empId, List<AttLog>>>
shiftIndex → Map<dayKey, Map<shiftName, Set<empId>>>
otIndex    → Map<dayKey, Map<empId, List<OtRegister>>>

── Vòng lặp chính ──────────────────────────────────────────────────
for (date, employee):
    Xác định ca: Day → Canteen(resolve) → Shift1/2 → Sunday→Day
    Nếu Sunday + có OT register:
        shiftBegin/End từ OT register (record id lớn nhất)
    restBegin/End: Sunday=12:00/13:00 cố định; weekday=shiftBegin+4h+restHour

    isPregnant / isYoungChild → shiftEnd −= 1h

    ┌─ 0 logs ─────────────────────────────────→ firstIn=null, lastOut=null (zeros)
    ├─ 1 log ─────────────────────────────────→ firstIn=log[0], lastOut=null; note 'Chỉ có 1 lần chấm công'
    └─ ≥2 logs:
        fi, lo = min/max(timestamps); firstIn=fi, lastOut=lo
        ┌─ lo ≤ shiftBegin ───────────────────→ 'Không chấm công RA'
        ├─ fi ≥ shiftEnd ────────────────────→ 'Không chấm công VÀO'
        └─ fi ≠ lo:
            morning   = _normalMorning(fi, lo, shiftBegin, restBegin)
            afternoon = isPregnant|isYoungChild
                          ? _youngChildAfternoon(lo, restEnd, shiftEnd)  ← 8−earlyBy
                          : _normalAfternoon(fi, lo, shiftEnd, restEnd)
            normalHrs = _floorWorkingToBlock(morning + afternoon)
            ghi chú: Vào trễ / Ra sớm / Vào sớm ≥1h / Ra trễ ≥1h

    ── Unified OT block (chạy cho cả 0 / 1 / ≥2 logs) ──────────────────
    if lastOut != null:
        otActual = _floorToBlock(max(lastOut − shiftEnd, 0))
    if empId in OT register:
        dedup (highest id per uniqueKey)
        if lastOut != null:
            filter rest-hour record (weekday only) → otRestHour flag
            if otRecs not empty:
                _calcOtRecords → otActual, otApproved, otFinal (per-segment)
            else:
                otFinal = 0   ← no records left after filter
            if otRestHour AND allowOtInRest:
                otActual += restHour; otApproved += restHour; otFinal += restHour
        else:
            otApproved = _calcOtApproved(...)   ← approved only, otFinal stays 0

    Sunday block (ghi đè):
        otApproved = shiftEnd−shiftBegin [−1h lunch nếu span qua trưa]  (chỉ nếu có OT reg)
        otActual = normalHrs; normalHrs = 0
        otFinal  = clamp(otActual, 0, otApproved)

    Anomaly checks → anomalies[]
    Regime notes   → 'Chế độ mang thai' / 'Chế độ con nhỏ'
    Sunday notes   → 'OT ngày CN' [+ 'Có phụ cấp cơm trưa']
```

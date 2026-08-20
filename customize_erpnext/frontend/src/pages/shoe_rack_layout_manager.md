# Shoe Rack Layout Manager — Review & Tài liệu logic

> **Mục đích:** Ghi lại logic trang sắp xếp tủ giày trong app React nhúng, kèm kết quả review code (chỉ review, không sửa).
> **Phạm vi:** Ứng dụng React nhúng
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-07-28

> **Chỉ review — không sửa code.**
> File chính: `src/pages/ShoeRackLayoutManager.jsx` (+ `ShoeRackLayoutManager.css`)
> Backend: `customize_erpnext/api/api_endpoints.py` và `customize_erpnext/doctype/shoe_rack/shoe_rack.py`
> Review lần 2: 2026-07-24 (cả 2 file JS + Python đã bị chỉnh trong lúc review → số dòng dưới đây là **tương đối**, hãy dò theo tên hàm).

---

## 1. Tổng quan chức năng

Trang React (Vite SPA) làm dashboard quản lý **tủ để giày (Shoe Rack)** của nhà máy:

1. **Hiển thị sơ đồ giá** — load toàn bộ `Shoe Rack`, gom thành **block 16 giá** (4×4), tách 2 loại theo `rack_display_name`:
   - `number` — mã chỉ có số (1, 2, 3…)
   - `letter` — mã có chữ (A1, G3, J7…) → đặt bên dưới các block số.
2. **Edit mode** — kéo/thả + resize block bằng `react-grid-layout`, thêm **Pathway (lối đi)**; lưu vào doctype single **Shoe Rack Layout Settings** (`layout_data`, `pathway_blocks` là JSON string).
3. **View mode** — render bằng `flex-wrap` (dùng cho cả desktop & mobile), sắp theo `(y, x)` của layout đã lưu.
4. **Assign Racks panel** — lấy nhân viên vào làm theo ngày (`get_today_joiners`), gợi ý slot trống (`suggest_shoe_racks`), gán (`assign_shoe_racks`), in nhãn.
5. **Clear Left Employees panel** — liệt kê slot còn giữ nhân viên `status = Left` (`get_left_employees_in_racks`) và xoá (`clear_left_employees_from_racks`).
6. **Gender Mismatch panel** *(mới)* — liệt kê giá 2 ngăn có **2 người khác giới** dùng chung (`shoe_rack.get_gender_mismatch_racks`); mở form giá để xử lý.
7. **Cảnh báo trực quan trên từng ô giá:**
   - `⚠️` (góc phải) — giá đang chứa nhân viên đã nghỉ (`leftEmployees`).
   - `⚧` (góc trái) — giá 2 ngăn khác giới (`genderMismatchSet`).
   - chấm nhỏ `no-suggest-dot` — giá `do_not_auto_suggest` **(chỉ hiện ở edit mode — xem CI-2)**.

### Màu trạng thái (`getStatusColor`)
Parse `status = "occupied/total"`: `0/*` → empty, `occupied < total` → partial, else → full.

### Mô hình dữ liệu Shoe Rack (từ `shoe_rack.py`)
- Mỗi giá có `compartments` = `"1"` | `"2"` (**string, không phải số**), `user_type` = `Employee` | `External`.
- 4 field người: `compartment_{1,2}_employee` và `compartment_{1,2}_external_personnel`.
- `validate()` hook: tự set `user_type`/`naming_series`, xoá field không khớp `user_type`, **chặn xếp 1 người vào 2 giá** (`check_duplicate_assignment`, `frappe.throw`), auto `status` + `rack_display_name`, và **cảnh báo (không chặn)** khi 2 người khác giới (`check_mixed_gender` → `msgprint`).

---

## 2. Luồng dữ liệu & state

### Luồng khởi tạo
`loadRackData()` → fetch `Shoe Rack` (bỏ giá không có `rack_display_name`) + fetch Employee `status=Left` + `loadGenderMismatchRacks()` (fire-and-forget) → `setRacks()` → `loadLayout()` → parse settings → `createBlocksFromRacks(racks, savedLayout, savedPathways)`.

### API dùng
| Endpoint | File | Vai trò |
|----------|------|---------|
| `get_today_joiners(date)` | `api_endpoints.py` | Employee `Active` + `date_of_joining=date`, annotate giá đang giữ |
| `suggest_shoe_racks(employees)` | `api_endpoints.py` | 2 pass: ưu tiên cùng gender → bất kỳ; loại `do_not_auto_suggest`; chỉ `rack_type=Standard Employee` |
| `assign_shoe_racks(assignments)` | `api_endpoints.py` | Ghi `compartment_N_employee`; chặn slot đã bị chiếm; `rack.save()` chạy qua `validate()` |
| `get_left_employees_in_racks()` / `clear_...` | `api_endpoints.py` | Danh sách/ xoá nhân viên đã nghỉ còn trong giá |
| `get_gender_mismatch_racks()` | `shoe_rack.py` | SQL join Employee/External Personnel, so gender cặp trong giá 2 ngăn |

---

## 3. 🐞 BUG (theo mức độ)

### 🔴 Nghiêm trọng — sai dữ liệu hiển thị

**B1. `autoAssignAll` / `clearAll` đánh dấu TẤT CẢ pending là thành công dù chỉ một phần thành công**
`autoAssignAll` (~`jsx:215-216`) và `clearAll` (~`jsx:308-309`):
```js
if (data.assigned > 0) {                       // hoặc data.cleared > 0
  setAssignedSet(prev => new Set([...prev, ...pending.map(r => r.employee)]));
}
```
Server trả `assigned = 3` trên `pending = 5` (2 slot bị chiếm → nằm trong `data.errors`), nhưng UI vẫn nạp **cả 5** vào `assignedSet` → 2 dòng thất bại vẫn hiện "Assigned". `clearAll` y hệt.
→ **Hướng fix:** server trả về danh sách employee/slot xử lý thành công, FE chỉ add đúng phần tử đó; hoặc khi có `errors` thì reload lại danh sách từ DB.

**B2. Backend `get_left_employees_in_racks` bỏ sót giá chỉ có compartment 2 bị chiếm**
`api_endpoints.py` (~dòng 631-643): dùng đồng thời `filters` (comp1 `!= ""` AND comp1 `is set`) **và** `or_filters`. Frappe ghép `filters AND or_filters`, nên rút gọn thành **"comp1 bắt buộc có giá trị"**. Giá có `compartment_1_employee` rỗng nhưng `compartment_2_employee` là nhân viên đã nghỉ → **không bao giờ trả về**, không thể clear qua UI.
→ **Hướng fix:** bỏ khối `filters`, chỉ giữ `or_filters=[[comp1 is set],[comp2 is set]]` (đoạn sau vốn đã lọc lại bằng `left_set` nên vẫn đúng).

### 🟠 Trung bình

**B3. Vào Edit mode có thể lập tức bật `hasUnsavedChanges`** — `GridLayout` gọi `onLayoutChange` khi mount / khi prop `layout` đổi. `useEffect [isEditMode]` (~`jsx:63-72`) tạo mảng layout mới (static=false) mỗi lần vào edit → `handleLayoutChange` (`jsx:719`) chạy dù người dùng chưa kéo gì → nút Cancel hỏi "Discard changes?" oan, hoặc "OK" ghi save thừa.
→ **Hướng fix:** so sánh layout thực sự khác trước khi set `hasUnsavedChanges`, hoặc bỏ qua lần `onLayoutChange` đầu tiên.

**B4. Double-render layout & race khi khởi tạo** — `useEffect [racks]` (~`jsx:78-82`) gọi `createBlocksFromRacks(racks)` **không có savedLayout**, trong khi `loadRackData → loadLayout` cũng gọi `createBlocksFromRacks(racks, savedLayout, …)`. Hai lời gọi cùng ghi `setLayout`; thứ tự phụ thuộc timing `fetch` trong `loadLayout`. Nếu effect chạy sau → **layout đã lưu bị ghi đè bằng vị trí mặc định** (nhấp nháy hoặc mất layout).
→ **Hướng fix:** bỏ effect `[racks]` (thừa) hoặc chỉ dùng làm fallback khi chưa có settings.

**B5. `assignDate` mặc định lệch ngày buổi sáng sớm** — (~`jsx:31`) `new Date().toISOString().split('T')[0]` trả **ngày UTC**. Với VN (UTC+7), trước 07:00 sáng sẽ ra **ngày hôm trước** → load nhầm joiners. (Đúng lỗi `toISOString` đã gặp ở module OT/Attendance.)
→ **Hướng fix:** dùng local, ví dụ `new Date().toLocaleDateString('en-CA')`.

### 🟡 Nhẹ / an toàn

**B6. XSS tiềm ẩn khi in nhãn** — `printLabels` (~`jsx:348-376`) nhét `employee_name`, `rack_display_name` thẳng vào HTML rồi `document.write`. Dữ liệu nội bộ nên rủi ro thấp, nhưng nên escape.

**B7. `getCsrf()` có thể `undefined`** — nếu không có `window.frappe` lẫn `<meta name="csrf-token">`, header `X-Frappe-CSRF-Token` = `undefined` → POST fail khó hiểu. Nên kiểm tra & báo lỗi rõ ràng.

**B8. `Math.max(...savedPathways.map(parseInt…))` có thể ra `NaN`** — (~`jsx:514`) nếu một `pathway.id` không đúng dạng `pathway-<số>`, `parseInt` → `NaN` → `nextPathwayId = NaN` → pathway mới có id `pathway-NaN`, và các pathway sau đè key. Edge hiếm nhưng nên chặn.

**B9. `assign_shoe_racks` chỉ chặn slot đã chiếm** — không kiểm tra `compartment` hợp lệ với `compartments` của giá, không kiểm tra employee `Active`. *(Đã nhẹ đi:* `rack.save()` chạy qua `validate()` nên: gán comp2 vào giá 1 ngăn sẽ bị `validate` **xoá lại**; xếp trùng 2 giá bị `check_duplicate_assignment` **throw** → rơi vào `errors`. Nhưng việc "âm thầm xoá comp2" có thể khiến `assigned` đếm thành công mà thực tế không ghi gì.)

---

## 4. ✅ Điểm làm tốt

- **An toàn concurrency khi assign:** `suggest` chỉ tính trong RAM, nhưng `assign` kiểm tra slot đã chiếm + `validate()` chặn trùng giá → không double-book dữ liệu (chỉ báo lỗi mềm).
- **Truy vấn gộp:** `get_left_employees_in_racks` và `get_gender_mismatch_racks` lấy dữ liệu nhân viên bằng 1 query, không N+1.
- **Degrade mềm:** thiếu `window.frappe.show_alert` thì fallback `alert()`; lỗi gender-mismatch chỉ `console.error`, không chặn dashboard.
- **`suggest` giữ nguyên dòng `already_assigned`** khi map kết quả về (không ghi đè giá cũ).
- **Trạng thái loading/disabled per-row** (`assigningRows`, `clearingRows`) tránh double-submit từng dòng.

---

## 5. 🔧 Đề xuất cải thiện

**Kiến trúc / DRY**
1. **Tách helper gọi API** (giống pattern `callFrappeMethod` trong memory dự án): gom lặp `fetch + headers + csrf + result.message` (~7 chỗ) về 1 hàm; xử lý lỗi & `credentials` nhất quán.
2. **Tách component `<RackCell>`** — block render giá bị lặp gần như y hệt giữa view mode (~`jsx:1010-1034`) và edit mode (~`jsx:1094-1117`).
   - **CI-2:** view mode **thiếu** chấm `no-suggest-dot` (`do_not_auto_suggest`) mà edit mode có → nên đồng bộ.
3. **Tách component panel** — `AssignPanel` / `ClearPanel` / `GenderPanel` dùng chung khung overlay + table + toolbar; nên trừu tượng hoá 1 `<SidePanel>`.
4. **Đưa CSS nút Gender ra file** — hiện chèn `<style>` inline trong JSX (~`jsx:824-856`), lệch với phần còn lại dùng `ShoeRackLayoutManager.css`.
5. **`react-grid-layout`** đang dùng bản không-responsive + tự tính `containerWidth`; cân nhắc `WidthProvider`.

**Đúng đắn / UX**
6. Sau `autoAssignAll` / `clearAll` có `errors` → **reload danh sách** để phản ánh đúng DB (liên quan B1).
7. `loadGenderMismatchRacks` được gọi 2 lần khi mở panel sau Refresh (trong `loadRackData` + onClick panel) → có thể gộp.
8. **Magic number 16** (giá/block) và quy tắc tách letter/number nên đặt hằng số có tên + comment.
9. `handleRackClick` dùng `window.location.href` → thoát SPA, full reload; dùng router nếu có route nội bộ.

**Bảo mật / quyền**
10. Toàn bộ endpoint `@frappe.whitelist()` + `ignore_permissions=True` → **bất kỳ user đăng nhập nào** cũng assign/clear/xoá giá. Nên thêm `frappe.has_permission("Shoe Rack", "write")` hoặc giới hạn role.

**Dọn rác**
11. Xoá file thừa cùng thư mục: `aaaa` (0 byte); cân nhắc `RackLayoutComplete.jsx` (bản cũ dùng `@dnd-kit`, không còn import).
12. Bỏ block code chết đã comment (`loadLayout` ~`jsx:621-627`) và các `console.log` đã comment (~`jsx:398-400`).

---

## 6. Ghi chú đã sửa so với review lần 1
- ✅ **Typo `sx` trong bảng Clear panel** — đã sửa (giờ hiển thị đúng `{row.rack_display_name}`).
- ✅ `console.log` debug trong `createBlocksFromRacks` đã comment.
- ➕ Thêm feature **Gender Mismatch** (state, panel, icon `⚧`, endpoint `get_gender_mismatch_racks`).

## 7. Tham chiếu nhanh (tên hàm — số dòng tương đối)

| Việc | Vị trí |
|------|--------|
| Gom block 16 giá, tách letter/number | `createBlocksFromRacks` ~`jsx:378-535` |
| Load / lưu layout (PUT, fallback POST 404) | `loadLayout` ~600 / `saveLayout` ~641 |
| Toggle static theo edit mode | `useEffect [isEditMode]` ~`jsx:63-72` |
| Icon cảnh báo giới tính | `renderGenderWarningIcon` ~`jsx:804-819` |
| Assign / Clear / Gender panel | ~`jsx:1131` / ~1266 / ~1376 |
| API joiners / suggest / assign | `api_endpoints.py` ~349 / 413 / 570 |
| API left employees (get/clear) | `api_endpoints.py` ~625 / 698 |
| Gender mismatch + validate hook | `shoe_rack.py` ~192 / 11 |

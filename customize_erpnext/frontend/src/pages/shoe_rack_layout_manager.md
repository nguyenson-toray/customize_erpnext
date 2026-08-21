# Shoe Rack Layout Manager — Review & Tài liệu logic

> **Mục đích:** Ghi lại logic trang sắp xếp tủ giày trong app React nhúng + toàn bộ backend Shoe Rack, kèm kết quả review code.
> **Phạm vi:** Ứng dụng React nhúng + DocType Shoe Rack
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-21

> File chính: `frontend/src/pages/ShoeRackLayoutManager.jsx` (1.797 dòng) + `ShoeRackLayoutManager.css`
> Backend: `customize_erpnext/api/api_endpoints.py` (toàn bộ file là API tủ giày) và
> `customize_erpnext/doctype/shoe_rack/shoe_rack.py` (1.381 dòng)
> UI DocType: `shoe_rack.js` (form) · `shoe_rack_list.js` (list view, 1.026 dòng)
> Số dòng trong tài liệu này khớp với commit `f6f0051` (2026-08-21) — nếu lệch, dò theo **tên hàm**.

---

## 1. Thay đổi lớn so với bản review 2026-07-28

Bản trước mô tả mô hình **tủ có giới tính**. Mô hình đó đã bị bỏ:

| Trước | Bây giờ |
|-------|---------|
| `Shoe Rack.gender` (Select, reqd) — tủ dành cho nam hoặc nữ | ❌ Bỏ khỏi doctype. Giới tính **suy từ người đang ngồi trong tủ** |
| `Shoe Rack.do_not_auto_suggest` (field trong doctype) | Chuyển thành **Custom Field** trên Shoe Rack + cờ mới `Employee.custom_do_not_suggest_shoe_rack` |
| Lệch giới tính → chặn save | Chỉ **cảnh báo** (`msgprint`), thêm panel rà soát |
| Một người ở 2 tủ → luôn `frappe.throw` | Thêm **chế độ auto-reassign**: Data Import thì DỜI người, không chặn |
| `autoname: field:rack_display_name` (name = "1", "J1") | `autoname: naming_series:[rack_display_name]` → name = `RACK-00001`, `J-00001`… |
| Assign panel chỉ theo ngày vào làm | Thêm tab **All Unassigned Employees** |
| — | Cờ **Unknown** (`compartment_N_unidentified`) cho ngăn "có giày nhưng không biết của ai" |
| — | Nút **⇄ Swap** từng dòng: đánh dấu ngăn cũ Unknown + dời NV sang tủ khác |
| — | Tìm tủ theo tên, lọc tủ nửa trống theo giới tính người đang ngồi, highlight theo Group |

---

## 2. Mô hình dữ liệu Shoe Rack

### 2.1 Field trong doctype (`shoe_rack.json`)

| Field | Kiểu | Ghi chú |
|-------|------|---------|
| `naming_series` | Select | `RACK-` / `G-` / `J-` / `A-` — tự set trong `validate` theo `rack_type` |
| `rack_display_name` | Data, read-only | Sinh trong code từ `name`: `RACK-00001`→`1`, `J-00001`→`J1`. **Có UNIQUE index trong DB** (di sản của `field:` autoname cũ) |
| `rack_type` | Select | `Standard Employee` / `Guest` / `Japanese Employee` / `External Personnel` |
| `compartments` | Select | **`"1"` hoặc `"2"` — chuỗi, không phải số** |
| `user_type` | Select, read-only | `Employee` (Standard + Japanese) hoặc `External` (Guest + External Personnel) — tự suy từ `rack_type` |
| `status` | Data, read-only | `"0/2"`, `"1/2"`, `"2/2"`, `"0/1"`, `"1/1"` |
| `compartment_{1,2}_employee` | Link Employee | |
| `compartment_{1,2}_external_personnel` | Link External Personnel | |
| `compartment_{1,2}_employee_name` | Data | fetch_from employee |
| `gender_employee_1` / `employee_2_gender` | Data, read-only | fetch_from `compartment_N_employee.gender`. **Tên 2 field không đối xứng** — cẩn thận khi copy code |
| `compartment_{1,2}_unidentified` | Check | "Chưa xác định (Unknown)" — có người nhưng không biết là ai |

### 2.2 Bẫy ở tầng DB (đã kiểm bằng `SHOW COLUMNS`)

- 🔴 **`gender_employee_1` là `NOT NULL` (không default)**, còn `employee_2_gender` thì nullable.
  Ghi `None` vào `gender_employee_1` bằng `db.set_value` ⇒ `IntegrityError 1048`.
  Vì vậy `release_person_from_rack()` ghi `""` chứ không ghi `None` — xem comment tại `shoe_rack.py:239`.
- ⚠ **Cột `gender` vẫn còn trong `tabShoe Rack`** dù field đã bị xoá khỏi doctype (cột mồ côi).
  `load_rack_layout()` đã bỏ `"gender"` khỏi danh sách fields; đừng thêm lại.
- ⚠ **`do_not_auto_suggest` là Custom Field, KHÔNG có trong `fixtures/custom_field.json`** —
  chỉ được tạo khi chạy tay `api_endpoints.setup_assignment_field`. Site mới migrate sẽ **không có** field này.
  Code chịu được (mọi chỗ đọc đều bọc `meta.has_field`), nhưng tính năng im lặng biến mất.
  Ngược lại `Employee.custom_do_not_suggest_shoe_rack` **có** trong fixtures nên an toàn.
- `rack_display_name` UNIQUE ⇒ 2 tủ không được trùng tên hiển thị, kể cả khi `name` đã khác nhau.

### 2.3 Dữ liệu thật trên production (2026-08-21)

748 tủ · series `RACK-`=732, `J-`=8, `G-`=4, `A-`=4 · 9 tủ `do_not_auto_suggest`
· **79 tủ có `compartment_2_unidentified = 1`** (63 Standard, 8 Japanese, 4 Guest, 4 External).

Trong 79 tủ đó, **73 tủ ngăn 2 hoàn toàn trống** — di sản của lỗi *field từng có `default = 1`*,
khiến tủ mới tạo bị tick sẵn ngăn 2 → status nhảy `0/2`→`1/2` và Suggest Slots bỏ qua tủ.
Dọn bằng menu **Clear Unknown Flags** (có dry-run).
6 tủ còn lại **vừa có người vừa bị tick Unknown** — trạng thái không hợp lệ do các đường ghi
`db.set_value` không đi qua `validate`; lần save tay kế tiếp `enforce_unidentified_flags()` sẽ tự bỏ tick.

---

## 3. Vòng đời document (`hooks.py` → `doc_events["Shoe Rack"]`)

```
validate  → customize_erpnext...shoe_rack.validate
on_update → shoe_rack.on_update
          → uniform_control.api.shoe_rack_sync.sync_profiles_on_rack_update
```

### 3.1 `validate(doc, method)` — `shoe_rack.py:34`

Thứ tự các bước (quan trọng, đừng đảo):

1. Suy `user_type` từ `rack_type`.
2. Set `naming_series` nếu là document mới.
3. `clear_incompatible_assignments()` — xoá field không khớp `user_type`.
4. `check_duplicate_assignment()` — **một người = một tủ** (xem 3.2).
5. `compartments == "1"` ⇒ xoá sạch mọi field của ngăn 2.
6. `enforce_unidentified_flags()` — ngăn đã có người thật thì tự bỏ tick Unknown; tủ 1 ngăn thì
   `compartment_2_unidentified = 0`.
7. `update_status()` — **cờ Unknown được tính như đã có người**.
8. `check_mixed_gender()` — chỉ `msgprint` cảnh báo, không chặn.
9. `generate_display_name()`.

`compute_status(compartments, has_comp1, has_comp2)` (`:87`) là **nguồn duy nhất** tính status —
`update_status()`, `release_person_from_rack()` và JS form đều dùng chung công thức này.

### 3.2 `check_duplicate_assignment()` — `shoe_rack.py:151` + chế độ auto-reassign

```python
AUTO_REASSIGN_FLAG = "shoe_rack_auto_reassign"
def is_auto_reassign_mode():
    return bool(frappe.flags.in_import or frappe.flags.get(AUTO_REASSIGN_FLAG))
```

| Tình huống | Save tay | Auto-reassign (Data Import) |
|------------|----------|------------------------------|
| Người đã ở tủ khác | `frappe.throw` + chỉ tên tủ cũ | **Rút người khỏi tủ cũ** rồi ghi vào tủ mới |
| Cùng 1 người ở **cả 2 ngăn của chính tủ này** | `throw` | `throw` (dời đi đâu cũng không sửa được) |

- `release_person_from_rack()` (`:212`) dùng `db.set_value`, **cố ý không gọi `doc.save()`** để tủ cũ
  không chạy lại `validate` (sẽ đệ quy) — nên phải tự tính lại `status` tại chỗ.
- `log_reassignments()` (`:286`) ghi audit vào `add_comment("Info", …)` + `msgprint`, **chỉ trong
  auto-reassign mode**. Bọc try/except: *"An audit comment must never be the reason an import row fails."*
- `get_evicted_occupants()` (`:262`) so `get_doc_before_save()` với bản mới để log cả người bị **đẩy ra**
  (import ghi đè ngăn ⇒ người cũ mất tủ mà không có dòng nào trong file import nhắc tới).

Bật thủ công trong bench script:
```python
frappe.flags.shoe_rack_auto_reassign = True
```

---

## 4. Cơ chế gợi ý chỗ (`suggest_shoe_racks`)

### 4.1 `_build_slot_pools(exclude_slots, exclude_racks)` — `api_endpoints.py:487`

Dựng 2 pool ngăn trống, **chỉ trong `rack_type = "Standard Employee"`**:

- `paired_slots` — ngăn trống của tủ **đã có 1 người** (kèm `required_gender` = giới tính người đó)
- `empty_slots` — ngăn trống của tủ **chưa có ai**

Một ngăn bị coi là **đã chiếm** khi có Employee, **hoặc** External Personnel, **hoặc** `unidentified = 1`.

Loại trừ:
- tủ `do_not_auto_suggest = 1`
- tủ/ngăn trong `exclude_racks` / `exclude_slots` (dùng cho Swap)
- ngăn trống của tủ mà **người ngồi cùng có `Employee.custom_do_not_suggest_shoe_rack = 1`**
  → tủ của người đó không bị ghép thêm ai. (Bản thân người đó vẫn được gợi ý tủ bình thường nếu chưa có tủ.)

Mọi field tuỳ chọn đều đọc qua `frappe.get_meta(...).has_field(...)` nên chạy được cả khi site
chưa có Custom Field.

### 4.2 Ba lượt xếp (`api_endpoints.py:600`)

1. **Cùng giới tính** — nhét vào tủ đã có 1 người cùng giới (không sinh lệch giới tính).
2. **Tủ trống hoàn toàn.**
3. **Vét cạn** — bất kỳ ngăn trống nào còn lại, kể cả khác giới, để không ai bị bỏ sót.
   Tủ xếp kiểu này sẽ hiện trong panel **Gender Mismatch** để xử lý tay.

`swap_shoe_rack()` dùng **đúng thứ tự ưu tiên này** (`_pick()` tại `api_endpoints.py:852`).

### 4.3 `swap_shoe_rack()` — `api_endpoints.py:756`

Tình huống thật: Suggest gợi ý tủ N ngăn 1, nhưng ra hiện trường thì trong ngăn đã có đôi giày
không rõ của ai. Một cú bấm làm 3 việc:

1. Tick `compartment_N_unidentified = 1` cho ngăn cũ (⇒ engine không bao giờ gợi ý lại, status tính là đã đầy),
   rút NV ra khỏi ngăn đó nếu đã ghi vào DB.
2. Tìm chỗ mới, **loại nguyên tủ cũ** + `exclude_slots` (các slot mà những dòng khác trong bảng đang giữ).
3. Ghi NV vào chỗ mới **chỉ khi** NV thật sự đã được assign ở chỗ cũ. Dòng mới chỉ là gợi ý pending thì
   vẫn để pending ở slot mới.

Ngoại lệ: nếu ngăn cũ đang giữ **một NV khác đã biết tên** ⇒ đó là gợi ý cũ, không phải người lạ ⇒
**không** tick Unknown, chỉ trỏ NV sang slot khác.

Trả về đủ cờ để FE phản ánh cả trường hợp hỏng một nửa:
`marked_unknown` / `released` / `assigned` / `suggested` + slot mới.

---

## 5. Trang dashboard React

### 5.1 Luồng khởi tạo

`loadRackData()` (`jsx:705`)
→ `GET /api/resource/Shoe Rack?fields=["*"]` (bỏ tủ không có `rack_display_name`)
→ `GET Employee status=Left` → `leftEmployees`
→ `loadGenderMismatchRacks()` (fire-and-forget)
→ sort theo `rack_display_name` (`localeCompare` numeric)
→ `setRacks()` → `loadLayout()` → parse **Shoe Rack Layout Settings** (`layout_data`, `pathway_blocks` là JSON string)
→ `createBlocksFromRacks(racks, savedLayout, savedPathways)` (`jsx:546`).

Song song: `loadGroupOptions()` nạp danh sách `Group` cho bộ lọc highlight.

### 5.2 Sắp xếp block

- Gom **16 tủ / block** (4×4), tách theo `rack_display_name`:
  `letterRacks` (có chữ: A1, G3, J7…) đặt **bên dưới** `numberRacks` (chỉ số).
- **Edit mode**: `react-grid-layout` (`cols=5`, `rowHeight=2`, `compactType=null`, `preventCollision`),
  kéo bằng `.drag-handle`, resize 8 hướng, thêm **Pathway (lối đi)**.
- **View mode**: render bằng `flex-wrap` (`.mobile-rack-layout`) cho **cả desktop lẫn mobile**,
  sắp theo `(y, x)` của layout đã lưu. Nút Edit bị ẩn khi `containerWidth < 650`.

### 5.3 Bộ lọc & highlight (chỉ hiện ở view mode)

| Điều khiển | State | Cách hoạt động |
|------------|-------|----------------|
| **Find Rack** | `rackSearch` → `searchMatchSet` (`jsx:948`) | `normalizeRackQuery` (trim/upper/bỏ khoảng trắng). **Khớp chính xác thắng khớp prefix** — gõ "50" chỉ ra tủ 50, không ra 500/501 |
| **Half full, occupant is:** | `occupantGenderFilter` → `genderMatchSet` (`jsx:961`) | `getSingleOccupantGender()` (`jsx:15`): chỉ tủ **2 ngăn đang có đúng 1 người**; đọc `gender_employee_1` / `employee_2_gender` |
| Hai bộ trên | `filterMatchSet` (`jsx:972`) | Giao nhau (AND). `null` = không lọc. Tủ khớp `.filter-hit`, tủ còn lại `.filter-hidden` |
| **Highlight Group** | `selectedGroup` → `groupMemberIds` | API `get_employees_by_group`; tủ có thành viên → `.group-highlight`, còn lại `.group-dimmed` |

`useEffect [filterMatchSet]` (`jsx:980`) tự `scrollIntoView` tủ khớp đầu tiên — layout rất rộng nên
tủ tìm được thường nằm ngoài màn hình.

### 5.4 Cảnh báo trên ô tủ

| Dấu hiệu | Nguồn | Vị trí |
|----------|-------|--------|
| `⚠️` | `leftEmployees` — tủ còn giữ NV đã nghỉ | góc **phải trên** |
| icon giới tính | `genderMismatchSet` — 2 người khác giới chung tủ | góc **trái dưới**, `renderGenderWarningIcon()` (`jsx:1013`) |
| chấm `.no-suggest-dot` | `rack.do_not_auto_suggest` | **chỉ edit mode** — xem BUG B7 |

Màu nền: `getStatusColor()` parse `status = "occupied/total"` → `empty` / `partial` / `full`.

### 5.5 Ba panel

| Panel | Mở bằng | API |
|-------|---------|-----|
| **Assign Shoe Racks** | nút `Assign Racks` | `get_today_joiners` / `get_unassigned_employees` / `suggest_shoe_racks` / `assign_shoe_racks` / `swap_shoe_rack` |
| **Clear Left Employees** | nút `Clear Left Employees` | `get_left_employees_in_racks` / `clear_left_employees_from_racks` |
| **Gender Mismatch** | nút `Gender Mismatch (n)` | `shoe_rack.get_gender_mismatch_racks` |

**Assign panel có 2 tab** (`assignMode`):
- `by_date` — NV vào làm đúng ngày `assignDate`.
- `unassigned` — **mọi NV Active chưa chiếm ngăn nào**, bất kể ngày vào; để vét những người lọt lưới.

Cả hai đi qua `applyJoinersResponse()` (`jsx:146`) nên cùng một cấu trúc dòng; NV đã có tủ trong DB
được nạp sẵn vào `assignedSet` và hiện "Already assigned ✓".

Mỗi dòng có nút **Assign** và **⇄ Swap**; dòng đã swap hiện `⇄ was <tủ cũ> (Unknown)`.

---

## 6. Bản đồ API

### `api_endpoints.py`

| Hàm | Dòng | Vai trò |
|-----|------|---------|
| `save_rack_layout` / `save_block_order` / `load_rack_layout` | 6 / 88 / 130 | Vị trí block trên sơ đồ (`block_id`, `block_index`, `slot_index`) |
| `add_layout_fields` | 236 | Tạo custom field layout (chạy 1 lần) |
| `setup_assignment_field` | 322 | Tạo Custom Field `Shoe Rack.do_not_auto_suggest` (chạy 1 lần) |
| `setup_employee_do_not_suggest_field` | 349 | Tạo `Employee.custom_do_not_suggest_shoe_rack` (chạy 1 lần) |
| `get_today_joiners(date)` | 379 | NV Active vào làm đúng ngày, kèm tủ đang giữ |
| `get_unassigned_employees()` | 443 | NV Active **không** nằm trong ngăn nào (raw SQL `NOT EXISTS`) |
| `_build_slot_pools()` | 487 | Dựng pool ngăn trống (dùng chung suggest + swap) |
| `suggest_shoe_racks(employees)` | 600 | 3 lượt xếp, chỉ tính trong RAM, không ghi DB |
| `assign_shoe_racks(assignments)` | 701 | Ghi `compartment_N_employee`, `rack.save()` chạy qua `validate()` |
| `swap_shoe_rack(...)` | 756 | Tick Unknown ngăn cũ + dời NV sang tủ khác |
| `bulk_set_do_not_suggest_shoe_rack(custom_group, value, active_only)` | 931 | Bật/tắt cờ hàng loạt theo Group. **Có `has_permission("Employee","write")`** |
| `get_employees_by_group(custom_group)` | 970 | Danh sách NV của Group (không lọc Active — để tủ của người đã nghỉ vẫn sáng) |
| `get_left_employees_in_racks()` | 995 | Ngăn còn giữ NV `status = Left` |
| `clear_left_employees_from_racks(items)` | 1068 | Xoá NV đã nghỉ khỏi ngăn |

### `shoe_rack.py`

| Hàm | Dòng | Vai trò |
|-----|------|---------|
| `validate` / `on_update` | 34 / 490 | Hook chính |
| `compute_status` | 87 | Công thức status duy nhất |
| `check_duplicate_assignment` / `release_person_from_rack` | 151 / 212 | Một người = một tủ + auto-reassign |
| `get_evicted_occupants` / `log_reassignments` | 262 / 286 | Audit trail khi import |
| `get_rack_occupants` / `check_mixed_gender` | 324 / 361 | Cảnh báo lệch giới tính |
| `get_gender_mismatch_racks()` | 386 | 2 SQL (Employee + External Personnel), sort theo `name` vì `rack_display_name` sort kiểu chuỗi sẽ ra 1,10,100 |
| `get_unidentified_occupant_racks()` | 441 | Danh sách ngăn đang tick Unknown |
| `bulk_create_racks_by_type` | 526 | Tạo tủ hàng loạt |
| `auto_reset_empty_series` / `force_reset_series` | 629 / 659 | Sửa `tabSeries` |
| `clear_all_assignments(series_prefix)` | 693 | Rút hết người khỏi tủ, **giữ tủ** (xem BUG B4) |
| `clear_unidentified_flags(rack_type, target, dry_run)` | 751 | Bỏ tick Unknown hàng loạt + tính lại status |
| `bulk_delete_and_reset(series_prefix)` | 850 | Xoá sạch 1 series + reset counter |
| `fix_all_rack_status` / `regenerate_all_display_names` | 979 / 1034 | Công cụ sửa dữ liệu |
| `get_available_racks` / `get_empty_racks_in_range` / `bulk_edit_empty_racks` | 1109 / 1140 / 1184 | Truy vấn + sửa hàng loạt tủ trống |
| `sync_racks_to_employees(rack_names, clear_orphans, dry_run)` | 1278 | Đẩy tủ sang `Employee.custom_shoe_rack`; Shoe Rack là nguồn sự thật |

---

## 7. UI ở DocType

### `shoe_rack_list.js` — menu

| Mục | Loại | Hàm |
|-----|------|-----|
| Go To Dashboard | menu | `frappe.set_route('shoe-rack-dashboard')` |
| Bulk Create / Bulk Edit | inner button | `show_bulk_create_dialog` (`:184`) / `show_bulk_edit_dialog` (`:320`) |
| Sync to Employee | inner button | ⚠ **đang bị vô hiệu hoá** — thân hàm bị comment `// temp disable` (`:21`), dialog `show_sync_to_employee_dialog` (`:435`) vẫn còn nguyên |
| Bulk Set: Do Not Suggest Rack (by Group) | menu | `show_bulk_set_do_not_suggest_dialog` (`:874`) |
| Bulk Delete & Reset | menu | `show_bulk_delete_dialog` (`:965`) |
| Reset Empty Series | menu | `auto_reset_empty_series` (`:638`) |
| Clear All Assignments | menu | `show_clear_assignments_dialog` (`:657`) |
| Clear Unknown Flags | menu | `show_clear_unknown_dialog` (`:730`) — có **preview + dry-run**, lọc theo Rack Type và ngăn 1/2/cả hai |
| Fix All Inconsistencies / Fix All Status / Regenerate Display Names | menu | công cụ sửa dữ liệu |

### `shoe_rack.js` — form

- Nút: **Refresh Status**, **Release All** (khi tủ có người), **Find Personnel**.
- Chọn NV vào ngăn ⇒ **tự bỏ tick Unknown** của chính ngăn đó (`compartment_N_employee` handler).
- `update_status_auto()` (`:214`) lặp lại đúng công thức của `compute_status()` — sửa một bên thì
  **phải sửa cả bên kia**.
- `check_left_employees()` gắn description đỏ khi NV trong ngăn đã `status = Left`.

### Quyền

Page `shoe-rack-dashboard` giờ giới hạn **HR User / HR Manager / Administrator**
(`shoe_rack_dashboard.json`). Nhưng xem BUG B6: các endpoint bên dưới vẫn mở.

---

## 8. 🐞 BUG còn tồn đọng (đã đối chiếu lại với code ngày 2026-08-21)

### 🔴 Nghiêm trọng

**B1. `autoAssignAll` / `clearAll` đánh dấu TẤT CẢ pending là thành công dù chỉ một phần thành công**
`jsx:384` và `jsx:477`:
```js
if (data.assigned > 0) {                       // hoặc data.cleared > 0
  setAssignedSet(prev => new Set([...prev, ...pending.map(r => r.employee)]));
}
```
Server trả `assigned = 3` trên `pending = 5` (2 slot bị chiếm → nằm trong `data.errors`), nhưng UI vẫn nạp
**cả 5** vào `assignedSet` → 2 dòng thất bại vẫn hiện "Assigned" và bị đem đi **in nhãn**.
→ *Hướng fix:* server trả về danh sách employee/slot xử lý thành công, FE chỉ add đúng phần tử đó;
hoặc khi có `errors` thì reload lại danh sách từ DB.
*(Cùng lỗi này ở `assignSingle`/`clearSingle` thì vô hại vì chỉ có 1 phần tử.)*

**B2. `get_left_employees_in_racks` bỏ sót tủ chỉ có ngăn 2 bị chiếm** — `api_endpoints.py:1001`
Dùng đồng thời `filters` (comp1 `!= ""` AND comp1 `is set`) **và** `or_filters`. Frappe ghép
`filters AND or_filters`, nên rút gọn thành **"comp1 bắt buộc có giá trị"**. Tủ có
`compartment_1_employee` rỗng nhưng `compartment_2_employee` là NV đã nghỉ → **không bao giờ trả về**,
không thể clear qua UI.
→ *Hướng fix:* bỏ khối `filters`, chỉ giữ `or_filters` (đoạn sau vốn đã lọc lại bằng `left_set`).

### 🟠 Trung bình

**B3. `assign_shoe_racks` không kiểm cờ Unknown và không kiểm External Personnel** — `api_endpoints.py:735`
Chỉ kiểm `compartment_N_employee` đã có giá trị chưa. Một ngăn đang tick
`compartment_N_unidentified = 1` (hoặc đang có External Personnel) vẫn nhận được assign; sau đó
`enforce_unidentified_flags()` **âm thầm bỏ tick Unknown** trong lúc save.
Suggest không bao giờ đề xuất ngăn như vậy, nhưng dòng gợi ý cũ / thao tác tay thì có.
→ *Hướng fix:* kiểm cả 3 nguồn chiếm chỗ như `_build_slot_pools()` đang làm.

**B4. `clear_all_assignments` để lại dữ liệu không nhất quán** — `shoe_rack.py:693`
Ghi thẳng `status = "0/1"|"0/2"` mà **không xét cờ Unknown**, nên tủ đang tick Unknown sẽ có
status `0/2` — trái với `compute_status()` (Unknown tính là đã chiếm). Ngoài ra không xoá
`gender_employee_1` / `employee_2_gender` (giá trị cũ đọng lại) và không đụng `Employee.custom_shoe_rack`.
→ *Hướng fix:* gọi `compute_status()` và xoá luôn 2 field gender (nhớ ghi `""`, không ghi `None`).

**B5. Vào Edit mode lập tức bật `hasUnsavedChanges`** — `jsx:91` + `jsx:887`
`useEffect [isEditMode]` tạo mảng layout mới (`static: false`) mỗi lần vào edit → `GridLayout` mount
và gọi `onLayoutChange` → `handleLayoutChange` chạy dù người dùng chưa kéo gì (guard `if (!isEditMode) return`
chỉ chặn chiều view mode) → nút Cancel hỏi "Discard changes?" oan, hoặc "OK" ghi save thừa.
→ *Hướng fix:* so sánh layout thực sự khác trước khi set cờ, hoặc bỏ qua lần `onLayoutChange` đầu tiên.

**B6. Endpoint vẫn mở cho mọi user đăng nhập** — `api_endpoints.py` (toàn bộ) + phần lớn `shoe_rack.py`
`@frappe.whitelist()` + `ignore_permissions=True`, không kiểm quyền. Chỉ
`bulk_set_do_not_suggest_shoe_rack` có `frappe.has_permission`. Hạn chế role ở Page **không** bảo vệ
được `/api/method/...`: bất kỳ user nào cũng gọi được `assign_shoe_racks`, `clear_all_assignments`,
`bulk_delete_and_reset`…
→ *Hướng fix:* thêm `frappe.has_permission("Shoe Rack", "write")` ở các endpoint ghi.

**B7. View mode thiếu chấm `no-suggest-dot`** — `jsx:1292` (view) so với `jsx:1395` (edit)
Tủ `do_not_auto_suggest` chỉ nhìn thấy được khi vào Edit mode; view mode chỉ có tooltip.
Người dùng thường ở view mode ⇒ gần như không ai thấy cờ này.

**B8. Icon lệch giới tính nạp từ Cloudinary** — `jsx:1023` và `jsx:1122`
`https://res.cloudinary.com/dd6yp2m05/...` — phụ thuộc Internet ngoài. Mạng nhà máy chặn / rớt mạng
⇒ mất icon cảnh báo (chỉ còn ô trống), trong khi `male.png` thì đã import local.
→ *Hướng fix:* đưa file vào `frontend/src/images/` như `male.png`.

### 🟡 Nhẹ / an toàn

**B9. `assignDate` mặc định lệch ngày buổi sáng sớm** — `jsx:48`
`new Date().toISOString().split('T')[0]` trả **ngày UTC**. Với VN (UTC+7), trước 07:00 sáng sẽ ra
**ngày hôm trước** → load nhầm joiners. (Đúng lỗi `toISOString` đã gặp ở module OT/Attendance.)
→ *Hướng fix:* `new Date().toLocaleDateString('en-CA')`.

**B10. Double-render layout khi khởi tạo** — `jsx:137` vs `jsx:768`
`useEffect [racks]` gọi `createBlocksFromRacks(racks)` **không có savedLayout**, trong khi
`loadRackData → loadLayout` cũng gọi bản có savedLayout. Thực tế fetch settings luôn về sau effect
nên layout đã lưu vẫn thắng, nhưng vẫn có **2 lần render + nhấp nháy vị trí mặc định**.
→ *Hướng fix:* bỏ effect `[racks]` (thừa).

**B11. XSS tiềm ẩn khi in nhãn** — `printLabels` (`jsx:516`) nhét `employee_name`, `rack_display_name`
thẳng vào HTML rồi `document.write`. Dữ liệu nội bộ nên rủi ro thấp, nhưng nên escape.

**B12. `getCsrf()` có thể `undefined`** — `jsx:143`. Không có `window.frappe` lẫn `<meta name="csrf-token">`
⇒ header `X-Frappe-CSRF-Token: undefined` → POST fail khó hiểu.

**B13. `Math.max(...savedPathways.map(parseInt…))` có thể ra `NaN`** — `jsx:682`
Nếu một `pathway.id` không đúng dạng `pathway-<số>` → `nextPathwayId = NaN` → pathway mới có id
`pathway-NaN`, các pathway sau đè key.

**B14. Sau Swap không refresh sơ đồ** — `swapRack` (`jsx:285`) cập nhật đúng bảng trong panel, nhưng
status tủ trên sơ đồ nền vẫn cũ cho tới khi bấm **Close & Refresh**.

---

## 9. ✅ Điểm làm tốt

- **Một nguồn sự thật cho status:** `compute_status()` được cả `update_status`, `release_person_from_rack`
  và `clear_unidentified_flags` dùng lại.
- **Auto-reassign có audit:** mọi lượt dời người / đẩy người ra đều được ghi comment + msgprint, và
  lỗi ghi comment **không** làm hỏng dòng import.
- **Suggest và Swap dùng chung `_build_slot_pools()`** ⇒ hai đường không bao giờ lệch tiêu chí.
- **Swap gửi kèm `exclude_slots`** của các dòng khác đang giữ ⇒ 2 người không bị trỏ vào cùng một slot.
- **Chống lệch schema:** mọi field tuỳ chọn đều đọc qua `meta.has_field()` nên site chưa chạy
  `setup_*_field` vẫn không lỗi.
- **Truy vấn gộp:** `get_left_employees_in_racks`, `get_gender_mismatch_racks`, `_build_slot_pools`
  lấy dữ liệu người bằng 1 query, không N+1.
- **`clear_unidentified_flags` có dry-run + preview** trước khi ghi 79 bản ghi.
- **Trạng thái loading/disabled per-row** (`assigningRows`, `swappingRows`, `clearingRows`) tránh double-submit.

---

## 10. 🔧 Đề xuất cải thiện

**Kiến trúc / DRY**
1. **Tách helper gọi API** — gom lặp `fetch + headers + csrf + result.message` (~10 chỗ) về 1 hàm
   (xem mẫu `callFrappeMethod` trong tài liệu `/www` page).
2. **Tách component `<RackCell>`** — khối render tủ lặp gần y hệt giữa view mode (`jsx:1287`) và
   edit mode (`jsx:1376`); chính vì lặp mà sinh ra B7.
3. **Tách `<SidePanel>`** — 3 panel dùng chung khung overlay + table + toolbar.
4. **Đưa CSS nút Gender ra file** — hiện chèn `<style>` inline trong JSX (`jsx:1034-1065`), lệch với
   phần còn lại dùng `ShoeRackLayoutManager.css`.
5. **Hằng số có tên cho magic number 16** (tủ/block) và quy tắc tách letter/number.
6. Xoá rác cùng thư mục: `aaaa` (0 byte), `RackLayoutComplete.jsx` (bản cũ dùng `@dnd-kit`, không còn import).
7. Quyết dứt điểm nút **Sync to Employee**: bật lại hoặc gỡ hẳn cả dialog (~110 dòng code chết).

**Dữ liệu**
8. Dọn 73 tủ còn tick Unknown ở ngăn 2 do lỗi `default = 1` cũ (menu **Clear Unknown Flags**,
   chạy dry-run trước), và 6 tủ vừa có người vừa tick Unknown.
9. Cân nhắc **thêm `do_not_auto_suggest` vào fixtures** để site mới không mất field
   (⚠ đọc `reference_fixtures_import_scans_folder.md` trước khi đụng vào fixtures).
10. Cột `gender` mồ côi trong `tabShoe Rack` — xoá khi có dịp migrate.

---

## 11. Tham chiếu nhanh

| Việc | Vị trí |
|------|--------|
| Chuẩn hoá tên tủ khi tìm kiếm | `normalizeRackQuery` `jsx:10` |
| Giới tính người duy nhất trong tủ 2 ngăn | `getSingleOccupantGender` `jsx:15` |
| Nạp joiners (2 tab) | `applyJoinersResponse` `jsx:146` · `loadTodayJoiners` `jsx:166` · `loadUnassignedEmployees` `jsx:189` |
| Swap chỗ | `swapRack` `jsx:285` |
| Gom block 16 tủ, tách letter/number | `createBlocksFromRacks` `jsx:546` |
| Load / lưu layout (PUT, fallback POST khi 404) | `loadLayout` `jsx:768` · `saveLayout` `jsx:809` |
| Bộ lọc tìm tủ / giới tính / giao nhau | `jsx:948` · `jsx:961` · `jsx:972` |
| Icon cảnh báo giới tính | `renderGenderWarningIcon` `jsx:1013` |
| Render tủ: view mode / edit mode | `jsx:1271` · `jsx:1322` |
| 3 panel | Assign `jsx:1411` · Clear `jsx:1600` · Gender `jsx:1710` |
| Pool ngăn trống / 3 lượt xếp / swap | `api_endpoints.py:487` · `:600` · `:756` |
| Một người = một tủ + auto-reassign | `shoe_rack.py:151` · `:212` |
| Công thức status | `shoe_rack.py:87` (Python) · `shoe_rack.js:214` (JS form) |
| Bulk Clear Unknown Flags | `shoe_rack.py:751` · dialog `shoe_rack_list.js:730` |

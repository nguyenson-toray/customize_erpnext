# Vehicle Management — Hợp đồng giao diện với Zalo Mini App

> **Đây là tài liệu tham chiếu giao diện.** Cách cài đặt, các bẫy đã vấp và quy ước nội bộ
> nằm ở [`README.md`](./README.md) cùng thư mục.
>
> File này gom lại toàn bộ nội dung của 9 file prompt `ERPNEXT_*.md` trước đây ở thư mục
> gốc app (spec ban đầu, hợp đồng API, câu trả lời của đội Mini App, kịch bản dữ liệu test,
> spec trang điều hành, prompt Excel/dashboard). Các file đó **đã xoá**; mọi thứ còn giá trị
> đều ở đây.

---

## 1. Kết nối

```
Base    https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.api.vehicle_management.<method>
Auth    Authorization: token <API_KEY>:<API_SECRET>
OK      HTTP 200,  dữ liệu ở  {"message": ...}
Lỗi     HTTP 417 (ValidationError) · 401 (AuthenticationError) · 403 (sai HTTP method / thiếu quyền)
        thông điệp đọc ở  json.exception  hoặc  json._server_messages
```

**API user dùng chung:** `miniapp@tiqn.com.vn` — System User, **chỉ** role `Vehicle Manager`,
không đặt mật khẩu nên không đăng nhập Desk được.

🔴 **Đừng dùng API key của `Administrator`.** Key nhúng trong client bundle là key công khai;
lộ key Administrator là mất toàn bộ ERP (lương, HR, kho). Đã kiểm: user `miniapp@` không đọc
được `Salary Slip` lẫn `Employee`.

**CORS:** `common_site_config.json` có `allow_cors: "*"` (đặt từ 29/07/2026). Preflight trả
đủ `Access-Control-Allow-Origin` + `Allow-Credentials`.
⚠ `"*"` nghĩa là **mọi website** gọi được API kèm cookie phiên của user đang đăng nhập ERP.
User đã quyết định giữ nguyên (15/09/2026).

Mọi method đổi dữ liệu **phải** gọi bằng `POST`/`PUT`; gọi `GET` trả **403**.

---

## 2. Định dạng — cố định, không thương lượng

| Kiểu | Định dạng | Ví dụ |
|---|---|---|
| Date | `YYYY-MM-DD` | `2026-09-15` |
| Datetime | `YYYY-MM-DD HH:MM:SS` | `2026-09-15 07:28:40` |
| Time (trả về) | `HH:MM` | `06:30` |

**Không có `T`, không có `Z`, không có milliseconds.**

Server **vẫn tự cắt** `T`/`Z`/ms nếu client lỡ gửi ISO (`_normalise_dt_in`), làm lưới an toàn
cho bản Mini App cũ.
🔴 Nó **vứt chữ `Z`, KHÔNG quy đổi múi giờ** — Mini App dựng chuỗi từ giờ VN rồi gắn `Z` cho
có. Ai đó "sửa cho đúng chuẩn" bằng cách quy đổi UTC thật là **mọi giờ check-in lệch 7 tiếng**.

---

## 3. Trạng thái

```
Chuyến   scheduled → confirmed → in_progress → completed
         (mọi trạng thái chưa kết thúc → cancelled)

Yêu cầu  pending → assigned            (tạo chuyến = đã duyệt)
         pending → rejected            (điều hành từ chối)
         pending/approved/assigned → cancelled   (người yêu cầu tự rút)
```

**Chỉ đi MỘT CHIỀU.** Gửi lùi trả HTTP 417.

`approved` chỉ tồn tại cho màn hình Desk; Mini App không sinh ra nhưng phải hiển thị được.
`rejected` (điều hành từ chối) và `cancelled` (người yêu cầu tự rút) là **hai trạng thái
khác nhau** — báo cáo cần phân biệt.

---

## 4. Object chuyến — server LUÔN trả đủ

```json
{
  "name": "TIQN-TRIP-2026-0005",
  "trip_name": "Họp UBND Tỉnh",
  "trip_type": "on_demand",          // fixed | on_demand
  "template_id": null,                // docname TIQN Fixed Trip Schedule nếu là chuyến cố định
  "trip_date": "2026-09-15",
  "depart_time": "09:00",
  "status": "completed",
  "from_location": "Toray VSIP",
  "to_location": "UBND Tỉnh Quảng Ngãi",
  "purpose": "Khám sức khỏe | Nộp hồ sơ",   // ← LÝ DO chuyến, tách khỏi notes
  "dispatcher_note": null,
  "notes": null,
  "route_changed": 0,
  "vehicle": "TIQN-VEH-003",
  "vehicle_name": "Kia",              // ← luôn có khi chuyến đã có xe
  "license_plate": "76H-058.34",      // ← luôn có khi chuyến đã có xe
  "driver": "TIQN-DRV-003",
  "driver_name": "Mr. Duy",           // ← luôn có khi chuyến đã có tài xế
  "driver_phone": "0905...",          // ← luôn có khi chuyến đã có tài xế
  "driver_zalo_user_id": "1234...",   // ← để openChat(); null nếu tài xế chưa mở Mini App
  "km_start": 30140.0,
  "km_end": 30158.0,
  "total_km": 18.0,                   // server tự tính, KHÔNG gửi lên
  "km_start_photo": null, "km_end_photo": null,
  "checkin_time": "2026-09-15 09:05:00",
  "checkout_time": "2026-09-15 11:30:00",
  "checkin_notes": null, "checkout_notes": null,
  "confirmed_at": null, "cancelled_reason": null,
  "additional_cost": 0.0,
  "passengers": [ ... ]               // LUÔN là array
}
```

Kèm theo `creation`, `modified` và 4 field GPS (`start_gps_lat/lng`, `end_gps_lat/lng`) —
GPS luôn `0.0` ở Phase 1, bỏ qua.

---

## 5. Hành khách

Server **trả về**:

```json
{ "passenger_name": "Nguyễn Văn A",
  "from_location": "Toray VSIP",
  "request_id": "TIQN-REQ-2026-0002",
  "order": 1,
  "row_name": "a1b2c3d4e5" }
```

🔴 **`row_name` là mã dòng con, KHÔNG phải tên người.** Trước đây field này tên `name` và đã
gây nhầm: `p.passenger_name || p.name` khi `passenger_name` rỗng sẽ ghi `a1b2c3d4e5` vào ô
tên hành khách.

Khi **gửi lên**, server nhận mọi cách viết (`PASSENGER_ALIASES`):

| Ý nghĩa | Chấp nhận |
|---|---|
| liên kết yêu cầu | `request_id` · `requestId` · `request` |
| tên hành khách | `passenger_name` · `passengerName` · `name` |
| điểm đón | `from_location` · `fromLocation` · `pickup_location` · `pickupLocation` |
| thứ tự | `order` · `pickup_order` · `pickupOrder` |

`passenger_name` bắt buộc; thiếu thì server lấy `employee_name` của yêu cầu được link, hết
cách mới báo lỗi **kèm số thứ tự dòng**. Mỗi lần gửi `passengers` là **thay thế toàn bộ**.

---

## 6. Luật server ép

| Luật | Vi phạm |
|---|---|
| `km_end > km_start` | 417 |
| `km_start` ≥ `km_end` chuyến **completed cùng xe cùng ngày** | 417, thông điệp nêu tên chuyến trước |
| Trạng thái chỉ đi một chiều | 417 |
| Từ chối yêu cầu phải có `rejection_reason` | 417 |
| Đặt yêu cầu `assigned` phải kèm `assigned_trip` | 417 |
| Sửa **nội dung** yêu cầu chỉ khi còn `pending` | 417 |
| `return_time` phải sau `request_time` | 417 |
| Xe không có tài xế active nào | MandatoryError |

**Nội dung yêu cầu** = `from_location`, `to_location`, `request_time`, `return_time`,
`purpose`, `passenger_count`, `notes`, `employee_name`, `employee_id_display`, `zalo_user_id`.
Field **workflow** (`status`, `rejection_reason`, `assigned_trip`) vẫn sửa được ở mọi trạng
thái, nên hủy một chuyến đã xếp vẫn làm được.

Field **dẫn xuất** (`total_km`, `confirmed_at`, `template_id`) gửi lên sẽ bị từ chối.

🔴 **Mô hình tính tiền:** xe và tài xế là của công ty đối tác, TIQN trả theo **số km thực tế
từng chuyến**. Nên **hụt** km giữa hai chuyến = vô hại (đối tác chạy việc riêng); **đè** km
(`km_start` < `km_end` chuyến trước) = **trả tiền hai lần**. Server chặn "đè" trong cùng
ngày; qua ngày cố ý không chặn (sẽ cản nhập bù chuyến cũ) nhưng `verify()` có kiểm.

---

## 7. Danh sách endpoint

| Nhóm | Method | HTTP |
|---|---|---|
| Auth | `get_user_by_zalo_id(zalo_user_id)` — chưa map thì trả `null`, KHÔNG ném lỗi | GET |
| | `verify_driver_login(driver_name, password)` | POST |
| | `get_drivers()` | GET |
| | `update_zalo_user_id(role, doc_name, zalo_user_id)` | POST |
| | `decode_phone_token(phone_token, access_token, zalo_user_id?)` | **POST** |
| | `update_zalo_id_by_oa(zalo_user_id, id_by_oa)` | POST |
| Chuyến | `get_trips(date?, vehicle?, driver?, status?, limit?)` | GET |
| | `get_trip(name)` · `get_today_trips_by_driver(driver_name, date?)` | GET |
| | `get_last_completed_trip_by_vehicle(vehicle, date?)` | GET |
| | `get_fixed_templates_for_driver(driver_name, trip_date?)` | GET |
| | `create_trip(...)` · `create_trip_from_template(template_name, trip_date?)` | POST |
| | `update_trip(name, **fields)` · `confirm_trip` · `cancel_trip` | POST/PUT |
| | `update_trip_route` · `acknowledge_route_change` | POST/PUT |
| | `checkin_trip` · `checkout_trip` | POST/PUT |
| Yêu cầu | `get_requests(status?, employee_id?)` · `get_my_requests(zalo_user_id)` · `get_request(name)` | GET |
| | `create_request(...)` · `update_request(name, **fields)` | POST |
| | `approve_request` · `reject_request` · `assign_request_to_trip` · `combine_requests_to_trip` | POST/PUT |
| Xe | `get_vehicles()` · `get_vehicle(name)` · `get_vehicle_status()` | GET |
| | `update_vehicle(name, **fields)` · `update_vehicle_status(vehicle, status)` | POST/PUT |
| Báo cáo | `get_today_stats(date?)` · `get_trip_report(start_date, end_date, vehicle?, driver?)` | GET |
| | `get_dispatch_overview(date?)` — gộp toàn bộ panel vào 1 request | GET |
| | `download_trip_report_excel(start_date, end_date, vehicle?, driver?)` | GET |

`create_trip_from_template` **idempotent**: gọi lại trong cùng ngày trả đúng chuyến cũ.

`driver` là **tuỳ chọn** ở `create_trip` / `combine_requests_to_trip` — controller tự điền
tài xế mặc định của xe. Truyền vào chỉ khi muốn đè (chạy thay ca).

### Đăng nhập tài xế (Phase 1)

Sai mật khẩu **5 lần** → khoá tài xế đó **15 phút**. Tên tài xế sai và mật khẩu sai trả
**cùng một thông điệp** (cố ý, để không lộ danh sách).

🔴 **`Password` fieldtype MÃ HOÁ, KHÔNG băm.** Frappe lưu `__Auth` với `encrypted=1` (Fernet,
giải mã ngược được); `check_password()` chỉ khớp dòng `encrypted=0` nên **không bao giờ**
verify được field này — phải dùng `doc.get_password()`. Cột trong bảng chứa `"*" * độ_dài`
⇒ **select field đó là lộ độ dài mật khẩu**.

### Lọc yêu cầu theo nhân viên

```
GET .../get_requests?employee_id=EMP004            → chỉ yêu cầu của EMP004
GET .../get_requests?status=pending                → cả hàng đợi (màn Dispatcher)
GET .../get_requests?status=pending&employee_id=EMP004   → kết hợp
```

Không truyền `employee_id` thì trả toàn bộ — hành vi cũ, **không breaking change**.
Nhận cả `employee_id` lẫn `employee_id_display`.

🔴 **Key mã nhân viên trong payload là `employee_id_display`, KHÔNG phải `employee_id`.**
`employee_id` chỉ là tên **tham số lọc**. Client đọc nhầm sang `employee_id` sẽ thấy
`undefined` và lịch sử trống — đúng triệu chứng đã gặp.

⚠ **Đây là bộ lọc tiện dụng, KHÔNG phải ranh giới phân quyền.** Mọi bản Mini App dùng
**chung một API key**, nên ai cầm key đó chỉ cần đổi mã trong tham số là đọc được yêu cầu
của người khác. Server ở Phase 1 không có cách nào phân biệt hai người yêu cầu.

Muốn cô lập thật thì phải có **danh tính phía server**: Phase 2 ánh xạ Zalo user → nhân
viên qua `TIQN Zalo Role Map`, và bộ lọc phải **suy ra từ phiên đăng nhập** chứ không tin
tham số client gửi lên. `get_my_requests(zalo_user_id)` hiện cũng đúng hạn chế này.

### `decode_phone_token` — đổi token của Zalo lấy SĐT thật

Zalo `getPhoneNumber()` trả **token**, không phải số. Server đổi hộ qua
`https://graph.zalo.me/v2.0/me/info`.

```
POST .../decode_phone_token
    phone_token=<code từ getPhoneNumber>
    access_token=<access token của phiên Mini App>
    zalo_user_id=<tuỳ chọn>

→ { "phone": "+84-962200089",
    "phone_local": "0962200089",
    "raw": "84962200089",
    "saved_to": "zalo-user-123" | null }
```

🔴 **POST, không phải GET.** Endpoint này ghi. GET sẽ bị `sync_database()` rollback đúng
như sự cố Excel 21/09 — ghi xong rồi mất, không lỗi gì.

**Truyền `zalo_user_id` thì server tự lưu vào `TIQN Zalo Role Map.phone`** (field đã có sẵn,
kiểu Phone) và trả `saved_to`. Nên dùng cách này thay vì bước 4 trong đề bài (client nhận số
rồi gọi REST API ghi lại): một SĐT đã giải mã không cần đi ra client rồi quay vào chỉ để được
lưu. Bản ghi Role Map **phải tồn tại trước**; server không tự tạo, vì `role` là quyết định
của người quản trị chứ không phải của client.

⚠ **Dùng `phone_local` để đối chiếu, không dùng `phone`.** `TIQN Driver.phone` lưu dạng nội
địa `"0905…"`; so bằng `"+84-…"` thì không bao giờ khớp, và lỗi chỉ lộ ra rất muộn dưới dạng
"không tìm thấy tài xế". `phone` là định dạng Mini App yêu cầu, giữ nguyên.

🔴 **Token dùng MỘT lần, hết hạn sau 2 PHÚT** (tài liệu Zalo). Gọi `decode_phone_token`
ngay sau `getPhoneNumber()`; **đừng thử lại cùng một token** — lần hai luôn ra lỗi 119.

**Bảng mã lỗi Zalo** (docs.zaloplatforms.com/docs/MA/api/errorCode) — server đã dịch sẵn
thành câu nói rõ *lỗi của ai*, vì lời gốc của Zalo không nói:

| Mã | Zalo nói | Thực chất | Ai sửa |
|---|---|---|---|
| 116 | secret_key is empty | thiếu khoá trong site_config.json | **server** |
| 117 | secret_key is invalid | khoá không hợp lệ | **server** |
| 118 | code is invalid | ⚠ khoá **hợp lệ nhưng của SAI ứng dụng** | **server** |
| 114 | code is empty | không gửi token | client |
| 115 | code is invalid | token hỏng | client |
| 119 | code has already been used | token đã dùng / quá 2 phút | client, lấy token mới |
| −1401 | User Authentication Required | user chưa cấp quyền | user |

⚠ **118 dễ hiểu nhầm nhất**: đọc "code is invalid" ai cũng đi lùng Mini App, nhưng nó có
nghĩa **token thuộc về một Zalo App khác với app của secret key**. Server trả riêng câu nói
rõ điều đó.

**Cấu hình bắt buộc** — `sites/erp.tiqn.local/site_config.json`:

```json
{ "zalo_app_vehicle_management_secret_key": "<secret key từ Zalo Developer Dashboard>" }
```

Khoá lấy ở **developers.zalo.me → Quản lý ứng dụng** của đúng Zalo App mà Mini App thuộc về
(KHÔNG phải secret của OA, KHÔNG phải Mini App ID), rồi `bench restart`.

**Chưa có khoá thì endpoint báo lỗi rõ ràng**, không gửi placeholder sang Zalo (đề bài gợi ý
fallback `"YOUR_ZALO_APP_SECRET_KEY"` — làm thế thì Zalo trả lỗi chung chung và không ai biết
là do thiếu cấu hình).
🔴 Khoá này **không được nằm trong source**: repo này ở git, và `app/public/` phục vụ công
khai không cần đăng nhập.

Lỗi mạng/timeout trả message trung tính; chi tiết vào Error Log. Cố ý: thông điệp lỗi của
`requests` có thể in lại header của request, mà header đó mang chính secret key.

### Trạng thái xe: bốn còn ba (23/09)

```
available · in_trip · not_available
```

`maintenance` và `broken` **đã bỏ**, gộp thành `not_available`. Xe là của đối tác: TIQN không
theo dõi bảo dưỡng hay hư hỏng, chỉ cần biết xếp được hay không.

`update_vehicle_status()` chỉ nhận **`available`** và **`not_available`** — `in_trip` do hệ
thống tự đặt. Gửi giá trị cũ trả `ValidationError`.

### 🔴 Chuyến gán theo XE, không gán cho người (23/09)

`TIQN Vehicle Trip` **không còn field `driver`**. Xe là đơn vị; tài xế xe nào thì thấy chuyến
của xe đó.

Payload **vẫn có** `driver`, `driver_name`, `driver_phone`, `driver_zalo_user_id`,
`driver_zalo_id_by_oa` — nhưng là **giá trị suy ra từ xe lúc đọc**. Client không phải đổi gì
khi hiển thị.

* `create_trip()` và `combine_requests_to_trip()` **không còn nhận tham số `driver`** (gửi lên
  bị bỏ qua).
* `get_trips(driver=…)` và `get_today_trips_by_driver(…)` vẫn dùng như cũ — server dịch sang
  lọc theo xe. Tài xế chưa được gán xe thì trả **rỗng**, không trả hết.
* Đổi tài xế của một xe là mọi chuyến của xe đó đổi theo ngay, kể cả chuyến cũ.

**Bỏ:** `summary.km_by_driver` và cột Driver trong report KM. Suy từ xe trả lời đúng câu hỏi
*bây giờ*, nhưng sai câu hỏi *lúc đó* — tài xế đổi xe là lịch sử km bị viết lại. `km_by_vehicle`
và `summary.vehicles` không đổi.

**Bỏ:** field `confirmed_at` trên chuyến (chỉ ghi, không ai đọc). Trạng thái `confirmed` vẫn còn.

### 🔴 `TIQN Driver` đã bỏ — tài xế LÀ một tài khoản Zalo (23/09)

`driver` trong object chuyến giờ là **docname của `TIQN Zalo Role Map`**, tức chính
**Zalo user ID**. Tên hiển thị vẫn ở `driver_name` như cũ.

```json
{ "driver": "9110000000000000001",
  "driver_name": "Mr. Lương",
  "driver_zalo_user_id": "9110000000000000001",
  "driver_zalo_id_by_oa": null }
```

Tài xế = bản ghi Role Map có `role = driver` và một `vehicle` được gán. Mọi tài khoản vào app
lần đầu là `requester`; quản lý nâng vai trò.

**`get_drivers()` giữ nguyên hình dạng cũ** — vẫn có `driver_name`, `assigned_vehicle`,
`assigned_vehicle_name`, `is_active`. Client không phải đổi gì ở đây.

### ❌ `verify_driver_login()` đã xoá

Không còn đăng nhập bằng tên + mật khẩu. **`get_user_by_zalo_id()` chính là đăng nhập**: nó
trả `role`, và với tài xế thì kèm `vehicle`, `vehicle_name`, `license_plate`, `is_leader`.

Tài khoản bị chặn (`disabled`) trả **`null`** y như chưa map — Mini App xử lý `null` giống
trường hợp người dùng mới.

### 🔴 Chuyến gộp có ĐÚNG MỘT điểm đến (23/09)

`to_location` là điểm đến của **yêu cầu đầu tiên**, hoặc giá trị bạn truyền vào. Mọi điểm đến
khác trong các yêu cầu được gộp đi vào **`dispatcher_note`**:

```
to_location     = "Sân bay Chu Lai"
dispatcher_note = "Ghé thêm: Ga Quảng Ngãi, Cảng Dung Quất"
```

Dispatcher gõ ghi chú riêng thì điểm đến đứng **trước**, ghi chú xuống dòng dưới.

⚠ **ĐỪNG nối nhiều nơi vào `to_location`** kiểu `"Sân bay Chu Lai | Ga Quảng Ngãi"`. Field đó
bị so khớp, lọc và gom nhóm trong báo cáo KM — một chuỗi nối lại thành **một địa điểm không
hề tồn tại**, và mọi thống kê theo điểm đến đều sai.

⚠ **Mini App phải hiển thị `dispatcher_note` trên thẻ chuyến.** Từ nay nó mang thông tin tài
xế bắt buộc phải đọc, không còn chỉ là ghi chú tuỳ ý.

### ❌ Bảng `stops` đã bỏ hẳn

`TIQN Trip Stop` và field `stops` **không còn tồn tại**. Object chuyến không còn khoá `stops`.
Client cũ còn gửi `stops` thì server lặng lẽ bỏ qua, không lỗi.

Không cần nó: **mỗi dòng hành khách đã mang điểm đón riêng** (`passengers[].from_location`,
lấy từ chính yêu cầu), và điểm đến phụ nằm ở `dispatcher_note`.

### Tên chuyến: chỉ lộ trình

`trip_name` sinh tự động giờ là `"Toray VSIP → Sân bay Chu Lai"` — **không còn giờ và ngày**.
Cả hai đã có cột riêng (`depart_time`, `trip_date`) và luôn hiện cạnh tên. Tên do bạn tự đặt
thì giữ nguyên.

### `purpose` — lý do chuyến, KHÔNG phải `notes`

`purpose` là **lý do đi**, đi vào cột *Mục đích* của báo cáo KM. `notes` là ghi chú tự do.
Hai field khác nhau; gửi lý do vào `notes` thì báo cáo trống.

`create_trip`, `update_trip` và `combine_requests_to_trip` đều nhận `purpose`, và
`get_trip` / `get_trips` / `get_today_trips_by_driver` đều trả về.

`combine_requests_to_trip` **không** cần `purpose`: bỏ trống thì server gom lý do của chính
các yêu cầu được ghép, nối bằng `" | "`, **khử trùng** (3 người cùng đi khám sức khỏe ra một
cụm, không phải ba) và bỏ dòng rỗng. Dispatcher gõ `purpose` thì bản gõ tay thắng.

⚠ **Chuyến CŨ có `purpose = null`** — field mới, không backfill. Cột *Mục đích* trong Excel
sẽ trống cho toàn bộ dữ liệu tháng 9 hiện có.

⚠ `combine_requests_to_trip` **không nhận `passengers`**. Hành khách được suy ra từ
`request_names`, vì chính dòng hành khách mang link tới yêu cầu mà server dựa vào để đẩy yêu
cầu sang `assigned` và trả về `approved` nếu chuyến bị huỷ. Gửi danh sách hành khách riêng sẽ
cắt đứt liên kết đó.

⚠ Yêu cầu được ghép chuyển sang **`assigned`**, KHÔNG phải `approved`. `approved` nghĩa là
"đã duyệt, chưa có xe"; `assigned` là "đã có chuyến". Chuyến huỷ thì chúng quay về `approved`.

### `is_leader` — hiện tab Báo cáo

`TIQN Driver.is_leader` (Check). `get_drivers()` và `verify_driver_login()` đều trả về.

⚠ Đây là **gợi ý UI, không phải phân quyền**. Ẩn tab không chặn được gì: các endpoint báo cáo
vẫn đọc được bằng chính API key dùng chung nằm trong Mini App.

### Zalo User ID — để openChat()

| Ai | Đọc ở đâu | Ghi bằng |
|---|---|---|
| Người yêu cầu | `get_requests()[].zalo_user_id` | `update_zalo_user_id("requester", <tên yêu cầu>, id)` |
| Tài xế của chuyến | `get_trips()[].driver_zalo_user_id` | `update_zalo_user_id("driver", <TIQN-DRV-…>, id)` |
| Điều hành | `verify_driver_login().dispatcher_zalo_id` | bản ghi `TIQN Zalo Role Map` có `role = dispatcher` **và** `id_by_oa` |
| SĐT thật | `get_user_by_zalo_id().phone` | `decode_phone_token(..., zalo_user_id)` |

`dispatcher_zalo_id` đọc từ `TIQN Zalo Role Map`, **không hardcode** — người điều hành sẽ đổi.
Bảng đó **đang rỗng** ⇒ hiện trả `null`; Mini App phải ẩn nút chat thay vì mở chat với rỗng.

`get_drivers()` **cố tình KHÔNG trả `zalo_user_id`**: nó liệt kê *mọi* tài xế cho bất kỳ ai
cầm API key. `driver_zalo_user_id` chỉ lộ tài xế của đúng chuyến đang xem.

⚠ `update_zalo_user_id` **không chứng minh được người gọi sở hữu id đó**. Cùng lỗ hổng API key
dùng chung như `get_requests`. `role` chỉ nhận 3 giá trị `driver` / `requester` / `dispatcher`;
mọi tên doctype khác bị từ chối.

### 🔴 `zalo_user_id` KHÔNG mở được chat — phải dùng `id_by_oa`

`getUserInfo()` trả **hai** id và chúng không thay thế nhau được:

| | Là gì | Dùng cho openChat? |
|---|---|---|
| `id` → `zalo_user_id` | app-scoped | **KHÔNG** |
| `idByOA` → `id_by_oa` | theo Official Account | **CÓ** |

Đây là đính chính cho vòng trước: mọi chỗ tôi trả `zalo_user_id` "để openChat" đều **sai loại
id**. Nó trông như một id hợp lệ, và nó *là* id hợp lệ — chỉ không phải cho việc mở chat, nên
hỏng ra thành "bấm nút chat không thấy gì" mà không có lỗi nào để lần.

Field mới: **`TIQN Zalo Role Map.id_by_oa`** (Data) — cần `bench migrate`, đã chạy.

```
POST .../update_zalo_id_by_oa   zalo_user_id=… & id_by_oa=…
→ { "name": "...", "zalo_user_id": "...", "id_by_oa": "..." }
```

Hoặc `PUT /api/resource/TIQN Zalo Role Map/<name>` như kế hoạch của Mini App — key đã có
quyền ghi. Endpoint riêng tồn tại để có một đường ghi **đúng một field**, không đổi được
`role` như đường REST chung.

Đọc ra ở: `get_user_by_zalo_id().id_by_oa` · `get_trips()[].driver_zalo_id_by_oa` ·
`verify_driver_login().dispatcher_zalo_id`.

🔴 **`dispatcher_zalo_id` giờ trả `id_by_oa`, và KHÔNG rơi về `zalo_user_id` khi trống.**
Nút chat biến mất thì thành thật; nút chat bấm không ra gì là lỗi không ai tái hiện nổi.
`driver_zalo_id_by_oa` cũng vậy — tài xế chưa map thì `null`, không mượn tạm id của ai.

⚠ `id_by_oa` chỉ có giá trị khi **Mini App đã được OA xác thực**, hoặc **user đã follow OA**
liên kết. Trống là chuyện bình thường, không phải lỗi.

### `summary.vehicles` — xác nhận hình dạng (hỏi 22/09)

**Đúng, là một ARRAY.** `km_by_vehicle` vẫn là object và **không đổi**, dùng song song được.

```json
"vehicles": [
  { "vehicle": "TIQN-VEH-003", "name": "Kia",
    "license_plate": "76H 058.34", "km": 2175.0, "trips": 63 }
]
```

`vehicle` = docname (str) · `name`, `license_plate` = str · `km` = float · `trips` = int.
Khoá theo **docname** nên hai xe trùng tên không bị cộng dồn — điều `km_by_vehicle` không
làm được. Sắp **giảm dần theo km**.

⚠ **`trips` chỉ đếm chuyến CÓ km**, không phải mọi chuyến. Đo trên tháng 9:
`total_trips = 271` nhưng `sum(vehicles[].trips) = 183` (= số chuyến `completed`). Chuyến
huỷ và chuyến chưa chạy không có km nên không vào đây. Đừng dùng `trips` để đối chiếu với
`total_trips`. Tổng `km` thì khớp chính xác với `km_by_vehicle`.

⚠ Xe **không chạy km nào** trong khoảng ngày sẽ **không xuất hiện** trong mảng (cũng không
có trong `km_by_vehicle`). Biểu đồ phải chịu được danh sách thiếu xe.

### Sửa nội dung yêu cầu: chỉ khi `pending`

Nội dung chuyến đi (`from_location`, `to_location`, `request_time`, `return_time`, `purpose`,
`passenger_count`, `notes`, thông tin người yêu cầu) **đóng băng ngay khi trạng thái rời khỏi
`pending`** — bao gồm cả `approved`, không chỉ `assigned`.

Điều hành đã bấm duyệt dựa trên nội dung họ đọc; cho sửa sau đó, im lặng, làm chữ ký duyệt
thành vô nghĩa. `approved` lại là trạng thái chỉ sinh ra từ Desk (Mini App đi thẳng
`pending → assigned`) nên trong thực tế gần như không gặp.

Field **quy trình** (`status`, `rejection_reason`, `assigned_trip`) vẫn đổi được ở mọi trạng
thái.

⚠ Ngoại lệ có chủ ý: **sửa nội dung + huỷ trong CÙNG một lần gọi vẫn chạy.** Server đọc trạng
thái **trước khi lưu**, nên `update_request(name, notes="đổi ý", status="cancelled")` trên một
yêu cầu đang `pending` được chấp nhận trọn vẹn.

Luật nằm ở controller nên `PUT /api/resource/...` cũng dính, không riêng `update_request()`.

### Excel

`download_trip_report_excel` trả `{url, absolute_url, filename, is_private, row_count,
expires_in_minutes}`. File **public**, **tự xoá sau 45 phút**.

🔴 **Nguyên nhân thật của "link có mà file không có" (sửa 21/09/2026).**
Endpoint này **GHI** (tạo bản ghi `File`). Frappe **rollback mọi request có HTTP method
"an toàn"** — GET/HEAD/OPTIONS — ở `frappe/app.py: sync_database()`, và `File.on_rollback()`
**xoá luôn file vừa ghi trên đĩa**. Nên một lời gọi GET vẫn dựng file, vẫn trả URL đúng, rồi
xoá file trước khi response rời server. Không có lỗi nào trong log.

Đã sửa phía server (`frappe.local.flags.commit = True`), **Mini App không phải đổi gì**.
Nhưng **gọi bằng POST vẫn đúng hơn** — đây là endpoint có ghi, GET chỉ còn được chấp nhận vì
tương thích ngược.

⚠ Dấu hiệu nhận biết nếu tái diễn: bản ghi `File` **cũng không có trong DB**. Đó là rollback,
không phải chuyện đĩa hay job dọn dẹp. Job dọn chỉ xoá file **quá 45 phút**, nên file vừa tạo
2 phút mà mất thì không bao giờ là do nó.

⚠ **Dùng `absolute_url`, đừng dùng `url`.** `url` là đường dẫn tương đối (`/files/…`); mở nó
trong webview Zalo thì trình duyệt resolve theo origin của **Mini App**, không phải ERPNext,
và ra 404. Đây là lỗi thứ HAI, độc lập với lỗi trên.

Cột: Ngày · Xe · Biển số · Tài xế · Giờ đi · Giờ về · Điểm đi · Điểm đến · **Mục đích** ·
KM đầu · KM cuối · KM tính tiền · Chi phí phát sinh · Trạng thái · Ghi chú. Dòng TOTAL dùng
công thức `=SUM()` thật.

---

### `get_trip_report` — nhánh `vehicles` kèm biển số

`summary.km_by_vehicle` **giữ nguyên** `{"Tên xe": km}` (không đổi, Mini App đang đọc).

Thêm `summary.vehicles`, cùng số liệu nhưng đủ thông tin và sắp giảm dần theo km:

```json
"vehicles": [
  { "vehicle": "TIQN-VEH-003", "name": "Kia", "license_plate": "76H 058.34",
    "km": 3030.0, "trips": 83 }
]
```

Khoá theo **docname** chứ không phải tên hiển thị, nên hai xe trùng tên không bị cộng dồn vào
nhau — điều mà `km_by_vehicle` không làm được.

---

## 8. Chuyến cố định do SERVER tạo

Cron `*/5 * * * *` sinh chuyến từ `TIQN Fixed Trip Schedule`. Tài xế mở app là thấy sẵn,
**không cần bấm gì**.

🔴 **Chuyến chỉ xuất hiện TRƯỚC GIỜ ĐI 15 PHÚT**, không tạo sẵn từ sáng cho cả ngày
(`SCHEDULE_LEAD_MINUTES = 15`). Một chuyến 17:15 nằm trên bảng từ 6 giờ sáng trông y như một
chuyến đang cần xử lý — điều hành không phân biệt được với chuyến sắp chạy thật.

⚠ Nghĩa là: Mini App gọi `get_fixed_templates_for_driver()` lúc 8 giờ sáng sẽ thấy lịch chiều
với `trip = null`. Đó là **bình thường**, không phải lỗi — chuyến sẽ tự có lúc 17:00. Tài xế
muốn đi sớm thì `create_trip_from_template()` vẫn tạo được ngay (idempotent).

**Timezone:** Frappe chấm cron bằng `now_datetime()` = **giờ site**, không phải UTC. Đã kiểm
`System Settings.time_zone = Asia/Ho_Chi_Minh` và đồng hồ máy chủ khớp ⇒ `30 6 * * *` đúng là
06:30 giờ VN.
🔴 Cờ đó **hay tự lật về `Asia/Kolkata`** trên site này — chuyến cố định trễ ~1,5 tiếng thì
kiểm chỗ đó TRƯỚC.

---

## 9. Định nghĩa 4 KPI — đã chốt với đội Mini App (15/09/2026)

| KPI | Công thức |
|---|---|
| **Chờ duyệt** | yêu cầu `pending`, **KHÔNG lọc ngày** |
| **Đã xếp xe** | chuyến `scheduled` + `confirmed`, lọc theo ngày đang xem |
| **Đang chạy** | chuyến `in_progress`, lọc theo ngày đang xem |
| **Hoàn thành** | chuyến `completed` **chỉ**, không tính `cancelled` |

Màu dùng chung với Mini App: `#FFA500` · `#0068FF` · `#00C851` · `#666`.

"Chờ duyệt" không lọc ngày là cố ý: một yêu cầu nộp hôm qua chưa ai trả lời mà qua nửa đêm
biến mất khỏi hàng đợi thì sẽ treo vĩnh viễn.

`get_dispatch_overview` còn trả `minutes_until` cho mỗi yêu cầu chờ duyệt (âm = quá giờ),
**tính ở server** để không lệ thuộc đồng hồ trình duyệt.

---

## 10. Các quyết định đã chốt

| Câu hỏi | Trả lời |
|---|---|
| Mini App có sinh `approved`? | Không. Xếp xe = duyệt. Vẫn phải hiển thị được nếu gặp. |
| Server chặn tài xế chạy 2 chuyến cùng lúc? | **Không.** Mini App chặn phía client. |
| Giới hạn chênh lệch `km_start`? | Không. Chỉ cần không nhỏ hơn `km_end` chuyến trước cùng ngày. |
| GPS + Zalo User ID | Phase 2, chưa có kế hoạch. Cột và `TIQN Zalo Role Map` vẫn còn trong schema, chỉ đóng cửa ở API. |
| Siết liên tục KM qua ngày? | Không cần — xem mô hình tính tiền ở mục 6. |

---

### ❌ `send_email_notification` KHÔNG tồn tại và sẽ không được viết

Đề bài liệt kê nó trong nhóm "API hiện có mà Mini App đang gọi". Nó **chưa bao giờ có**, và
sẽ không có ở dạng đó.

`send_email_notification(recipients, subject, message)` nhận **người nhận, tiêu đề và nội
dung tuỳ ý từ client**. Mọi bản Mini App dùng **chung một API key** nằm trong chính file
client, nên endpoint đó biến máy chủ mail của TIQN thành **relay mở**: ai lấy được key là gửi
được mail tới bất kỳ địa chỉ nào, với nội dung bất kỳ, mang tên miền công ty. Đó là công cụ
lừa đảo sẵn dùng, không phải tính năng thông báo.

Đã có tiền lệ trong chính app này: 04/08/2026, một Notification bật sẵn với
`receiver_by_role: "HR Manager"` nở ra 11 người và **154 email thật bay đi** trong khi nội
dung còn chưa chốt. Mail đã gửi thì không thu hồi được.

**Cách làm đúng, nếu thật sự cần báo:**

| Cần gì | Dùng gì |
|---|---|
| Báo trong app (đã có, đang chạy) | realtime `tiqn_vehicle_dispatch_update` |
| Báo cho tài xế qua Zalo | ZNS — `utils/zns.py`, đã viết, đang TẮT |
| Mail theo sự kiện | DocType `Notification` của Frappe: mẫu **cố định**, người nhận do quản trị viên chọn trong Desk, client không quyết định gì |

Nếu vẫn cần một endpoint, nó phải là dạng `notify_dispatcher(trip_name, reason)`: **không có
tham số `recipients`**, người nhận suy từ cấu hình phía server, nội dung từ mẫu cố định. Nói
rõ yêu cầu nghiệp vụ thì viết được.

---

### ⚠ Docname tài xế đã đổi (21/09/2026)

Tài xế giờ có docname **chính là tên hiển thị**: `Mr. Lương`, `Mr. Long`, `Mr. Duy` — không
còn `TIQN-DRV-001/002/003`. Mọi chỗ Mini App hardcode mã cũ sẽ hỏng. `driver` trong object
chuyến và tham số `driver_name` của `get_today_trips_by_driver` đều là docname này.

Nhân tiện: **đừng dò bằng `GET /api/resource/TIQN Zalo Role Map/<id>`.** Chưa map thì Frappe
ném lỗi và ghi Error Log (đang có 10 bản ghi rác như vậy). Dùng `get_user_by_zalo_id`, nó trả
`null` gọn gàng.

---

## 11. Việc còn treo

- 🔴 **`TIQN Zalo Role Map` đang 0 bản ghi** ⇒ `verify_driver_login().dispatcher_zalo_id`
  luôn `null` và tài xế không chat được với điều hành. Cần **1 bản ghi** `role = dispatcher`
  kèm Zalo ID thật của người điều hành. Đây là việc nhập liệu, không phải việc code.
- **`TIQN Driver.zalo_user_id` đang trống** cho mọi tài xế — sẽ tự đầy khi Mini App gọi
  `update_zalo_user_id` lúc tài xế đăng nhập lần đầu.
- **`TIQN Driver.is_leader` đang 0 cho mọi tài xế** — cần tick tay ai là tổ trưởng, nếu không
  không ai thấy tab Báo cáo.
- 🔴 **`zalo_app_vehicle_management_secret_key` đã cấu hình nhưng Zalo TỪ CHỐI**: `error 117 - secret_key is
  invalid` (14:16 ngày 21/09, token thật từ Mini App). Khoá đúng hình dạng (32 ký tự hex,
  không khoảng trắng thừa) nhưng **không phải khoá của đúng ứng dụng Zalo**. Lấy lại ở
  `developers.zalo.me` → App của Mini App → **App Secret Key** (KHÔNG phải secret của OA,
  KHÔNG phải Mini App ID), thay vào `site_config.json` rồi `bench restart`.
  ⚠ **Không thể tự kiểm bằng token giả**: Zalo xác thực *session trước, secret key sau*, nên
  token bịa luôn trả `"Session key invalid"` dù khoá đúng hay sai. Chỉ một lượt gọi thật từ
  `getPhoneNumber()` mới phân biệt được.
- **Chuyến cũ `purpose = null`**: cột Mục đích trong Excel trống với dữ liệu tháng 9 hiện có.
  Backfill từ yêu cầu liên kết được, nhưng chưa làm vì đụng vào dữ liệu đã có.
- **Role `Vehicle Dispatcher` chưa tạo.** Muốn tách vai thì phải thêm DocPerm cho 8 DocType.
- **ZNS (`utils/zns.py`) đang TẮT hoàn toàn** — `dry_run=True`, không chỗ nào gọi, cần 3 khoá
  trong `site_config.json` mới gửi thật.
- **Desktop icon `System Mindmap`** của app không hiện vì thiếu Workspace Sidebar cùng tên
  (xem README mục 22) — có sẵn từ trước, chưa xử lý.

---

## 12. Cách tự kiểm hai bên đã khớp

```bash
GET .../get_trips?date=<một ngày có dữ liệu>
#  1. mọi chuyến có vehicle_name / driver_name / license_plate, không null
#  2. depart_time dạng "06:30", không phải "6:30:00"
#  3. passengers là array, phần tử có passenger_name / from_location / request_id / order
#  4. datetime dạng "YYYY-MM-DD HH:MM:SS", không T, không Z, không ms
```

Đầy đủ hơn:

```bash
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_test_data.verify
```

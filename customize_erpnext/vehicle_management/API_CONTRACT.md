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
  "dispatcher_note": null,
  "notes": null,
  "route_changed": 0,
  "vehicle": "TIQN-VEH-003",
  "vehicle_name": "Kia",              // ← luôn có khi chuyến đã có xe
  "license_plate": "76H-058.34",      // ← luôn có khi chuyến đã có xe
  "driver": "TIQN-DRV-003",
  "driver_name": "Mr. Duy",           // ← luôn có khi chuyến đã có tài xế
  "km_start": 30140.0,
  "km_end": 30158.0,
  "total_km": 18.0,                   // server tự tính, KHÔNG gửi lên
  "km_start_photo": null, "km_end_photo": null,
  "checkin_time": "2026-09-15 09:05:00",
  "checkout_time": "2026-09-15 11:30:00",
  "checkin_notes": null, "checkout_notes": null,
  "confirmed_at": null, "cancelled_reason": null,
  "additional_cost": 0.0,
  "passengers": [ ... ],              // LUÔN là array
  "stops": [ ... ]
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
| Auth | `get_user_by_zalo_id` (Phase 2) | GET |
| | `verify_driver_login(driver_name, password)` | POST |
| | `get_drivers()` | GET |
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
| Xe | `get_vehicles()` · `get_vehicle_status()` | GET |
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

### Excel

`download_trip_report_excel` trả `{url, absolute_url, filename, is_private, row_count,
expires_in_minutes}`. File **public**, **tự xoá sau 45 phút**.
Dùng `absolute_url` khi mở từ webview Zalo — đường dẫn tương đối sẽ resolve theo origin của
Mini App và 404.

---

## 8. Chuyến cố định do SERVER tạo

Cron `30 6 * * *` và `0 17 * * *` sinh chuyến từ `TIQN Fixed Trip Schedule`. Tài xế mở app là
thấy sẵn, **không cần bấm gì**.

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

## 11. Việc còn treo

- **`TIQN Zalo Role Map` đang 0 bản ghi** và `TIQN Driver.phone`/`zalo_user_id` đang trống.
  Chỉ cần cho Phase 2 (đăng nhập bằng Zalo + ZNS), Phase 1 không dùng.
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

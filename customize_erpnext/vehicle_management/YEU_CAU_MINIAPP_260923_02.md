# Yêu cầu Server → Mini App (lần 2) — 23/09/2026

Server: `erp.tiqn.com.vn:8888` · 369 assert tự động, đã deploy.

Bên mình vừa **bỏ hẳn DocType `TIQN Driver`**. Đây là thay đổi breaking lớn nhất từ đầu dự
án. Chi tiết và việc cần làm phía client ở dưới.

---

## 🔴 1. Tài xế giờ LÀ một tài khoản Zalo

Trước đây một người có **hai** bản ghi: một `TIQN Driver` và một dòng `TIQN Zalo Role Map`
trỏ về nó. Hai bản ghi cho một người là hai cơ hội để lệch nhau — và đã lệch thật: ba tài
khoản Zalo khác nhau cùng trỏ về một tài xế.

Giờ chỉ còn **`TIQN Zalo Role Map`**. Tài xế = tài khoản Zalo có `role = driver` và một
`vehicle` được gán.

### Cái gì đổi trong payload

`driver` của chuyến giờ là **docname của Role Map**, tức **chính Zalo user ID**:

```json
{
  "driver": "9110000000000000001",
  "driver_name": "Mr. Lương",
  "driver_zalo_user_id": "9110000000000000001",
  "driver_zalo_id_by_oa": null
}
```

**Việc của Mini App:** bất cứ chỗ nào đang hardcode hoặc so sánh `driver` với `"Mr. Duy"` /
`"Mr. Long"` / `"Mr. Lương"` đều phải bỏ. Hiển thị thì dùng `driver_name` như cũ.

### Cái gì KHÔNG đổi

`get_drivers()` **giữ nguyên hình dạng cũ**: vẫn có `driver_name`, `assigned_vehicle`,
`assigned_vehicle_name`, `is_active`. Bên mình cố ý giữ các khoá này để client không phải
sửa màn chọn tài xế.

---

## 🔴 2. `verify_driver_login()` đã xoá — không còn đăng nhập bằng mật khẩu

Xoá cùng field `password` và toàn bộ cơ chế khoá chống dò.

Nó ra đời vì lúc đó chưa nối được danh tính Zalo. Giờ đã nối:
**`get_user_by_zalo_id()` chính là đăng nhập.**

```
GET .../get_user_by_zalo_id?zalo_user_id=<id từ getUserInfo()>

→ tài xế:
{ "zalo_user_id": "9110000000000000003", "display_name": "Mr. Duy",
  "role": "driver", "is_leader": 0,
  "vehicle": "TIQN-VEH-003", "vehicle_name": "Kia", "license_plate": "76H 058.34",
  "phone": null, "id_by_oa": null }

→ chưa map, hoặc bị chặn:
null
```

**Việc của Mini App:**

1. Gỡ màn đăng nhập bằng tên + mật khẩu.
2. Sau `getUserInfo()`, gọi `get_user_by_zalo_id()` và định tuyến theo `role`.
3. `null` → người dùng mới **hoặc** bị chặn. Xử lý như nhau: màn chờ quản lý cấp quyền.

---

## 3. Vai trò mặc định là `requester`

Mọi tài khoản Zalo vào app lần đầu là `requester`. Quản lý nâng lên `driver` (kèm xe) hoặc
`dispatcher` trong Desk.

Field mới **`disabled`** chặn một tài khoản dùng app mà **không xoá bản ghi** — lịch sử chuyến
và yêu cầu vẫn trỏ tới đó.

⚠ Người bị chặn khiến `get_user_by_zalo_id()` trả **`null`**, không phải vai trò kèm cờ. Cố ý:
Mini App đã biết xử lý `null`, còn một cờ phụ thì chỉ cần sót một chỗ kiểm là lọt.

---

## 4. `update_zalo_user_id` chỉ còn nhận `role = "requester"`

`driver` và `dispatcher` bị từ chối kèm giải thích. Danh tính của họ **là** bản ghi Role Map,
mà docname của bản ghi đó chính là `zalo_user_id` — ghi id lên chính nó là thao tác vô nghĩa.

Từ chối thẳng còn hơn im lặng chấp nhận một lời gọi không làm gì.

`update_zalo_id_by_oa(zalo_user_id, id_by_oa)` **không đổi**, vẫn dùng như cũ.

---

## 5. Lịch cố định không còn ghi tài xế

`TIQN Fixed Trip Schedule.driver` giờ để trống. Lịch nói **xe nào chạy ca nào**; ai lái thì
tra từ xe tại thời điểm tạo chuyến.

`get_fixed_templates_for_driver(driver_name)` **vẫn dùng y như cũ** — chỉ khác là `driver_name`
giờ là Zalo user ID, và server suy "lịch của người này" qua xe họ được gán. Trường `driver`
trong kết quả sẽ là `null`; đó là bình thường.

---

## Tóm tắt việc cho Mini App

| | Việc | Mức |
|---|---|---|
| 1 | Gỡ màn đăng nhập mật khẩu; dùng `get_user_by_zalo_id()` làm đăng nhập | 🔴 breaking |
| 2 | Bỏ mọi chỗ hardcode/so sánh `driver` với tên tài xế — nó là Zalo ID | 🔴 breaking |
| 3 | `null` từ `get_user_by_zalo_id()` = người mới **hoặc** bị chặn, xử lý như nhau | 🔴 breaking |
| 4 | `update_zalo_user_id` chỉ còn `role="requester"` | sửa nếu đang gọi |
| 5 | `driver = null` trong fixed templates là bình thường | hiển thị |
| — | `get_drivers()`, `update_zalo_id_by_oa()` | **không đổi** |

---

## Việc phía TIQN

Ba tài khoản Zalo các bạn đã tạo khi test (`Thành Vinh`, `User Name`, `Thái Sơn`) đã được đưa
về `requester` — trước đó cả ba cùng được gán nhầm làm tài xế của một xe. Quản lý sẽ nâng vai
trò cho đúng người.

Tài xế mẫu hiện tại là ba bản ghi demo (`Mr. Lương` / `Mr. Long` / `Mr. Duy`). Khi tài xế
thật đăng nhập Zalo lần đầu, quản lý gán `role = driver` + xe cho họ và xoá bản demo.

---

Tài liệu hợp đồng đầy đủ: `vehicle_management/API_CONTRACT.md`.
Yêu cầu lần 1 (bỏ `stops`, gộp điểm đến): `vehicle_management/YEU_CAU_MINIAPP_260923.md`.

---

## 🔴 6. Bổ sung cùng ngày: chuyến gán theo XE, không gán cho người

`TIQN Vehicle Trip` **không còn field `driver`**. Xe là đơn vị; tài xế xe nào thì thấy chuyến
của xe đó.

**Payload không đổi** — vẫn có `driver`, `driver_name`, `driver_phone`,
`driver_zalo_user_id`, `driver_zalo_id_by_oa`. Chỉ khác: chúng là **giá trị suy ra từ xe lúc
đọc**, không phải cột lưu. Chỗ hiển thị của các bạn giữ nguyên.

**Việc của Mini App:**

1. **Bỏ tham số `driver`** khi gọi `create_trip()` và `combine_requests_to_trip()` — gửi lên
   sẽ bị bỏ qua. Chỉ cần `vehicle`.
2. **Bỏ mọi ô cho người dùng CHỌN tài xế.** Không còn chỗ nào để lưu lựa chọn đó. Muốn đổi
   tài xế thì đổi ở bản ghi Zalo Role Map (quản lý làm trong Desk), hoặc đổi xe của chuyến.
3. `get_trips(driver=…)` và `get_today_trips_by_driver(…)` **dùng y như cũ** — server tự dịch
   sang lọc theo xe.

**Bỏ khỏi payload:**

| | |
|---|---|
| `summary.km_by_driver` trong `get_trip_report` | dùng `km_by_vehicle` hoặc `summary.vehicles` |
| `confirmed_at` trên chuyến | trạng thái `confirmed` vẫn còn |

Lý do bỏ `km_by_driver`: suy tài xế từ xe trả lời đúng câu hỏi *bây giờ* (gọi ai), nhưng sai
câu hỏi *lúc đó* (tháng 9 ai chạy bao nhiêu km) — tài xế đổi xe là lịch sử bị viết lại, âm
thầm. Thà không có con số còn hơn có một con số lặng lẽ đổi nghĩa.

Lý do bỏ `confirmed_at`: nó được ghi ở 4 chỗ trong code nhưng **không đọc ở đâu cả**.

---

## 7. Trạng thái xe: bốn giá trị còn ba

```
available · in_trip · maintenance · broken   →   available · in_trip · not_available
```

Xe là của công ty đối tác — TIQN không theo dõi bảo dưỡng hay hư hỏng, chỉ cần biết xếp được
xe hay không.

**Việc của Mini App:** bỏ mọi chỗ hiển thị hoặc gửi `maintenance` / `broken`.
`update_vehicle_status()` chỉ nhận `available` và `not_available`; `in_trip` do hệ thống tự
đặt, gửi lên sẽ bị từ chối.

Nhãn tiếng Việt đề xuất: **Không sẵn sàng**.

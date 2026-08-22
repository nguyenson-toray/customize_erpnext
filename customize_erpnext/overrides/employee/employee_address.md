# Địa chỉ tiếng Anh trên Employee — `permanent_address` · `current_address`

> **Mục đích:** sinh hai field địa chỉ tiếng Anh của core Employee từ bộ field tiếng Việt, theo
> đúng quy ước đang in trên **hợp đồng lao động** của công ty.
> **Phạm vi:** `overrides/employee/employee_address.py` · `CustomEmployee.validate`
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-21

---

## Làm gì

`permanent_address` và `current_address` là field lõi kiểu Small Text, trước đây **bỏ trống hoàn
toàn** (0/2.437). Nay được dựng lại mỗi lần lưu hồ sơ:

```
custom_<loại>_address_village   thôn/xóm   -> bỏ dấu + đổi tiền tố thành hậu tố
custom_<loại>_address_commune   xã/phường  -> wards.full_name_en
custom_<loại>_address_province  tỉnh/TP    -> provinces.full_name_en
```

```
TDP Liên Hiệp 1C, Xã Bình An, Tỉnh Gia Lai
   -> TDP Liên Hiệp 1C, Binh An Commune, Gia Lai Province
```

Đặt ở `CustomEmployee.validate()` chứ không ở JS: Data Import và API không đi qua JS, mà phần lớn
địa chỉ trên site này vào bằng Data Import.

## Quy ước lấy từ mẫu hợp đồng đang dùng

`api/address_converter/address.csv` — 2.398 địa chỉ HR đã dịch tay cho **hợp đồng lao động**. Đây
là văn bản pháp lý, nên bộ từ phải khớp đúng cái HR đang in, không được tự chế.

⚠ File đó **KHÔNG dùng làm bảng tra 1-1 được**: cột tiếng Anh lệch dòng ở rất nhiều chỗ — dòng
`Xã Tây Vinh, huyện Tây Sơn, tỉnh Bình Định` lại đi kèm `Lien Hiep 1C Group, Binh An Commune,
Gia Lai Province`; có dòng ghép tỉnh Hà Nội với `Quang Ngai Province`. Thứ rút ra được từ nó là
**quy ước dùng từ**, đếm trên toàn bộ cột tiếng Anh:

| Dùng | | Không dùng | |
|---|---|---|---|
| Province | 2.346 | Hamlet | 1 |
| Commune | 2.132 | Area | 0 |
| Village | 1.909 | Quarter | 0 |
| District | 643 | Residential | 0 |
| Ward | 215 | Team | 0 |
| City | 211 | Block | 0 |
| Group | 169 | | |
| Town | 28 | | |

Nên `Thôn` là **Village** chứ không phải Hamlet, và `KDC` / `Khu dân cư` xếp vào **Group** thay vì
bịa ra "Residential Area" — từ đó không có trong vốn từ HR đang dùng.

### Bảng tiền tố — nằm ở `address_vocabulary.json`, KHÔNG hardcode

Sửa file `overrides/employee/address_vocabulary.json` là đổi được cách dịch: **không cần sửa code,
không cần `bench restart`**, chỉ `bench clear-cache` (hoặc đợi hết TTL 1 ngày).

Không cần để ý thứ tự các dòng trong file — code tự sắp **cụm dài trước cụm ngắn** lúc nạp, nên
`tổ dân phố` luôn được xét trước `tổ`. Khoá viết thường không dấu; code bỏ dấu trước khi so nên
`Thôn`, `thôn`, `THÔN` đều khớp.

| Tiếng Việt | Kết quả |
|---|---|
| `Thôn X` · `Xóm X` | `X Village` |
| `Tổ dân phố X` · `TDP X` · `Tổ X` · `Đội X` · `KDC X` · `Khu dân cư X` | `X Group` |
| `Số 18` | `No.18` |
| `Xã` / `Phường` / `Thị trấn` | `Commune` / `Ward` / `Town` (từ `wards.full_name_en`) |
| `Tỉnh` / `Thành phố` | `Province` / `City` (từ `provinces.full_name_en`) |

Phần còn lại **thuần số thì danh từ đứng trước**: `Tổ 23` → `Group 23`, `Xóm 3` → `Village 3` —
đúng cách file mẫu viết (`Group 13`, `Village 1`). Có chữ thì đứng sau: `Thôn An Đại 2` →
`An Dai 2 Village`.

Dài khớp trước ngắn: `tổ dân phố` phải xét trước `tổ`, nếu không `tổ` nuốt mất và ra
`Dan Pho Group`.

## Cờ `translate_unmatched_admin` — mặc định TẮT

Trong `address_vocabulary.json`. Quyết định làm gì khi xã/tỉnh **không tra được** trong bảng
`provinces`/`wards`:

| Giá trị | Kết quả với `TP Đà Nẵng` |
|---|---|
| `false` (mặc định) | `TP Đà Nẵng` — giữ nguyên tiếng Việt |
| `true` | `Da Nang City` — dịch máy bằng bảng `admin_unit` |

🔴 **Cân nhắc trước khi bật `true`.** Bảng `provinces` chỉ có đơn vị **sau sáp nhập 2025**. Dữ
liệu còn 36 hồ sơ mang tên tỉnh cũ (`Tỉnh Quảng Nam`, `Tỉnh Bình Định`, `Tỉnh Phú Yên` — đã sáp
nhập, không còn tồn tại). Bật `true` là in `Quang Nam Province` lên **hợp đồng lao động**: trông
rất chuẩn nhưng đặt tên một đơn vị hành chính không còn tồn tại — sai âm thầm, ký xong mới biết.
Để `false` thì nó lòi ra tiếng Việt và người ta sửa được trước khi in.

## 🔴 Chỉ dịch khi địa chỉ tiếng Việt ĐỔI — không bao giờ đè bản đã có

Giá trị tiếng Anh đang có là **bất khả xâm phạm**. Ba nhánh trong `sync_english_addresses`:

| Tình huống | Hành động |
|---|---|
| Ô tiếng Anh **rỗng**, có dữ liệu tiếng Việt | dịch và điền |
| Bộ field tiếng Việt **vừa đổi trong chính lần lưu này** | dịch lại |
| Còn lại | **không đụng vào** |

Nhánh 2 so với `get_doc_before_save()`, không so với giá trị vừa tính ra.

Vì sao quan trọng: bản đầu dịch lại ở **mọi** lần lưu rồi ghi đè nếu khác. Hệ quả là **địa chỉ
tiếng Anh import thẳng vào bị xoá mất** ở lần lưu kế tiếp — HR nhập bản dịch tay đúng chuẩn hợp
đồng, hệ thống lẳng lặng thay bằng bản máy dịch. Trên văn bản pháp lý thì đó là hỏng việc.

Muốn dựng lại: **xoá trắng ô tiếng Anh rồi lưu** (nhánh 1), hoặc sửa địa chỉ tiếng Việt (nhánh 2).

### Phía form: bắt thay đổi ngay trên JS

`employee.js` gắn `translate_address_to_english()` vào 6 ô tiếng Việt (village/commune/province ×
thường trú/hiện tại) và nút *Copy Permanent Address*. Mỗi lần người dùng sửa một ô, JS gọi
`translate_address()` (whitelisted, chỉ đọc) rồi `set_value` vào ô lõi — HR **thấy kết quả trước
khi lưu** thay vì lưu xong mới biết máy dịch ra cái gì.

JS **không** dịch lúc mở hồ sơ, cùng lý do với server: mở form không phải là thay đổi.

## 🔴 Tra xã PHẢI kèm mã tỉnh

Tên xã **trùng nhau giữa các tỉnh**: `Xã Tân Thanh` có ở **13 tỉnh**, `Xã Vĩnh Thanh` 7 tỉnh. Tra
bằng mỗi tên xã là bốc trúng tỉnh nào thì trúng — sai âm thầm, và sai đúng vào địa chỉ của người
lao động. Khoá tra cứu là cặp `(mã tỉnh, tên xã)`.

## Không tra được thì GIỮ NGUYÊN tiếng Việt

Không bỏ trống, không đoán. Một địa chỉ lẫn tiếng Việt vẫn gửi thư đến nơi; một địa chỉ trống hoặc
dịch sai thì không.

Nhờ vậy, **phần còn tiếng Việt chính là danh sách dữ liệu cần sửa** — lọc
`current_address LIKE '%Tỉnh %'` hoặc `'%Xã %'` là ra ngay.

Đo 21/08/2026 sau khi backfill 2.437 hồ sơ:

| | Số hồ sơ |
|---|---|
| `current_address` đã dựng | 2.046 |
| `permanent_address` đã dựng | 4 |
| còn lẫn tiếng Việt | **64** |

Hai nguyên nhân, cả hai đều là **dữ liệu nguồn**, không phải lỗi code:

1. **Tên đơn vị hành chính cũ** — 36 hồ sơ / 18 giá trị. Bảng `provinces` chỉ chứa đơn vị **sau
   sáp nhập 2025**, dữ liệu Employee còn `Tỉnh Quảng Nam`, `TP Đà Nẵng`, `Tỉnh Bình Định`,
   `Tỉnh Phú Yên`… Có cả biến thể viết hoa/thường (`tỉnh Quảng Ngãi`, `Thành Phố Đà Nẵng`).
2. **Ô nhập tay lộn xộn** — 28 hồ sơ / 20 giá trị: `Tịnh Khê` (thiếu chữ Xã),
   `Xã Tân Hà Lâm Hà, Tỉnh Lâm Đồng` (nhét cả tỉnh vào ô xã), `Xã Trà Ginag` (gõ sai),
   `Xã Nghĩa An [Tỉnh Nghệ An]` (xã của tỉnh khác).

HR sửa lại địa chỉ tiếng Việt cho đúng thì bản tiếng Anh tự đúng theo ở lần lưu kế tiếp.

🔴 **Phải dọn hết 64 địa chỉ này TRƯỚC khi in hợp đồng.** Đây là văn bản pháp lý — một địa chỉ
lẫn tiếng Việt in ra thì nhìn thấy ngay và sửa được; nếu code đoán bừa sang tiếng Anh thì sai âm
thầm, ký xong mới biết. Đó là lý do nhánh fallback tồn tại.

## 🔴 Hai field này từng KHÔNG hiện trên form — vì Section Break bị ẩn

Triệu chứng: `permanent_address` / `current_address` có dữ liệu trong DB, `as_dict()` trả về đúng,
nhưng mở hồ sơ trên desk **không thấy đâu**.

Nguyên nhân: bản thân hai field `hidden = 0`, nhưng **`address_section` — Section Break chứa
chúng — có `hidden = 1`**. Ẩn một Section Break là ẩn cả section, kể cả field bên trong đang hiện.
Kiểm bằng `meta.get_field("permanent_address").hidden` sẽ ra `0` và tưởng không có vấn đề gì.

Section đó bị ẩn từ đợt dọn field thừa trên Employee, hồi mà hai field còn rỗng hoàn toàn
(0/2.437) và trùng vai với bộ field tiếng Việt. Nay chúng giữ bản tiếng Anh nên đã hiện lại, kèm
đổi nhãn section thành **Address (English)** để không lẫn với section địa chỉ tiếng Việt ngay
phía trên.

Layout hiện tại của section: cột trái `Permanent Address Eng`, cột phải `Current Address Eng`;
`permanent_accommodation_type` / `current_accommodation_type` vẫn ẩn riêng.

Cả bốn Property Setter (`hidden`, `label`, và `read_only`/`label` của hai field) nằm trong
`fixtures/property_setter.json` — sửa trên UI xong nhớ `bench export-fixtures --app customize_erpnext`.

## Bẫy khi sửa

1. **Đừng bỏ nhánh fallback.** Trông như thừa cho tới lúc gặp một tên đơn vị hành chính vừa đổi —
   rồi 36 hồ sơ mất sạch địa chỉ mà không có gì báo.
2. **Đừng tra xã bằng mỗi tên** (xem mục trên).
3. `sync_english_addresses` **chỉ ghi khi giá trị đổi**. `validate` chạy ở mọi lần lưu; gán lại
   chuỗi y hệt sẽ khiến Frappe coi document là "đã đổi" và sinh một bản `Version` thừa mỗi lần lưu.
   Và **đừng bỏ điều kiện "ô tiếng Anh đang rỗng"** — bỏ là quay lại đè mất bản dịch tay.
4. Field quê quán (`custom_place_of_origin_address_*`) đã bị gỡ khỏi Employee 21/08/2026. Code
   liên quan **được comment lại chứ không xoá**, tìm bằng `grep 'TẠM TẮT 21/08/2026'`.
5. **Field không hiện thì kiểm Section Break trước**, đừng kiểm mỗi field (xem mục trên).
6. **Đổi cách dịch thì sửa `address_vocabulary.json`, đừng sửa code.** Sửa xong nhớ
   `bench clear-cache` — từ vựng cache 1 ngày.
7. Tên tiếng Anh của xã/tỉnh lấy từ `full_name_en` của bảng `provinces`/`wards`, **không** từ
   bảng `admin_unit` trong JSON. Bảng đó chỉ là phương án dự phòng, xem cờ ở trên.

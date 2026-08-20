# Hướng dẫn dùng trang Dev Tool

> **Mục đích:** Trang gom các công cụ tài liệu nội bộ vào một chỗ: **`https://erp.tiqn.com.vn:8888/dev-tool`**,
> **Phạm vi:** Tài liệu cho developer
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-19

Trang gom các công cụ tài liệu nội bộ vào một chỗ: **`https://erp.tiqn.com.vn:8888/dev-tool`**,
hoặc bấm icon **Dev Tool** ở màn hình chính của ERP.

Thanh dọc bên trái là nơi chuyển giữa các tab. Dưới cùng có nút **Present** (trình chiếu) và
link quay lại Desk.

## Ba tab hiện có

| Tab | Dùng để làm gì | Đọc file trong |
|---|---|---|
| **Mindmap** | Sơ đồ chức năng toàn hệ thống, xem chức năng nào chuẩn / đã sửa / tự phát triển và tiến độ | `docs/mindmap/` |
| **Flowchart** | Sơ đồ luồng xử lý: chấm công, tính lương, check-in… | `docs/flowchart/` |
| **Hướng dẫn** | Chính là trang bạn đang đọc — tài liệu cho người phát triển | `docs/user_manual/` |

## Thao tác chung

- **Kéo thanh dọc** giữa panel trái và vùng nội dung để đổi bề rộng. Nhấp đúp lên thanh đó
  để trả về mặc định. Bề rộng được nhớ cho lần mở sau.
- **Trình chiếu**: bấm nút **Present** hoặc phím **P**. Trang ẩn hết panel và thanh công cụ,
  chỉ còn sơ đồ, kèm toàn màn hình thật của trình duyệt. Thoát bằng phím **Esc**.

## Tab Flowchart

Chọn một file ở panel trái, mỗi sơ đồ trong file hiện thành một thẻ riêng.

**Xem sơ đồ**

- **Cuộn chuột** để phóng to thu nhỏ — phóng đúng vào điểm con trỏ đang trỏ.
- **Bấm giữ và kéo** để di chuyển sơ đồ trong khung.
- **Vừa khung** đưa cả sơ đồ lọt một màn; **Vừa ngang** phóng cho hết bề ngang; **1:1** về
  kích thước gốc.
- **Dọc / Ngang**: sơ đồ vẽ dọc thường cao và hẹp, bấm **Ngang** để nó trải theo chiều ngang
  cho đỡ phải cuộn. Nút này **chỉ đổi bản đang xem**, file gốc giữ nguyên.

**Lấy sơ đồ ra ngoài**

| Nút | Kết quả |
|---|---|
| **Copy mã Mermaid** | Chép mã sơ đồ vào clipboard, dán vào draw.io qua **Extras ▸ Edit Diagram…** |
| **Tải .mmd** | Lưu riêng phần mã sơ đồ thành file, để gửi cho người khác |
| **Tải PNG** | Ảnh nền trắng, gấp đôi độ phân giải — dán vào slide, Word, chat |
| **Tải SVG** | Ảnh vector, phóng to bao nhiêu cũng nét |

> Dán vào draw.io thì màu và cỡ chữ có thể mất, phải chỉnh tay lại — draw.io không giữ được
> phần định dạng của Mermaid. Nếu chỉ cần ảnh để chèn vào tài liệu thì dùng **Tải PNG**, nhanh
> và giữ đúng hình.

**Sửa nội dung**: ô soạn thảo ở panel trái. Bấm **Render** để xem thử, **Lưu** (hoặc **Ctrl+S**)
để ghi đè vào file đang mở. Chỉ tài khoản Administrator lưu được; bản trước khi lưu luôn được
giữ lại ở file `.bak` cạnh đó.

## Tab Hướng dẫn

Nơi lưu tài liệu cho **người phát triển**: một chức năng hoạt động ra sao, bẫy nào phải
tránh, đổi thì phải sửa ở đâu.

Panel trái liệt kê các bài trong `docs/user_manual/`, có ô tìm theo tên. Mở một bài thì mục
lục các đề mục của bài hiện ở dưới danh sách, bấm vào để nhảy tới.

**Quy định gốc — bản scan.** Cuối panel trái có khối *"Quy định gốc — bản scan"* liệt kê các
PDF trong `docs/user_manual/pdf/`: bản chụp có đóng dấu của quy chế, thông báo công ty. Bấm tên
để xem ngay trong trang bằng trình đọc PDF của trình duyệt; bấm **⭳** bên cạnh để tải về. Trong
khung xem còn có nút **Tải PDF** và **Mở tab mới**. Chế độ trình chiếu ẩn hết thanh nút, chỉ còn
trang scan.

Thêm bản scan mới: thả file `.pdf` vào `docs/user_manual/pdf/` rồi mở lại tab.

Thêm bài mới: thả một file `.md` vào thư mục
`apps/customize_erpnext/customize_erpnext/docs/user_manual/` rồi mở lại tab. Tên hiển thị lấy
từ dòng tiêu đề `#` đầu tiên trong file, nên bài nào cũng nên mở đầu bằng một dòng như vậy.

Trong bài viết được dùng bảng, danh sách, khối trích dẫn, đoạn mã. Nếu chèn một khối
` ```mermaid ` thì nó cũng được vẽ thành sơ đồ ngay trong bài.

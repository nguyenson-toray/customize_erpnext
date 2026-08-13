# 01_docs — Sơ đồ chức năng hệ thống / System Functional Mindmaps

Tài liệu **giới thiệu và hướng dẫn người dùng**: hệ thống có những chức năng gì, mỗi chức năng dùng để làm gì, chức năng nào là chuẩn / đã sửa / phát triển thêm, và tiến độ đến đâu. Tiêu đề mọi mục song ngữ `English / Tiếng Việt`.

Xem sơ đồ ngay trên hệ thống:

| Link | Sơ đồ |
|---|---|
| https://erp.tiqn.com.vn:8888/mindmap?file=hr_mindmap.md | HR — Nhân sự |
| https://erp.tiqn.com.vn:8888/mindmap?file=ga_mindmap.md | GA — Hành chính |

---

## 1. Files

| File | Nội dung |
|---|---|
| `hr_mindmap.md` | **HR**: hồ sơ, chấm công, tăng ca, nghỉ phép, tiền lương |
| `ga_mindmap.md` | **GA**: đồng phục, khám sức khỏe, kệ giày |
| `build_mindmap.py` | Script sinh 2 file trên + bảng dịch mô tả cho trang |
| `tests/test_mindmap.js` | Test cho trang `/mindmap` (không cần cài gì, chỉ cần node) |

Files của trang nằm ở `../www/mindmap/` và `../api/mindmap_docs.py` — xem mục 6.

## 2. Cấu trúc một dòng trong file .md

```
- **01. [Employee profile / Thông tin nhân viên](/desk/employee)** `[Override]` `[Done]` — Thông tin cá nhân, phòng ban...
     │    │                                    │                    │          │           └─ mô tả (đổi được VI/EN trên trang)
     │    │                                    │                    │          └───────────── tiến độ
     │    │                                    │                    └──────────────────────── phân loại
     │    │                                    └───────────────────────────────────────────── link mở chức năng
     │    └────────────────────────────────────────────────────────────────────────────────── tiêu đề song ngữ
     └─────────────────────────────────────────────────────────────────────────────────────── số thứ tự
```

**Phân loại** — chức năng đó từ đâu ra, quyết định **màu đường nối** trên sơ đồ:

| Nhãn | Màu | Ý nghĩa |
|---|---|---|
| `[Standard]` | xanh dương | Chức năng có sẵn của hệ thống, dùng nguyên bản |
| `[Override]` | cam | Chức năng chuẩn nhưng đã sửa cho phù hợp quy định công ty |
| `[Custom]` | xanh lá | Chức năng tự phát triển riêng, hệ thống gốc không có |
| *(không nhãn)* | xám | Mục gom nhóm, gồm nhiều loại |

**Tiến độ** — sửa được ngay trên trang hoặc sửa tay trong file:

| Nhãn | Hiển thị |
|---|---|
| `[Done]` | icon tròn xanh có dấu ✓ |
| `[In process 60%]` | icon hình bánh đầy 60% + nhãn `60%` |
| `[Pending: chờ HR chốt quy định]` | icon vòng nét đứt + dòng lý do in nghiêng |

Viết `[Inprocess]`, `[In progress]`, `[Todo]` cũng được, script tự chuẩn hoá.

**Số thứ tự** — 2 chữ số ở đầu tiêu đề. Trang sắp nhánh theo số này; mục không có số xếp sau và giữ thứ tự trong file. Đổi thứ tự chỉ cần đổi số.

**Link** — markdown thường, dùng **đường dẫn tương đối** để cùng file mở được ở mọi site:

- Desk của Frappe v16 ở `/desk/...` (`/app/...` chỉ chuyển hướng sang `/desk`)
- Dấu cách phải viết `%20`: `/desk/query-report/OT%20Compliance`
- Ví dụ: list view `/desk/attendance`, dạng report `/desk/employee/view/report`, trang riêng `/desk/uniform-dashboard`, trang portal `/employee-photos`

## 3. Sửa nội dung

**Sửa tay trong file `.md` hoặc sửa trên trang `/mindmap` đều được, build lại không mất.** Script đọc file cũ và giữ nguyên: **tiến độ, mô tả, link, số thứ tự**. Chỉ có cấu trúc cây và nhãn phân loại là luôn lấy theo script.

```bash
cd apps/customize_erpnext/customize_erpnext/01_docs
python3 build_mindmap.py                 # build, giữ mọi thứ đã sửa tay
python3 build_mindmap.py --renumber      # đánh số lại theo thứ tự logic trong script
python3 build_mindmap.py --from-script   # bỏ sửa tay, lấy lại mô tả + link theo script
python3 build_mindmap.py --json          # xuất thêm file JSON
```

Hai lưu ý:

- Mục **xoá hoặc comment lại** trong `.md` sẽ được build thêm vào lại, kèm cảnh báo `⚠`. Muốn bỏ hẳn thì xoá trong `build_mindmap.py`.
- Đổi **tiêu đề** một mục trong script thì mục đó coi như mới: tiến độ, mô tả, link, số đã sửa tay của nó không khớp được nữa và trở về mặc định.

**Thứ tự hiển thị** nằm ở dict `LOGICAL_ORDER` trong script, xếp theo logic nghiệp vụ — cái gì phải có trước thì đứng trước (khai ca trước khi tính công, cấu hình bảo hiểm/thuế trước khi chạy lương, khai kệ và vẽ sơ đồ trước khi gán ô). Sửa dict rồi chạy `--renumber`.

**Bảng link** nằm ở dict `LINKS` trong script, khoá là tiêu đề tiếng Anh của mục.

## 4. Ngôn ngữ phần mô tả (VI / EN)

File `.md` luôn giữ mô tả tiếng Việt. Bản tiếng Anh nằm cạnh trang:

| File | Vai trò |
|---|---|
| `../www/mindmap/vi.csv` | Bản chuẩn, **do `build_mindmap.py` sinh** — đừng sửa tay, build sẽ ghi đè |
| `../www/mindmap/vi_auto.csv` | Cache **dịch máy**, trang tự ghi thêm; sửa tay được, build không ghi đè |

Bấm **EN** trên trang: mục nào chưa có bản dịch sẽ được gửi đi dịch tự động qua internet (Google Translate) rồi cache lại. Máy chủ không ra internet thì trang giữ nguyên tiếng Việt và báo lại.

⚠ Dịch tự động **gửi nội dung mô tả ra ngoài internet**. Mô tả ở đây là tài liệu hướng dẫn chức năng nên không có dữ liệu nhân sự, nhưng cần biết để không dán nội dung mật vào rồi bấm EN.

Muốn bản tiếng Anh chuẩn thay vì dịch máy: sửa `desc` trong script (nhận `("English", "Tiếng Việt")`) rồi build lại.

## 5. Dùng trang `/mindmap`

**Phân quyền:**

| Ai | Được gì |
|---|---|
| Mọi người dùng đã đăng nhập | **Xem sơ đồ, chế độ chỉ đọc** — thanh trạng thái ghi `chỉ đọc`, ô markdown không sửa được, bấm icon tiến độ sẽ báo không có quyền |
| Role `Administrator` | Sửa mô tả, tiến độ, link, số thứ tự và **lưu vào file** |
| Guest | Bị chuyển sang trang đăng nhập |

Bấm **mũi tên ↗** của một mục thì Frappe tự kiểm quyền của người đó với chức năng đó — ai chưa được phân quyền sẽ nhận thông báo không có quyền như bình thường, sơ đồ không cấp thêm quyền gì.

Truy cập nhanh: icon **System Mindmap** trên trang chủ desk (Desktop Icon, hiện cho mọi người), hoặc vào thẳng `/mindmap`.

Trang đọc và ghi trực tiếp file `.md` trong thư mục này.

| Nhóm | Chức năng |
|---|---|
| Nguồn | Chọn file `.md` trên máy chủ, hoặc dán markdown vào ô soạn. Sửa là vẽ lại ngay |
| Lưu | `Save` ghi đúng file nguồn, giữ bản trước ở `.bak`. `Ctrl+S` cũng được |
| Kiểu vẽ | `Một bên` (dọc như markmap) hoặc `Hai bên` (toả hai phía node gốc, sơ đồ vuông và dễ nhìn hơn) |
| Không gian | `Markdown` ẩn/hiện ô soạn để nhường chỗ cho sơ đồ; `Details` ẩn/hiện phần mô tả. Cả hai được ghi nhớ |
| Nhánh | `Expand` / `Collapse` toàn bộ; bấm badge số để gập từng nhánh; bấm đúp mục cũng gập/mở |
| Tiến độ | Bấm icon để đổi `Done → In process → Pending`, sẽ hỏi **%** hoặc **lý do**. Shift+bấm chỉ sửa giá trị |
| Điều hướng | Bấm mục → nhảy tới đúng dòng trong ô soạn. Bấm mũi tên ↗ → mở chức năng tương ứng |
| Site | Ô chọn site quyết định link mở bằng `erp.tiqn.com.vn:8888`, `erp.tiqn.local` hay site hiện tại |
| Chia sẻ | URL luôn chứa `?file=...`; nút `Copy link` copy sẵn |
| Xuất | `PNG` (nền trắng, có tiêu đề + quy ước màu trong ảnh), `HTML` (link bấm được), `MD` |

Vẽ ngoài hệ thống: dán file `.md` vào https://markmap.js.org/repl, extension *Markmap* của VS Code, hoặc import vào XMind / FreeMind.

## 6. Trang được build thế nào (cho người bảo trì)

### Files

| File | Vai trò |
|---|---|
| `../www/mindmap/index.py` | `get_context`: bắt đăng nhập, cấp `csrf_token` và `can_save` (1 nếu có role Administrator) |
| `../www/mindmap/index.html` | Toàn bộ trang: HTML + CSS + JS trong một file, **không dùng thư viện ngoài** |
| `../api/mindmap_docs.py` | 5 whitelisted method: `list_docs`, `read_doc`, `read_lang`, `translate_texts` (cần đăng nhập) và `write_doc` (chỉ Administrator) |
| `../www/mindmap/vi.csv`, `vi_auto.csv` | Bảng dịch mô tả |
| `../desktop_icon/system_mindmap.json` | Icon **System Mindmap** trên trang chủ desk, trỏ tới `/mindmap` |

### Vì sao tự vẽ SVG thay vì dùng markmap

Cần **màu đường nối theo phân loại**, **icon tiến độ có %**, **link theo node** và **export PNG nền trắng** — markmap tô màu theo độ sâu và không có các thứ này, nhúng thêm thư viện lại phải build asset. Trang tự dựng cây SVG: đo chữ bằng `canvas.measureText`, layout cây ngang (`layoutBranch`), vẽ `<path>` bezier cho đường nối, `<g class="node-card">` cho mỗi mục. Không có `bench build`, chỉ cần `bench clear-cache`.

### Luồng dữ liệu

```
file .md  ──read_doc──▶  ô soạn markdown  ──parseMarkdown──▶  cây node
                              ▲                                   │
                              │ setStatusOnLine                   │ layout + buildInner
                              │ (bấm icon trên sơ đồ)             ▼
                        write_doc ◀── Save ──  người dùng  ◀── SVG trên trang
                                                                  │
                                                    exportSVGString ──▶ PNG / HTML
```

`parseMarkdown` hiểu: heading `#`, bullet lồng nhau (2 space = 1 cấp), blockquote `>` làm mô tả cho mục vừa tạo, comment `<!-- -->` kể cả nhiều dòng, nhãn trong `` `[...]` ``, link markdown, số thứ tự đầu tiêu đề.

### Bốn cái bẫy đã gặp, đừng đạp lại

1. **Trang `/www/` không có object `frappe`** — không dùng được `frappe.call`. Phải tự `fetch` `/api/method/...` với **`FormData` chứa `csrf_token`**; gửi JSON + header `X-Frappe-CSRF-Token` luôn lỗi `CSRFTokenError`. Xem `callFrappeMethod` trong `index.html`.
2. **`font-family` trong attribute SVG không được chứa nháy kép** — `"Segoe UI"` làm SVG sai XML, `<img>` không load được và Export PNG báo lỗi. Dùng nháy đơn: `'Segoe UI'`.
3. **File `.md` bị lưu CRLF** (editor Windows) làm hỏng việc đo thụt lề → cây rỗng. `parseMarkdown` và `setContent` đều chuẩn hoá `\r\n` → `\n`; `build_mindmap.py` giữ nguyên kiểu xuống dòng của file cũ để git không diff cả file.
4. **`mouseup` chạy trước `click`** — kéo canvas rồi nhả chuột trên một mục sẽ bị hiểu là bấm mục. Phải giữ cờ `panMoved` sau `mouseup` để `click` biết mà bỏ qua.

### An toàn

- API chỉ đọc/ghi file `.md` **trong `01_docs`**: `os.path.realpath` rồi kiểm tra prefix, nên `../hooks.py` hay `/etc/passwd` đều bị chặn.
- `write_doc` gọi `_check_edit()` (chỉ role Administrator), từ chối nội dung rỗng và luôn ghi `.bak` trước khi ghi đè. Kiểm tra nằm ở API chứ không chỉ ở giao diện, nên gọi trực tiếp `/api/method/...` cũng không lách được.
- `translate_texts` cho mọi người dùng dịch để xem, nhưng **chỉ Administrator mới được ghi cache** `vi_auto.csv`.
- Link `javascript:` / `data:` bị chặn khi mở và khi xuất HTML.
- File `*.bak` đã cho vào `.gitignore` của app.

### Test

```bash
cd apps/customize_erpnext/customize_erpnext
node 01_docs/tests/test_mindmap.js
```

85 kiểm tra, chạy trong ~1 giây: parse markdown (kể cả CRLF, nhãn viết tay, số thứ tự), layout không chồng lấn ở cả hai kiểu vẽ, màu đường nối, icon %, lý do Pending, đổi ngôn ngữ, link + chặn scheme lạ, và SVG export phải well-formed. Test rút code thẳng từ `index.html` nên sửa trang là test kiểm bản mới; nếu đổi tên mốc `/* ... wiring */` trong file thì test báo lỗi ngay.

Sau khi sửa `index.py` hoặc `mindmap_docs.py`: `bench --site erp.tiqn.local clear-cache`. Không cần restart vì không đụng `hooks.py`.

## 7. Quy ước viết nội dung

- Tiêu đề song ngữ, tiếng Anh trước, dấu `/`, rồi tiếng Việt.
- Mô tả một dòng, nói **chức năng giúp người dùng làm được gì**.
- Không đưa tên file, tên DocType kỹ thuật, tên hàm hay đường dẫn code vào nội dung — đây là tài liệu cho người dùng cuối.
- Nêu các quy tắc nghiệp vụ người dùng cần biết: ngày lễ vẫn tính công, nghỉ nửa ngày phép vẫn tính đủ công, nhân viên mang thai được bỏ chụp X-quang.

## 8. Phạm vi hiện tại

| | Số mục | Standard | Override | Custom | Có link |
|---|---|---|---|---|---|
| `hr_mindmap.md` | 93 | 18 | 22 | 34 | 74 |
| `ga_mindmap.md` | 93 | 0 | 0 | 69 | 69 |

Phần còn lại là mục gom nhóm và nhánh chú thích. Toàn bộ GA là tự phát triển vì hệ thống gốc không có 3 module này.

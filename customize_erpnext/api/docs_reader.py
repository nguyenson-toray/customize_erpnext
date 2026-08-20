"""Backend dùng chung cho trang Dev Tool (/dev-tool).

Mỗi tab của trang đọc file .md trong một thư mục con của `customize_erpnext/docs`:

    docs/mindmap/     - file .md để vẽ mindmap   (tab Mindmap)
    docs/flowchart/   - file .md để vẽ flowchart  (tab Flowchart)
    docs/user_manual/ - tài liệu cho developer    (tab Hướng dẫn)

Thêm tab mới = thêm một tên vào CATEGORIES + tạo thư mục cùng tên, không phải
sửa gì trong hai hàm API bên dưới.

Bảo mật đường dẫn: `category` phải nằm trong CATEGORIES (whitelist cứng, không
nhận đường dẫn tự do), `filename` phải là tên file trần — mọi thứ có dấu phân
cách thư mục đều bị chặn ngay, sau đó còn resolve rồi so lại prefix để chặn
symlink trỏ ra ngoài.

Quyền: đọc thì mọi người dùng đã đăng nhập đều được, giống trang mindmap cũ —
tài liệu này chỉ mô tả hệ thống, bấm vào link bên trong vẫn bị Frappe kiểm quyền
riêng. Guest thì không.
"""

import datetime
import os
import re
import unicodedata

import frappe
from frappe import _

DOCS_SUBDIR = "docs"

# Thư mục con hợp lệ. Thêm tab mới thì thêm vào đây.
CATEGORIES = ("mindmap", "flowchart", "user_manual")

# Đọc: mọi người dùng đã đăng nhập. Ghi: chỉ Administrator, giống trang /mindmap.
EDIT_ROLES = ("Administrator",)


def _check_view():
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to read documentation files"),
                     frappe.PermissionError)


def can_edit():
    return any(r in frappe.get_roles() for r in EDIT_ROLES)


def _check_edit():
    if not can_edit():
        frappe.throw(
            _("Only the Administrator role can edit documentation files"),
            frappe.PermissionError,
        )


def category_dir(category):
    """Đường dẫn tuyệt đối của thư mục một category, đã kiểm tra tên hợp lệ."""
    category = (category or "").strip()
    if category not in CATEGORIES:
        frappe.throw(_("Unknown documentation category: {0}").format(category))

    app_path = frappe.get_app_path("customize_erpnext")
    return os.path.realpath(os.path.join(app_path, DOCS_SUBDIR, category))


def resolve(category, filename):
    """Trả về đường dẫn tuyệt đối của một file .md trong category, đã kiểm tra.

    Dùng chung với api/mindmap_docs.py để chỉ có một nơi quyết định file nào đọc được.
    """
    root = category_dir(category)

    filename = (filename or "").strip()
    if not filename:
        frappe.throw(_("File name is required"))

    # Chặn thẳng mọi dạng đường dẫn: chỉ nhận tên file trần nằm ngay trong thư mục
    if os.path.basename(filename) != filename or filename in (".", ".."):
        frappe.throw(_("Only file names inside {0} are allowed").format(category))
    if not filename.lower().endswith(".md"):
        frappe.throw(_("Only .md files are allowed"))

    candidate = os.path.realpath(os.path.join(root, filename))

    # Kiểm lại sau khi resolve: bắt cả trường hợp symlink trỏ ra ngoài thư mục
    if not candidate.startswith(root + os.sep):
        frappe.throw(_("Only files inside {0} are allowed").format(category))

    return candidate


def _title_of(path, fallback):
    """Tiêu đề hiển thị = dòng heading '#' hoặc '##' đầu tiên trong file.

    Chỉ đọc phần đầu file, không nạp cả file chỉ để lấy một dòng. Bỏ qua heading
    nằm trong khối ``` để không nhặt nhầm comment trong đoạn code mẫu.
    """
    try:
        with open(path, encoding="utf-8") as f:
            in_fence = False
            for _i, line in zip(range(80), f):
                stripped = line.strip()
                if stripped.startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                m = re.match(r"^#{1,2}\s+(.+?)\s*$", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return fallback


@frappe.whitelist()
def list_docs(category):
    """Danh sách file .md trong docs/<category>/, kèm tiêu đề đọc từ heading đầu file."""
    _check_view()
    root = category_dir(category)

    if not os.path.isdir(root):
        return {"category": category, "dir": root, "files": []}

    files = []
    for name in sorted(os.listdir(root)):
        if not name.lower().endswith(".md"):
            continue
        full = os.path.join(root, name)
        if not os.path.isfile(full):
            continue
        st = os.stat(full)
        files.append({
            "name": name,
            "title": _title_of(full, name),
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })

    return {"category": category, "dir": root, "files": files, "can_edit": 1 if can_edit() else 0}


@frappe.whitelist()
def get_doc_content(category, filename):
    """Nội dung thô của một file .md trong docs/<category>/."""
    _check_view()
    full = resolve(category, filename)

    if not os.path.isfile(full):
        frappe.throw(_("File not found: {0}").format(filename))

    with open(full, encoding="utf-8") as f:
        content = f.read()

    return {
        "category": category,
        "name": os.path.basename(full),
        "content": content,
        # Trang giữ lại mtime này rồi gửi ngược lên lúc lưu để phát hiện file đã
        # bị người khác sửa trong lúc mình đang mở (xem save_doc).
        "mtime": int(os.path.getmtime(full)),
        "can_edit": 1 if can_edit() else 0,
    }


@frappe.whitelist()
def get_doc_html(category, filename):
    """Nội dung file .md đã dựng sẵn thành HTML — cho tab xem hướng dẫn sử dụng.

    Dựng ở máy chủ bằng `frappe.utils.md_to_html` (markdown2: bảng, code fence,
    id cho heading) để trang không phải nhúng thêm thư viện markdown nào.

    Không lọc HTML thô trong file: các file này chỉ Administrator ghi được
    (xem save_doc) và nằm trong repo của app, không phải nội dung người dùng
    nhập. Nếu sau này mở quyền ghi rộng hơn thì phải lọc lại ở đây.
    """
    _check_view()
    doc = get_doc_content(category, filename)
    doc["html"] = frappe.utils.md_to_html(doc["content"]) or ""
    return doc


def _app_root():
    return os.path.realpath(frappe.get_app_path("customize_erpnext"))


def resolve_app_doc(path):
    """Đường dẫn tới một file .md BẤT KỲ trong app, đã kiểm tra.

    Dùng cho file chỉ mục: một bài trong docs/user_manual liệt kê đường dẫn tới
    README của các module khác, người đọc bấm vào là xem được ngay.

    Khác `resolve()` ở chỗ cho phép đi sâu vào thư mục con, nhưng vẫn khoá cứng
    trong thư mục app: `realpath` rồi so prefix nên `../../` hay symlink trỏ ra
    ngoài đều bị chặn. Ngoài app (vd `/etc/passwd`, apps khác) là không đọc được.
    """
    root = _app_root()
    path = (path or "").strip()
    if not path:
        frappe.throw(_("File path is required"))

    candidate = path if os.path.isabs(path) else os.path.join(root, path)
    candidate = os.path.realpath(candidate)

    if not candidate.startswith(root + os.sep):
        frappe.throw(_("Only .md files inside the customize_erpnext app are allowed"))
    if not candidate.lower().endswith(".md"):
        frappe.throw(_("Only .md files are allowed"))

    return candidate


# Hai cách nhận ra một đường dẫn .md trong bài:
#
#   1. Nằm trong dấu backtick — `workspace_setup.md`. Backtick là dấu hiệu người
#      viết cố ý trỏ tới file, nên không cần có thư mục; nhờ vậy file ở ngay gốc
#      app cũng đưa vào chỉ mục được.
#   2. Đứng trần hoặc trong ngoặc của link markdown — lúc này BẮT BUỘC có dấu /,
#      nếu không thì mọi câu văn nhắc "xem README.md" đều bị nhặt nhầm.
_MD_TICKED_RE = re.compile(r"`([^`\n]+?\.md)`", re.IGNORECASE)
_MD_PATH_RE = re.compile(r"[\w./~-]*/[\w./ -]*?\.md\b", re.IGNORECASE)


def extract_md_paths(text):
    """Các đường dẫn .md xuất hiện trong nội dung, giữ nguyên thứ tự, bỏ trùng."""
    text = text or ""
    seen, out = set(), []
    for raw in _MD_TICKED_RE.findall(text) + _MD_PATH_RE.findall(text):
        p = raw.strip().strip("`<>()[]").strip()
        # bỏ ký tự đại diện: `docs/mindmap/*.md` là mẫu glob trong câu văn,
        # không phải một file cụ thể -> đừng liệt kê rồi báo "không tìm thấy"
        if "*" in p or "?" in p:
            continue
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


@frappe.whitelist()
def list_linked_docs(category, filename):
    """Danh sách file .md mà một bài trỏ tới, kèm tiêu đề để hiện ra menu.

    File nào nằm ngoài app hoặc không tồn tại thì vẫn trả về, có cờ `exists`,
    để trang nói rõ "đường dẫn hỏng" thay vì im lặng bỏ qua.
    """
    _check_view()
    doc = get_doc_content(category, filename)
    root = _app_root()

    out = []
    for path in extract_md_paths(doc["content"]):
        item = {"path": path, "exists": 0, "title": path.rsplit("/", 1)[-1], "rel": path}
        try:
            full = resolve_app_doc(path)
        except Exception:
            out.append(item)          # ngoài app hoặc không hợp lệ
            continue
        if os.path.isfile(full):
            st = os.stat(full)
            # Không có heading nào thì lấy tên thư mục: cả chục file cùng tên
            # README.md, hiện "README.md" thì không phân biệt được cái nào.
            base = os.path.basename(full)
            fallback = (os.path.basename(os.path.dirname(full)) + "/" + base
                        if base.lower() == "readme.md" else base)
            item.update({
                "exists": 1,
                "rel": os.path.relpath(full, root),
                "title": _title_of(full, fallback),
                "size": st.st_size,
                "modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        out.append(item)

    return {"category": category, "name": doc["name"], "links": out}


@frappe.whitelist()
def get_app_doc_html(path):
    """Nội dung một file .md bất kỳ trong app, đã dựng thành HTML."""
    _check_view()
    full = resolve_app_doc(path)
    if not os.path.isfile(full):
        frappe.throw(_("File not found: {0}").format(path))

    with open(full, encoding="utf-8") as f:
        content = f.read()

    return {
        "rel": os.path.relpath(full, _app_root()),
        "title": _title_of(full, os.path.basename(full)),
        "content": content,
        "html": frappe.utils.md_to_html(content) or "",
        "modified": datetime.datetime.fromtimestamp(os.path.getmtime(full)).strftime("%Y-%m-%d %H:%M"),
    }


# Thư mục bỏ qua khi quét toàn app: thư viện ngoài và bản sao lưu.
_SEARCH_SKIP = ("/node_modules/", "/pyzk-master/", "/.git/")

# Cache nội dung file để gõ từng ký tự không phải đọc lại 56 file mỗi lần.
# Khoá theo mtime nên sửa file là tự nạp lại, không cần xoá cache tay.
_SEARCH_CACHE = {}


def _strip_accents(text):
    """Bỏ dấu tiếng Việt để gõ 'nghi phep' vẫn ra 'nghỉ phép'.

    NFD tách nguyên âm khỏi dấu, rồi bỏ mọi ký tự thuộc nhóm dấu (Mn). Riêng
    đ/Đ không phải nguyên âm có dấu nên NFD không tách, phải thay tay.
    """
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if not unicodedata.combining(c))


def _norm(text):
    return _strip_accents(text).lower()


def _iter_app_docs():
    """(đường dẫn tuyệt đối, đường dẫn tương đối) của mọi .md trong app."""
    root = _app_root()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git")]
        for name in filenames:
            if not name.lower().endswith(".md"):
                continue
            full = os.path.join(dirpath, name)
            if any(skip in full for skip in _SEARCH_SKIP):
                continue
            yield full, os.path.relpath(full, root)


def _cached_doc(full):
    """Nội dung file + bản đã bỏ dấu, cache theo mtime.

    Cache cả bản đã chuẩn hoá chứ không chỉ nội dung thô: chi phí thật của mỗi
    lần gõ là bỏ dấu ~800KB văn bản, không phải đọc đĩa. Chỉ cache nội dung thô
    thì gõ 10 ký tự vẫn tốn 10 lần chuẩn hoá.
    """
    try:
        mtime = os.path.getmtime(full)
    except OSError:
        return None

    hit = _SEARCH_CACHE.get(full)
    if hit and hit["mtime"] == mtime:
        return hit

    try:
        with open(full, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None

    title = _title_of(full, os.path.basename(full))
    doc = {
        "mtime": mtime,
        "text": text,
        "n_text": _norm(text),
        "title": title,
        "n_title": _norm(title),
    }
    _SEARCH_CACHE[full] = doc
    return doc


def _snippet(line, pos, width=60):
    start = max(0, pos - width)
    end = min(len(line), pos + width)
    return ("…" if start else "") + line[start:end].strip() + ("…" if end < len(line) else "")


@frappe.whitelist()
def search_docs(query, limit=40):
    """Tìm trong MỌI file .md của app, không chỉ docs/user_manual.

    Khớp trên tên file, tiêu đề và nội dung; bỏ dấu và không phân biệt hoa
    thường. Điểm xếp hạng: tiêu đề > tên file > nội dung, cộng thêm theo số lần
    xuất hiện để bài nói nhiều về từ khoá đó lên trước.
    """
    _check_view()

    q = _norm((query or "").strip())
    if len(q) < 2:
        return {"query": query, "results": []}

    limit = int(limit or 40)
    results = []

    for full, rel in _iter_app_docs():
        doc = _cached_doc(full)
        if not doc or not doc["text"]:
            continue

        text, title = doc["text"], doc["title"]
        n_rel = _norm(rel)

        hits = doc["n_text"].count(q)
        in_title = q in doc["n_title"]
        in_path = q in n_rel
        if not (hits or in_title or in_path):
            continue

        score = (100 if in_title else 0) + (40 if in_path else 0) + min(hits, 20)

        # đoạn trích: dòng đầu tiên có chứa từ khoá
        snippet, line_no = "", 0
        for i, line in enumerate(text.split("\n"), 1):
            pos = _norm(line).find(q)
            if pos >= 0 and line.strip():
                snippet, line_no = _snippet(line.strip(), pos), i
                break

        results.append({
            "rel": rel,
            "title": title,
            "score": score,
            "hits": hits,
            "line": line_no,
            "snippet": snippet,
            # file trong docs/user_manual mở bằng get_doc_html, còn lại get_app_doc_html
            "in_manual": 1 if rel.startswith(os.path.join(DOCS_SUBDIR, "user_manual") + os.sep) else 0,
        })

    results.sort(key=lambda r: (-r["score"], r["rel"]))
    return {"query": query, "total": len(results), "results": results[:limit]}


# Bản scan quy định gốc của công ty (có dấu). Để riêng thư mục vì đây là
# chứng từ, không phải tài liệu sửa được — chỉ xem và tải.
PDF_SUBDIR = os.path.join(DOCS_SUBDIR, "user_manual", "pdf")


def _pdf_dir():
    return os.path.realpath(os.path.join(frappe.get_app_path("customize_erpnext"), PDF_SUBDIR))


def resolve_pdf(filename):
    """Đường dẫn tuyệt đối của một PDF trong docs/user_manual/pdf, đã kiểm tra.

    Cùng luật với resolve(): chỉ nhận tên file trần, không nhận đường dẫn.
    """
    root = _pdf_dir()
    filename = (filename or "").strip()
    if not filename:
        frappe.throw(_("File name is required"))
    if os.path.basename(filename) != filename or filename in (".", ".."):
        frappe.throw(_("Only file names inside {0} are allowed").format("pdf"))
    if not filename.lower().endswith(".pdf"):
        frappe.throw(_("Only .pdf files are allowed"))

    candidate = os.path.realpath(os.path.join(root, filename))
    if not candidate.startswith(root + os.sep):
        frappe.throw(_("Only files inside {0} are allowed").format("pdf"))
    return candidate


@frappe.whitelist()
def list_pdfs():
    """Danh sách bản scan quy định gốc."""
    _check_view()
    root = _pdf_dir()
    if not os.path.isdir(root):
        return {"dir": root, "files": []}

    files = []
    for name in sorted(os.listdir(root)):
        if not name.lower().endswith(".pdf"):
            continue
        full = os.path.join(root, name)
        if not os.path.isfile(full):
            continue
        st = os.stat(full)
        files.append({
            "name": name,
            "size": st.st_size,
            "size_mb": round(st.st_size / 1048576.0, 1),
            "modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return {"dir": root, "files": files}


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_pdf(filename, download=0):
    """Trả về nội dung PDF.

    `download=0` -> hiện thẳng trong trang (Content-Disposition: inline), để nhúng vào
    <iframe> xem được bằng trình đọc PDF sẵn có của trình duyệt.
    `download=1` -> trình duyệt tải file về.

    Phải là GET vì <iframe src=...> và link tải đều là GET; POST thì trình duyệt
    không nhúng được.
    """
    _check_view()
    full = resolve_pdf(filename)
    if not os.path.isfile(full):
        frappe.throw(_("File not found: {0}").format(filename))

    with open(full, "rb") as f:
        content = f.read()

    frappe.local.response.filename = os.path.basename(full)
    frappe.local.response.filecontent = content
    frappe.local.response.content_type = "application/pdf"
    frappe.local.response.display_content_as = "attachment" if int(download or 0) else "inline"
    frappe.local.response.type = "download"


@frappe.whitelist()
def save_doc(category, filename, content, known_mtime=None):
    """Ghi nội dung vào file .md, giữ bản trước ở file .bak.

    `known_mtime` là mtime lúc trang tải file về. Nếu file trên đĩa đã đổi so với
    lúc đó thì từ chối ghi: hai người cùng mở một file, người lưu sau sẽ xoá mất
    sửa của người trước mà không ai biết. Bỏ trống tham số này là ép ghi đè.
    """
    _check_edit()

    full = resolve(category, filename)
    if not os.path.isfile(full):
        frappe.throw(_("File not found: {0}").format(filename))

    # Nội dung rỗng gần như luôn là lỗi phía trình duyệt, đừng để nó xoá sạch tài liệu
    if content is None or not str(content).strip():
        frappe.throw(_("Content is required"))

    current_mtime = int(os.path.getmtime(full))
    if known_mtime not in (None, "", "0", 0) and int(known_mtime) != current_mtime:
        frappe.throw(
            _("{0} was changed on the server after you opened it. Reload it first, "
              "otherwise you would overwrite someone else's edit.").format(filename)
        )

    # Bản lưu trước khi ghi, để khôi phục nếu sửa sai
    with open(full, encoding="utf-8") as f:
        previous = f.read()
    with open(full + ".bak", "w", encoding="utf-8") as f:
        f.write(previous)

    with open(full, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "category": category,
        "name": os.path.basename(full),
        "bytes": len(content.encode("utf-8")),
        "mtime": int(os.path.getmtime(full)),
    }

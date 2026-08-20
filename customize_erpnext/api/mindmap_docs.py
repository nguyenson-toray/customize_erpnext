"""API cho trang Mindmap Viewer: liệt kê, đọc và ghi file markdown tài liệu,
cùng bảng dịch phần mô tả để trang đổi qua lại Anh / Việt.

Chỉ cho phép truy cập file .md nằm trong customize_erpnext/docs/mindmap
(trước 19/08/2026 nằm ở 01_docs).
Việc quyết định file nào đọc được giao hết cho api/docs_reader.py để trang
/mindmap và trang /dev-tool dùng chung một luật, không lệch nhau.

Hai file dịch, đều nằm cạnh trang trong www/mindmap:
  vi.csv       - do scripts/build_mindmap.py sinh ra, KHÔNG sửa tay (build sẽ ghi đè)
  vi_auto.csv  - cache bản dịch máy, do API translate_texts ghi thêm vào
Cả hai cùng dạng: english,vietnamese
"""

import csv
import datetime
import io
import json
import os

import frappe
from frappe import _

from customize_erpnext.api import docs_reader

DOCS_CATEGORY = "mindmap"
DOCS_SUBDIR = os.path.join(docs_reader.DOCS_SUBDIR, DOCS_CATEGORY)
LANG_SUBDIR = os.path.join("www", "mindmap")
LANG_FILE = "vi.csv"
LANG_AUTO_FILE = "vi_auto.csv"
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
TRANSLATE_LIMIT = 60
# Đọc tài liệu: mọi người dùng đã đăng nhập (Guest thì không)
# Ghi file tài liệu: chỉ role Administrator
EDIT_ROLES = ("Administrator",)


def _can_edit():
    return any(r in frappe.get_roles() for r in EDIT_ROLES)


def _check_view():
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to read documentation files"),
                     frappe.PermissionError)


def _check_edit():
    if not _can_edit():
        frappe.throw(
            _("Only the Administrator role can edit documentation files"),
            frappe.PermissionError,
        )


def _docs_dir():
    return docs_reader.category_dir(DOCS_CATEGORY)


def _resolve(path):
    """Nhận tên file hoặc đường dẫn, trả về đường dẫn tuyệt đối đã kiểm tra.

    Thư mục tài liệu phẳng (không có thư mục con), nên phần thư mục của giá trị
    gửi lên bị bỏ đi — ô "file name or path .md" trên trang vẫn nhận đường dẫn cũ
    kiểu `01_docs/hr_mindmap.md` hay `docs/mindmap/hr_mindmap.md` mà không lỗi. Việc kiểm tra thật nằm ở
    docs_reader.resolve.
    """
    if not path or not path.strip():
        frappe.throw(_("File path is required"))

    return docs_reader.resolve(DOCS_CATEGORY, os.path.basename(path.strip()))


def _rel(abs_path):
    return os.path.relpath(abs_path, _docs_dir())


@frappe.whitelist()
def list_docs():
    """Danh sách file .md trong thư mục tài liệu."""
    _check_view()
    root = _docs_dir()
    if not os.path.isdir(root):
        return {"dir": root, "files": []}

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
            "path": name,
            "size": st.st_size,
            "modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return {"dir": root, "files": files}


@frappe.whitelist()
def read_doc(path):
    """Đọc nội dung một file .md."""
    _check_view()
    full = _resolve(path)
    if not os.path.isfile(full):
        # Nói luôn thư mục đang tìm và những file đang có: lỗi này hay xảy ra sau
        # khi đổi tên / chuyển thư mục, và một câu "File not found" trống không
        # thì không đủ để biết nên sửa gì.
        root = _docs_dir()
        available = sorted(
            n for n in os.listdir(root) if n.lower().endswith(".md")
        ) if os.path.isdir(root) else []
        frappe.throw(_("File not found: {0} (looked in {1}; available: {2})").format(
            os.path.basename(full), root, ", ".join(available) or "-"))

    with open(full, encoding="utf-8") as f:
        content = f.read()

    return {"path": _rel(full), "content": content}


def _lang_path(name):
    return os.path.join(frappe.get_app_path("customize_erpnext"), LANG_SUBDIR, name)


def _read_pairs(path):
    """Đọc file csv english,vietnamese -> dict {vietnamese: english}."""
    pairs = {}
    if not os.path.isfile(path):
        return pairs
    with open(path, encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue
            en, vi = row[0].strip(), row[1].strip()
            if not en or not vi or en.startswith("#"):
                continue
            pairs[vi] = en
    return pairs


@frappe.whitelist()
def read_lang():
    """Bảng dịch mô tả: {tiếng Việt: tiếng Anh}. Bản dịch máy chỉ dùng khi chưa có bản chuẩn."""
    _check_view()
    auto = _read_pairs(_lang_path(LANG_AUTO_FILE))
    manual = _read_pairs(_lang_path(LANG_FILE))
    merged = dict(auto)
    merged.update(manual)   # bản chuẩn ưu tiên hơn bản dịch máy
    return {"map": merged, "manual": len(manual), "auto": len(auto)}


def _translate_one(text, source, target):
    import requests

    res = requests.get(
        TRANSLATE_URL,
        params={"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text},
        timeout=12,
    )
    res.raise_for_status()
    data = json.loads(res.text)
    # [[[ "bản dịch", "gốc", ...], [...]], ...] - nối các đoạn lại
    return "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()


@frappe.whitelist()
def translate_texts(texts, source="vi", target="en"):
    """Dịch các mô tả chưa có trong bảng, rồi cache vào vi_auto.csv.

    Cần máy chủ ra được internet. Nếu không ra được thì trả về lỗi rõ ràng để
    trang giữ nguyên tiếng Việt thay vì hiện trắng.
    Người không có quyền sửa vẫn dịch được để xem, chỉ không ghi cache lên máy chủ.
    """
    _check_view()

    if isinstance(texts, str):
        texts = json.loads(texts)
    texts = [t.strip() for t in (texts or []) if t and t.strip()]
    if not texts:
        return {"map": {}, "translated": 0, "failed": 0}

    known = _read_pairs(_lang_path(LANG_AUTO_FILE))
    known.update(_read_pairs(_lang_path(LANG_FILE)))

    todo, out = [], {}
    for t in texts:
        if t in known:
            out[t] = known[t]
        elif t not in todo:
            todo.append(t)
    todo = todo[:TRANSLATE_LIMIT]

    fresh, failed = {}, 0
    for t in todo:
        try:
            got = _translate_one(t, source, target)
            if got and got != t:
                fresh[t] = got
                out[t] = got
            else:
                failed += 1
        except Exception:
            failed += 1
            frappe.log_error(frappe.get_traceback(), "Mindmap translate failed")
            break   # mất mạng thì dừng luôn, đừng chờ hết danh sách

    if fresh and _can_edit():
        path = _lang_path(LANG_AUTO_FILE)
        new_file = not os.path.isfile(path)
        buf = io.StringIO()
        w = csv.writer(buf)
        if new_file:
            w.writerow(["# english", "vietnamese  (bản dịch máy, sửa tay được)"])
        for vi, en in fresh.items():
            w.writerow([en, vi])
        with open(path, "a", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())

    return {"map": out, "translated": len(fresh), "failed": failed,
            "remaining": max(0, len(texts) - len(out))}


@frappe.whitelist()
def write_doc(path, content):
    """Ghi nội dung vào file .md, giữ lại bản trước ở file .bak."""
    _check_edit()

    full = _resolve(path)
    if not os.path.isfile(full):
        frappe.throw(_("File not found: {0}").format(path))

    # Nội dung rỗng gần như luôn là lỗi phía trình duyệt, đừng để nó xoá sạch tài liệu
    if content is None or not content.strip():
        frappe.throw(_("Content is required"))

    # Bản lưu trước khi ghi, để khôi phục nếu sửa sai
    with open(full, encoding="utf-8") as f:
        previous = f.read()
    with open(full + ".bak", "w", encoding="utf-8") as f:
        f.write(previous)

    with open(full, "w", encoding="utf-8") as f:
        f.write(content)

    return {"path": _rel(full), "bytes": len(content.encode("utf-8"))}

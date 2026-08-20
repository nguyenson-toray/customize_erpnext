#!/usr/bin/env python3
"""Kiểm mọi .md trong app có đủ khung chuẩn.

Chạy:  python3 scripts/tests/check_md_structure.py --list

Khung chuẩn (4 dòng đầu file):

    # <Tên> — <mô tả ngắn>

    > **Mục đích:** một câu, viết cho người chưa biết chức năng này.
    > **Phạm vi:** doctype / module / trang liên quan.
    > **Trạng thái:** Đang chạy · **Cập nhật:** YYYY-MM-DD

Thoát mã 1 nếu có file thiếu, để cắm vào CI được.
"""
import os, re, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# docs/mindmap: file do build_mindmap.py SINH RA và có parser riêng của trang
# /mindmap — chèn H1 + blockquote vào là thêm node rác và làm gãy 4 test.
SKIP = ("/node_modules/", "/pyzk-master/", "/frontend/build/", "/public/dist/",
        "/docs/mindmap/")

def docs():
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in ("node_modules", ".git")]
        for n in sorted(fn):
            if n.lower().endswith(".md"):
                full = os.path.join(dp, n)
                if not any(s in full for s in SKIP):
                    yield full, os.path.relpath(full, ROOT)

def audit(full):
    lines = open(full, encoding="utf-8").read().split("\n")
    head = "\n".join(lines[:8])
    return {
        "h1": bool(lines and lines[0].startswith("# ")),
        "muc_dich": "**Mục đích:**" in head,
        "pham_vi": "**Phạm vi:**" in head,
        "trang_thai": "**Trạng thái:**" in head,
    }

if __name__ == "__main__":
    bad = ok = 0
    for full, rel in docs():
        a = audit(full)
        if all(a.values()):
            ok += 1
        else:
            bad += 1
            if "--list" in sys.argv:
                miss = [k for k, v in a.items() if not v]
                print(f"  {rel:<66} thiếu: {','.join(miss)}")
    print(f"\n{ok} file đủ khung / {ok+bad} tổng")
    sys.exit(1 if bad else 0)

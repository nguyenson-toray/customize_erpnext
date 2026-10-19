"""Trước khi update: import nào của customize_erpnext sẽ GÃY ở phiên bản đích (đọc git, không đụng code chạy).

Chạy từ ~/frappe-bench/apps (cần `git fetch upstream --tags` trước):
    python3 -I customize_erpnext/customize_erpnext/scripts/upgrade_checks/scan_imports.py frappe=v16.52.0 erpnext=v16.51.1 hrms=v16.51.0
Chỉ báo import đang chạy được ở HEAD mà mất ở ref đích. 17/10/2026 bắt được
`hrms.utils.holiday_list.get_assigned_holiday_lists_to_employee_and_company` (xoá ở hrms v16.20).
"""
import ast, os, subprocess, sys
APP = "customize_erpnext/customize_erpnext"
TARGET = dict(a.split("=") for a in sys.argv[1:])   # app=ref
cache = {}
def src(app, ref, mod):
    path = mod.replace(".", "/")
    for cand in (path + ".py", path + "/__init__.py"):
        r = subprocess.run(["git", "-C", app, "show", f"{ref}:{cand}"], capture_output=True, text=True)
        if r.returncode == 0: return r.stdout
    return None
def names(app, ref, mod):
    k = (app, ref, mod)
    if k not in cache:
        s = src(app, ref, mod)
        if s is None: cache[k] = None
        else:
            t = ast.parse(s); ns = set()
            for n in ast.walk(t):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): ns.add(n.name)
                elif isinstance(n, ast.Assign):
                    for tg in n.targets:
                        if isinstance(tg, ast.Name): ns.add(tg.id)
                elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name): ns.add(n.target.id)
                elif isinstance(n, (ast.ImportFrom, ast.Import)):
                    for a in n.names: ns.add((a.asname or a.name).split(".")[0])
            cache[k] = ns
    return cache[k]
bad = 0; total = 0
for root, _, files in os.walk(APP):
    for f in files:
        if not f.endswith(".py"): continue
        p = os.path.join(root, f)
        try: tree = ast.parse(open(p).read())
        except Exception: continue
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module:
                app = n.module.split(".")[0]
                if app not in TARGET: continue
                ref = TARGET[app]
                for a in n.names:
                    total += 1
                    now = names(app, "HEAD", n.module); new = names(app, ref, n.module)
                    def ok(ns, r):
                        return ns is not None and (a.name == "*" or a.name in ns or names(app, r, n.module + "." + a.name) is not None)
                    if ok(now, "HEAD") and not ok(new, ref):
                        bad += 1; print(f"BREAKS: {p}:{n.lineno} from {n.module} import {a.name}")
print(f"{total} imports checked, {bad} newly broken")

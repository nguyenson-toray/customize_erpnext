"""Trước khi update: hàm upstream nào mà customize_erpnext monkey-patch / kế thừa-override bị upstream SỬA.

Chạy từ ~/frappe-bench/apps:
    python3 -I customize_erpnext/customize_erpnext/scripts/upgrade_checks/scan_overridden_changed.py frappe=v16.52.0 erpnext=v16.51.1 hrms=v16.51.0
Mỗi dòng "changed" phải xem diff (func_diff.py): đổi CHỮ KÝ = override gãy (TypeError), đổi THÂN = mình
che mất bản sửa upstream. 17/10/2026 bắt được SalarySlip.calculate_lwp_ppl_and_absent_days_based_on_attendance
(thêm tham số half_day_holidays) và ShiftType.process_auto_attendance (thêm check_permission).
"""
import ast, os, subprocess, importlib
import sys
T = dict(a.split("=") for a in sys.argv[1:])   # app=ref, vd. hrms=v16.51.0
APP = "customize_erpnext/customize_erpnext"
def get(app, ref, path):
    r = subprocess.run(["git", "-C", app, "show", f"{ref}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None
def find_mod(dotted):
    parts = dotted.split("."); app = parts[0]
    for i in range(len(parts), 0, -1):
        for cand in ("/".join(parts[:i]) + ".py", "/".join(parts[:i]) + "/__init__.py"):
            if get(app, "HEAD", cand) is not None: return app, cand, parts[i:]
    return None
def func_src(code, qual):
    if code is None: return None
    t = ast.parse(code); node = t
    for q in qual:
        node = next((n for n in getattr(node, "body", []) if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == q), None)
        if node is None: return None
    return ast.unparse(node)
targets = set()
# 1) monkey patches: <alias>.<attr> = ...  where alias is an upstream module/class
for root, _, files in os.walk(APP):
    for f in files:
        if not f.endswith(".py"): continue
        p = os.path.join(root, f)
        try: t = ast.parse(open(p).read())
        except Exception: continue
        alias = {}
        for n in ast.walk(t):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.split(".")[0] in T: alias[a.asname or a.name] = a.name
            if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] in T:
                for a in n.names: alias[a.asname or a.name] = n.module + "." + a.name
        for n in ast.walk(t):
            if isinstance(n, ast.Assign):
                for tg in n.targets:
                    if isinstance(tg, ast.Attribute) and not tg.attr.startswith("_original") and not tg.attr.startswith("_tiqn"):
                        base = ast.unparse(tg.value); head = base.split(".")[0]
                        full = alias.get(head, base if head in T else None)
                        if full:
                            full = full + base[len(head):] if head in alias else full
                            targets.add((full + "." + tg.attr, p, n.lineno))
            # 2) subclasses of upstream classes: overridden methods
            if isinstance(n, ast.ClassDef):
                for b in n.bases:
                    bn = ast.unparse(b); full = alias.get(bn.split(".")[0])
                    if full:
                        for m in n.body:
                            if isinstance(m, ast.FunctionDef):
                                targets.add((full + bn[len(bn.split('.')[0]):] + "." + m.name, p, m.lineno))
changed = []
for dotted, p, line in sorted(targets):
    loc = find_mod(dotted)
    if not loc: continue
    app, path, qual = loc
    if not qual: continue
    a, b = func_src(get(app, "HEAD", path), qual), func_src(get(app, T[app], path), qual)
    if a is None: continue  # method added by us, not an override
    if a != b:
        changed.append((dotted, p.replace(APP + "/", ""), line, "REMOVED upstream" if b is None else "changed"))
for c in changed: print(*c)
print(len(targets), "override targets;", len(changed), "changed upstream")

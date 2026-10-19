"""Diff 1 hàm/method giữa HEAD và ref đích của một app.

    python3 -I func_diff.py hrms v16.51.0 hrms/payroll/doctype/salary_slip/salary_slip.py SalarySlip get_holidays_for_employee
(chạy từ ~/frappe-bench/apps)
"""
import ast, subprocess, sys, difflib
app, ref, path, *qual = sys.argv[1:]
def get(r):
    o = subprocess.run(["git","-C",app,"show",f"{r}:{path}"],capture_output=True,text=True).stdout
    node = ast.parse(o)
    for q in qual:
        node = next(n for n in node.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==q)
    return ast.get_source_segment(o, node).splitlines()
a, b = get("HEAD"), get(ref)
print(f"#### {'.'.join(qual)}  ({len(a)}→{len(b)} lines)")
for l in list(difflib.unified_diff(a, b, lineterm="", n=1))[2:]: print(l)

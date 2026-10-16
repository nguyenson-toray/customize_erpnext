"""End-to-end check of the Employee Portal (Zalo Mini App) backend - M1.

Runs against the real site and rolls everything back. Covers the contract
(API_CONTRACT.md) AND the security rules: one employee's token must never reach
another employee's data, whatever the client sends.

Run:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    exec(open('../apps/customize_erpnext/customize_erpnext/employee_portal/test_employee_portal.py').read())"

🔴 NOTHING here may commit, and endpoint errors must not roll back: the portal
wrapper calls frappe.db.rollback() on every ok:false (correct in production), which
would wipe this script's fixtures mid-run. Both are patched to no-ops for the run
and restored before the final rollback.
⚠ Assertions are scoped to records this script creates (zalo ids "unit-<uuid>",
periods 2030-xx) - the test team uses TIQN-0148 / TIQN-1405 on the same database.
"""

import io
import uuid
from unittest import mock

import frappe
from frappe.utils import add_days, add_to_date, flt, getdate, now_datetime, today

import customize_erpnext.api.employee_portal as api
from customize_erpnext.api.employee_portal import auth as auth_mod
from customize_erpnext.api.employee_portal.core import hash_token
from customize_erpnext.employee_portal import payslip_admin, utils
from customize_erpnext.utils import zalo_graph

ok = fail = 0
RUN = uuid.uuid4().hex[:8]
EMP_A, EMP_B = "TIQN-0148", "TIQN-1405"

_REAL_COMMIT, _REAL_ROLLBACK = frappe.db.commit, frappe.db.rollback
frappe.db.commit = lambda *a, **k: None
frappe.flags.in_test = True


def check(label, got, want):
	global ok, fail
	if got == want:
		ok += 1
		print(f"  ok   {label}")
	else:
		fail += 1
		print(f"  FAIL {label}: got {got!r}, want {want!r}")


def call(fn, token=None, version=None, **kwargs):
	"""Call an endpoint the way an HTTP request would: headers in, envelope out."""
	headers = {}
	if token:
		headers["X-Portal-Token"] = token
	if version:
		headers["X-Portal-Client-Version"] = version

	def fake_header(name, default=None):
		return headers.get(name, default)

	with mock.patch.object(frappe, "get_request_header", side_effect=fake_header), mock.patch.object(
		frappe.db, "rollback", lambda *a, **k: None
	):
		result = fn(**kwargs)
	frappe.set_user("Administrator")
	return result


def code(res):
	return None if res.get("ok") else res["error"]["code"]


def phone_of(emp):
	return frappe.db.get_value("Employee", emp, "cell_number")


# ---------------------------------------------------------------------------
print("\n=== utils ===")
for raw in ("0962200054", "84962200054", "+84 962 200 054", "962200054"):
	check(f"phone_key({raw})", utils.phone_key(raw), "962200054")
check("phone_key too short", utils.phone_key("12345"), None)
check("mask_phone", utils.mask_phone("84962200054"), "09•• ••• 054")
check("period_bounds 2026-08", tuple(str(d) for d in utils.period_bounds("2026-08")), ("2026-07-26", "2026-08-25"))
check("period_bounds 2026-01", tuple(str(d) for d in utils.period_bounds("2026-01")), ("2025-12-26", "2026-01-25"))
check("period_of_date 25/08", utils.period_of_date("2026-08-25"), "2026-08")
check("period_of_date 26/08", utils.period_of_date("2026-08-26"), "2026-09")
check("period_of_date 26/12", utils.period_of_date("2026-12-26"), "2027-01")
check("shift_period", utils.shift_period("2026-01", -1), "2025-12")
for raw, want in (("10-2026", "2026-10"), ("10/2026", "2026-10"), ("2026-10", "2026-10"), ("13-2026", None), ("", None)):
	check(f"parse_period_cell({raw!r})", utils.parse_period_cell(raw), want)
import datetime as _dt

check("parse_period_cell(date)", utils.parse_period_cell(_dt.datetime(2026, 10, 1)), "2026-10")
check("initials", utils.initials("Nguyễn Văn An"), "NA")
check("employee_access Active", utils.employee_access({"status": "Active"})[0], "ACTIVE")
check(
	"employee_access Left in window ('Left ' with space)",
	utils.employee_access({"status": "Left ", "relieving_date": add_days(today(), -10)})[0],
	"READ_ONLY",
)
check("employee_access Left expired", utils.employee_access({"status": "Left", "relieving_date": add_days(today(), -61)})[0], "EXPIRED")
check("read_only_days is 30", utils.setting_int("read_only_days", 0), 30)
check("employee_access Inactive", utils.employee_access({"status": "Inactive"})[0], "EXPIRED")


# ---------------------------------------------------------------------------
print("\n=== login decision table ===")
zid_a, zid_b = f"unit-{RUN}-a", f"unit-{RUN}-b"
r = auth_mod.complete_login(zid_a, "84" + utils.phone_key(phone_of(EMP_A)))
check("A: ACTIVE", r["result"], "ACTIVE")
check("A: employee", r["employee"]["employee_id"], EMP_A)
check("A: token issued", bool(r["token"]) and len(r["token"]) >= 40, True)
check("A: token stored only as hash", frappe.db.exists("TIQN Portal Session", {"token_hash": hash_token(r["token"])}) is not None, True)
check("A: token not stored in clear", frappe.db.exists("TIQN Portal Session", {"token_hash": r["token"]}), None)
check("A: masked phone", r["masked_phone"].count("•"), 5)
check("A: every contract key present", sorted(r), sorted(["result", "token", "expires_on", "zalo_user_id", "masked_phone", "employee", "access", "oa", "expired_on", "message"]))
check("A: avatar_url absolute + encoded", (r["employee"]["avatar_url"] or "").startswith("http") and " " not in r["employee"]["avatar_url"], True)
check("avatar_url: none -> None", auth_mod.avatar_url(None), None)
check("avatar_url: private -> None", auth_mod.avatar_url("/private/files/x.jpg"), None)
check("avatar_url: missing file -> None", auth_mod.avatar_url("/files/employee_photos/__missing__.jpg"), None)
TOKEN_A = r["token"]
TOKEN_B = auth_mod.complete_login(zid_b, phone_of(EMP_B))["token"]

r = auth_mod.complete_login(f"unit-{RUN}-nf", "0900000" + RUN[:3].translate(str.maketrans("abcdef", "123456")))
check("unknown phone: NOT_FOUND", r["result"], "NOT_FOUND")
check("NOT_FOUND: no token", r["token"], None)
check("NOT_FOUND: account kept for HR report", frappe.db.get_value("TIQN Portal Account", f"unit-{RUN}-nf", "last_result"), "NOT_FOUND")

# New account without a matching employee starts auto-disabled, unlocks on a matching phone.
acc_nf = frappe.get_doc("TIQN Portal Account", f"unit-{RUN}-nf")
check("NOT_FOUND new account: auto-disabled", (acc_nf.disabled, acc_nf.auto_disabled), (1, 1))
check("ACTIVE new account: not disabled", frappe.db.get_value("TIQN Portal Account", zid_a, ["disabled", "auto_disabled"]), (0, 0))
r = auth_mod.complete_login(f"unit-{RUN}-nf", None, "STORED_PHONE")
check("auto-disabled + no match: still NOT_FOUND (not DISABLED)", r["result"], "NOT_FOUND")
r = auth_mod.complete_login(f"unit-{RUN}-nf", phone_of(EMP_A))
check("auto-disabled + Zalo phone matches: ACTIVE", r["result"], "ACTIVE")
check("auto-disabled cleared after match", frappe.db.get_value("TIQN Portal Account", f"unit-{RUN}-nf", ["disabled", "auto_disabled"]), (0, 0))

zid_ad = f"unit-{RUN}-ad"
r = auth_mod.complete_login(zid_ad, None, "STORED_PHONE")
check("no phone: NO_PHONE (not DISABLED)", r["result"], "NO_PHONE")
check("NO_PHONE new account: auto-disabled", frappe.db.get_value("TIQN Portal Account", zid_ad, ["disabled", "auto_disabled"]), (1, 1))
acc_ad = frappe.get_doc("TIQN Portal Account", zid_ad)
acc_ad.phone = phone_of(EMP_B)
acc_ad.save(ignore_permissions=True)
check("HR assigns matching phone: enabled", (acc_ad.disabled, acc_ad.auto_disabled, acc_ad.employee), (0, 0, EMP_B))
check("HR-assigned phone then login: ACTIVE", auth_mod.complete_login(zid_ad, None, "STORED_PHONE")["result"], "ACTIVE")

acc_hr = frappe.new_doc("TIQN Portal Account")
acc_hr.zalo_user_id = f"unit-{RUN}-hr"
acc_hr.insert(ignore_permissions=True)
check("HR creates without phone: auto-disabled", (acc_hr.disabled, acc_hr.auto_disabled), (1, 1))
acc_hr.auto_disabled = 0  # as if HR ticked Disabled by hand
acc_hr.save(ignore_permissions=True)
acc_hr.phone = phone_of(EMP_B)
acc_hr.save(ignore_permissions=True)
check("hand-disabled stays disabled after matching phone", acc_hr.disabled, 1)
check("hand-disabled + match: DISABLED", auth_mod.complete_login(f"unit-{RUN}-hr", None, "STORED_PHONE")["result"], "DISABLED")
acc_hr.reload()
acc_hr.disabled = 0
acc_hr.save(ignore_permissions=True)
acc_hr.disabled = 1
acc_hr.save(ignore_permissions=True)
check("HR ticks Disabled by hand: not auto", acc_hr.auto_disabled, 0)

zid_d = f"unit-{RUN}-d"
auth_mod.complete_login(zid_d, phone_of(EMP_A))
frappe.db.set_value("TIQN Portal Account", zid_d, "disabled", 1)
r = auth_mod.complete_login(zid_d, phone_of(EMP_A))
check("disabled account: DISABLED", r["result"], "DISABLED")
check("DISABLED: no token", r["token"], None)

left_recent = frappe.db.sql(
	"""SELECT name, cell_number FROM tabEmployee WHERE TRIM(status)='Left' AND relieving_date > %s
	   AND IFNULL(cell_number,'')!='' ORDER BY relieving_date DESC LIMIT 20""",
	add_days(today(), -25),
	as_dict=True,
)


def owns_phone(e):
	matches = utils.find_employees_by_phone(e.cell_number)
	return bool(matches) and matches[0].name == e.name


left_recent = [e for e in left_recent if owns_phone(e)]
if left_recent:
	r = auth_mod.complete_login(f"unit-{RUN}-ro", left_recent[0].cell_number)
	check("recently left: READ_ONLY", r["result"], "READ_ONLY")
	check("READ_ONLY: access.mode", r["access"]["mode"], "READ_ONLY")
	check("recently left: new account NOT auto-disabled", frappe.db.get_value("TIQN Portal Account", f"unit-{RUN}-ro", "disabled"), 0)
else:
	print("  skip READ_ONLY (no recently-left employee with a unique phone)")

left_old = frappe.db.sql(
	"""SELECT name, cell_number FROM tabEmployee WHERE TRIM(status)='Left' AND relieving_date < %s
	   AND IFNULL(cell_number,'')!='' ORDER BY relieving_date DESC LIMIT 50""",
	add_days(today(), -90),
	as_dict=True,
)
left_old = [e for e in left_old if owns_phone(e)]
if left_old:
	r = auth_mod.complete_login(f"unit-{RUN}-ex", left_old[0].cell_number)
	check("left long ago: EXPIRED", r["result"], "EXPIRED")
	check("EXPIRED: expired_on set", bool(r["expired_on"]), True)
	check("left long ago: new account auto-disabled", frappe.db.get_value("TIQN Portal Account", f"unit-{RUN}-ex", ["disabled", "auto_disabled"]), (1, 1))
	r = auth_mod.complete_login(f"unit-{RUN}-ex", None, "STORED_PHONE")
	check("auto-disabled + left long ago: still EXPIRED (not DISABLED)", r["result"], "EXPIRED")


print("\n=== login endpoint with Zalo mocked ===")
with mock.patch.object(zalo_graph, "get_phone", return_value="84" + utils.phone_key(phone_of(EMP_A))), mock.patch.object(
	zalo_graph, "get_user_id", return_value=(f"unit-{RUN}-http", "Test")
):
	r = call(api.login, access_token="at", phone_token="pt")
check("login: ok envelope", r["ok"], True)
check("login: ACTIVE", r["data"]["result"], "ACTIVE")
check("login: server_time", bool(r.get("server_time")), True)
r = call(api.login, access_token="", phone_token="pt")
check("login without access_token", (code(r), r["error"]["field"]), ("ZALO_TOKEN_INVALID", "access_token"))

with mock.patch.object(zalo_graph, "_secret", return_value="s"), mock.patch.object(
	zalo_graph, "_get", return_value={"error": 119, "message": "code has already been used"}
):
	check("Zalo 119 -> ZALO_TOKEN_USED", code(call(api.login, access_token="at", phone_token="pt")), "ZALO_TOKEN_USED")
with mock.patch.object(zalo_graph, "_secret", return_value="s"), mock.patch.object(
	zalo_graph, "_get", return_value={"error": 118, "message": "code is invalid"}
):
	check("Zalo 118 -> ZALO_SERVER_CONFIG", code(call(api.login, access_token="at", phone_token="pt")), "ZALO_SERVER_CONFIG")
with mock.patch.dict(frappe.conf, {"zalo_app_employee_portal_secret_key": ""}):
	check("no secret configured -> ZALO_SERVER_CONFIG", code(call(api.login, access_token="at", phone_token="pt")), "ZALO_SERVER_CONFIG")


# ---------------------------------------------------------------------------
print("\n=== login without a phone token / HR-assigned phone ===")
zid_np = f"unit-{RUN}-np"
with mock.patch.object(zalo_graph, "get_user_id", return_value=(zid_np, "Test")), mock.patch.object(zalo_graph, "get_phone") as gp:
	r = call(api.login, access_token="at")
	check("no phone_token: Zalo phone API not called", gp.called, False)
check("unknown user, no phone -> NO_PHONE", r["data"]["result"], "NO_PHONE")
check("NO_PHONE returns own zalo id for HR", r["data"]["zalo_user_id"], zid_np)
check("NO_PHONE: no token", r["data"]["token"], None)
check("NO_PHONE account recorded", frappe.db.get_value("TIQN Portal Account", zid_np, "last_result"), "NO_PHONE")

acc = frappe.get_doc("TIQN Portal Account", zid_np)
acc.phone = "84" + utils.phone_key(phone_of(EMP_A))
acc.save(ignore_permissions=True)
check("HR assigns phone: normalised", acc.phone, "0" + utils.phone_key(phone_of(EMP_A)))
check("HR assigns phone: source Manual", acc.phone_source, "Manual")
check("HR assigns phone: employee derived", acc.employee, EMP_A)
try:
	acc.phone = "0900000" + RUN[:3].translate(str.maketrans("abcdef", "123456"))
	acc.save(ignore_permissions=True)
	check("HR phone that matches nobody refused", "saved", "refused")
except frappe.ValidationError:
	check("HR phone that matches nobody refused", "refused", "refused")
	acc.reload()

with mock.patch.object(zalo_graph, "get_user_id", return_value=(zid_np, "Test")):
	r = call(api.login, access_token="at")
check("stored phone -> ACTIVE", (r["data"]["result"], r["data"]["employee"]["employee_id"]), ("ACTIVE", EMP_A))
tok_np = r["data"]["token"]
check("session login_method STORED_PHONE", frappe.db.get_value("TIQN Portal Session", {"token_hash": hash_token(tok_np)}, "login_method"), "STORED_PHONE")
check("me shows login_method", call(api.me, token=tok_np)["data"]["login_method"], "STORED_PHONE")

acc = frappe.get_doc("TIQN Portal Account", zid_np)
acc.phone = phone_of(EMP_B)
acc.save(ignore_permissions=True)
r = call(api.me, token=tok_np)
check("HR re-assigns phone -> old session ends", (code(r), r["error"]["details"].get("reason")), ("SESSION_INVALID", "PHONE_CHANGED"))

with mock.patch.object(zalo_graph, "get_user_id", return_value=(zid_np, "Test")), mock.patch.object(
	zalo_graph, "get_phone", return_value="84" + utils.phone_key(phone_of(EMP_A))
):
	r = call(api.login, access_token="at", phone_token="pt")
check("Zalo phone overrides HR phone", (r["data"]["employee"]["employee_id"], frappe.db.get_value("TIQN Portal Account", zid_np, "phone_source")), (EMP_A, "Zalo"))
check("session login_method ZALO_PHONE", frappe.db.get_value("TIQN Portal Session", {"token_hash": hash_token(r["data"]["token"])}, "login_method"), "ZALO_PHONE")


print("\n=== dev_login (simulator) ===")
zid_dev = f"unit-{RUN}-dev"
with mock.patch.dict(frappe.conf, {"employee_portal_dev_login": 0}):
	check("dev_login off -> FEATURE_DISABLED", code(call(api.dev_login, zalo_user_id=zid_dev)), "FEATURE_DISABLED")
	check("get_config.dev_login false", call(api.get_config)["data"]["dev_login"], False)
with mock.patch.dict(frappe.conf, {"employee_portal_dev_login": 1}):
	check("get_config.dev_login true", call(api.get_config)["data"]["dev_login"], True)
	r = call(api.dev_login, zalo_user_id=zid_dev)
	check("unknown id -> DEV_NOT_ALLOWED", (r["data"]["result"], r["data"]["token"]), ("DEV_NOT_ALLOWED", None))
	check("unknown id recorded for HR", frappe.db.exists("TIQN Portal Account", zid_dev) is not None, True)
	acc = frappe.get_doc("TIQN Portal Account", zid_dev)
	acc.phone = phone_of(EMP_A)
	acc.save(ignore_permissions=True)
	check("phone but not ticked -> still DEV_NOT_ALLOWED", call(api.dev_login, zalo_user_id=zid_dev)["data"]["result"], "DEV_NOT_ALLOWED")
	frappe.db.set_value("TIQN Portal Account", zid_dev, "allow_dev_login", 1)
	r = call(api.dev_login, zalo_user_id=zid_dev)
	check("ticked + phone -> ACTIVE", r["data"]["result"], "ACTIVE")
	tok_dev = r["data"]["token"]
	sess = frappe.db.get_value("TIQN Portal Session", {"token_hash": hash_token(tok_dev)}, ["login_method", "expires_on"], as_dict=True)
	check("dev session marked DEV", sess.login_method, "DEV")
	check("dev session lasts 1 day", sess.expires_on <= add_to_date(now_datetime(), days=1, minutes=1), True)
	check("dev session works", call(api.me, token=tok_dev)["ok"], True)
	check("dev_login cannot pick another account", call(api.dev_login, zalo_user_id=zid_np)["data"]["result"], "DEV_NOT_ALLOWED")
with mock.patch.dict(frappe.conf, {"employee_portal_dev_login": 0}):
	r = call(api.me, token=tok_dev)
	check("dev flag turned off -> dev session ends", code(r), "SESSION_INVALID")


# ---------------------------------------------------------------------------
print("\n=== sessions ===")
r = call(api.me, token=TOKEN_A)
check("me: ok", r["ok"], True)
check("me: employee", r["data"]["employee"]["employee_id"], EMP_A)
check("me: department suffix stripped", " - TIQN" in (r["data"]["employee"]["department"] or ""), False)
check("me without token", code(call(api.me)), "SESSION_REQUIRED")
check("me with garbage token", code(call(api.me, token="nope")), "SESSION_INVALID")
check("old client", code(call(api.me, token=TOKEN_A, version="0.9.0")), "CLIENT_TOO_OLD")
check("current client", call(api.me, token=TOKEN_A, version="1.0.0")["ok"], True)

tok_exp = auth_mod.complete_login(f"unit-{RUN}-e", phone_of(EMP_A))["token"]
frappe.db.set_value("TIQN Portal Session", {"token_hash": hash_token(tok_exp)}, "expires_on", add_to_date(now_datetime(), hours=-1))
r = call(api.me, token=tok_exp)
check("expired session", (code(r), r["error"]["details"].get("reason")), ("SESSION_INVALID", "EXPIRED"))

tok_out = auth_mod.complete_login(f"unit-{RUN}-o", phone_of(EMP_A))["token"]
check("logout ok", call(api.logout, token=tok_out)["ok"], True)
r = call(api.me, token=tok_out)
check("after logout", (code(r), r["error"]["details"].get("reason")), ("SESSION_INVALID", "REVOKED"))

tok_dis = auth_mod.complete_login(f"unit-{RUN}-x", phone_of(EMP_A))["token"]
acc = frappe.get_doc("TIQN Portal Account", f"unit-{RUN}-x")
acc.disabled = 1
acc.save(ignore_permissions=True)
r = call(api.me, token=tok_dis)
check("disabled after login revokes session", code(r), "SESSION_INVALID")

tok_ph = auth_mod.complete_login(f"unit-{RUN}-p", phone_of(EMP_B))["token"]
real_phone_b = phone_of(EMP_B)
frappe.db.set_value("Employee", EMP_B, "cell_number", "0911" + RUN[:6].translate(str.maketrans("abcdef", "123456")), update_modified=False)
r = call(api.me, token=tok_ph)
check("HR changed the phone", (code(r), r["error"]["details"].get("reason")), ("SESSION_INVALID", "PHONE_CHANGED"))
frappe.db.set_value("Employee", EMP_B, "cell_number", real_phone_b, update_modified=False)

r = call(api.set_oa_follow, token=TOKEN_A, action="DISMISSED")
check("set_oa_follow DISMISSED", r["data"], {"followed": False, "show_invite": False})
check("set_oa_follow bad action", code(call(api.set_oa_follow, token=TOKEN_A, action="x")), "VALIDATION")


# ---------------------------------------------------------------------------
print("\n=== config ===")
r = call(api.get_config)
check("get_config without token", r["ok"], True)
check("get_config features.payslip", r["data"]["features"]["payslip"], True)
check("get_config policy url absolute", r["data"]["legal"]["privacy_policy_url"].startswith("http"), True)


# ---------------------------------------------------------------------------
print("\n=== payslips ===")
components = frappe.get_all(
	"Salary Component", filters={"custom_portal_section": ["not in", ["", "Hidden"]]}, fields=["name", "salary_component_abbr"]
)
from customize_erpnext.employee_portal.seed_test_payslips import _fake_amounts


def make_payslip(emp, period, status="Published"):
	a = _fake_amounts(emp, period)
	doc = frappe.get_doc(
		{
			"doctype": "TIQN Payslip",
			"employee": emp,
			"employee_name": "UNIT",
			"period": period,
			"status": status,
			"published_on": now_datetime() if status == "Published" else None,
			"import_batch": f"UNIT-{RUN}",
			"details": [{"salary_component": c.name, "amount": a.get(str(c.salary_component_abbr), 0)} for c in components],
		}
	).insert(ignore_permissions=True)
	return doc, a


doc_a, amounts_a = make_payslip(EMP_A, "2030-03")
make_payslip(EMP_A, "2030-04", status="Draft")
make_payslip(EMP_B, "2030-05")

r = call(api.get_payslip_periods, token=TOKEN_A, year=2030)
periods = [i["period"] for i in r["data"]["items"]]
check("periods: only own Published", periods, ["2030-03"])
check("periods: no amounts anywhere", "net" in frappe.as_json(r["data"]) or "amount" in frappe.as_json(r["data"]), False)
check("periods: is_new before viewing", r["data"]["items"][0]["is_new"], True)

r = call(api.get_payslip, token=TOKEN_A, period="2030-03")
check("payslip: ok", r["ok"], True)
d = r["data"]
check("payslip: net_pay = component 9", d["net_pay"], round(amounts_a["9"]))
check("payslip: own employee", d["employee"]["employee_id"], EMP_A)
keys = [s["key"] for s in d["sections"]]
check("payslip: section order", keys, ["EARNINGS", "DEDUCTIONS", "OTHERS", "ADJUSTMENT", "ATTENDANCE"])
earn = d["sections"][0]
check("payslip: earnings total = component 5", earn["total"], round(amounts_a["5"]))
check("payslip: deductions sign", d["sections"][1]["sign"], -1)
check("payslip: deductions total = component 6", d["sections"][1]["total"], round(amounts_a["6"]))
allowance = next(l for l in earn["lines"] if l["code"] == "3.1")
check("payslip: 3.1 is a subtotal", allowance["is_total"], True)
check("payslip: 3.3 (0đ) hidden by default", any(c["code"] == "3.3" for c in allowance["children"]), False)
check("payslip: 3.2 under 3.1", any(c["code"] == "3.2" for c in allowance["children"]), True)
att = d["sections"][-1]
check("payslip: attendance unit DAY", next(l for l in att["lines"] if l["code"] == "1.2")["unit"], "DAY")
check("payslip: attendance total null", att["total"], None)
check("payslip: section-total line not repeated", any(l["code"] == "5" for l in earn["lines"]), False)
check("payslip: view logged", frappe.db.count("TIQN Payslip View Log", {"payslip": doc_a.name}), 1)
check("payslip: first_viewed_on set", bool(frappe.db.get_value("TIQN Payslip", doc_a.name, "first_viewed_on")), True)
r = call(api.get_payslip, token=TOKEN_A, period="2030-03", include_zero=1)
allowance = next(l for l in r["data"]["sections"][0]["lines"] if l["code"] == "3.1")
check("payslip: include_zero shows 3.3", any(c["code"] == "3.3" for c in allowance["children"]), True)

check("payslip of B with A's token -> NOT_FOUND", code(call(api.get_payslip, token=TOKEN_A, period="2030-05")), "NOT_FOUND")
check("Draft payslip -> NOT_FOUND", code(call(api.get_payslip, token=TOKEN_A, period="2030-04")), "NOT_FOUND")
check("bad period", code(call(api.get_payslip, token=TOKEN_A, period="2030-13")), "VALIDATION")
check("employee kwarg is ignored", call(api.get_payslip, token=TOKEN_A, period="2030-03", employee=EMP_B)["data"]["employee"]["employee_id"], EMP_A)

frappe.db.set_single_value("Employee Portal Settings", "feature_payslip", 0)
frappe.clear_document_cache("Employee Portal Settings", "Employee Portal Settings")
check("feature off -> FEATURE_DISABLED", code(call(api.get_payslip_periods, token=TOKEN_A)), "FEATURE_DISABLED")
frappe.db.set_single_value("Employee Portal Settings", "feature_payslip", 1)
frappe.clear_document_cache("Employee Portal Settings", "Employee Portal Settings")

pub = frappe.get_doc("TIQN Payslip", doc_a.name)
pub.details[0].amount = 1
try:
	pub.save(ignore_permissions=True)
	check("published payslip cannot be edited", "saved", "refused")
except frappe.ValidationError:
	check("published payslip cannot be edited", "refused", "refused")


# ---------------------------------------------------------------------------
print("\n=== upload / publish ===")
from openpyxl import Workbook

wb = Workbook()
ws = wb.active
comp_cols = [c.name for c in payslip_admin._components()]
ws.append(["Kỳ lương", "MSNV", "Họ tên", "dept", "custom_section", "custom_group"] + comp_cols)
good = _fake_amounts(EMP_A, "2030-07")
abbr_of = {c.name: str(c.abbr) for c in payslip_admin._components()}
ws.append(["07-2030", EMP_A, frappe.db.get_value("Employee", EMP_A, "employee_name"), "Office", "HR-GA", "IT"] + [good.get(abbr_of[c], 0) for c in comp_cols])
bad_formula = dict(_fake_amounts(EMP_B, "2030-07"))
bad_formula["9"] += 1000
ws.append(["07-2030", EMP_B, "Tên Sai", "Office", "HR-GA", "IT"] + [bad_formula.get(abbr_of[c], 0) for c in comp_cols])
ws.append(["07-2030", "TIQN-9999", "Ghost", "", "", ""] + [0] * len(comp_cols))
ws.append(["07-2030", EMP_A, "", "", "", ""] + ["abc"] + [0] * (len(comp_cols) - 1))
buf = io.BytesIO()
wb.save(buf)
f = frappe.get_doc({"doctype": "File", "file_name": f"unit-{RUN}.xlsx", "is_private": 1, "content": buf.getvalue()}).insert(
	ignore_permissions=True
)
data = payslip_admin.parse_upload(f.file_url)
rows = {(r["row"]): r for r in data["rows"]}
check("upload: 4 rows read", len(data["rows"]), 4)
check("upload: good row clean", (rows[2]["errors"], rows[2]["warnings"]), ([], []))
check("upload: formula warning on 9", any(w.startswith("9 =") for w in rows[3]["warnings"]), True)
check("upload: name mismatch warning", any("Tên Sai" in w for w in rows[3]["warnings"]), True)
check("upload: unknown employee error", bool(rows[4]["errors"]), True)
check("upload: duplicate + non-number errors", len(rows[5]["errors"]) >= 2, True)
check("upload: periods", data["periods"], ["2030-07"])
throws_import = None
try:
	payslip_admin.import_upload(f.file_url, confirm_warnings=1)
except frappe.ValidationError:
	throws_import = "refused"
check("import refused while errors remain", throws_import, "refused")

wb2 = Workbook()
ws2 = wb2.active
ws2.append(["Kỳ lương", "MSNV", "Họ tên"] + comp_cols)
ws2.append(["07-2030", EMP_A, ""] + [good.get(abbr_of[c], 0) for c in comp_cols])
ws2.append(["07-2030", EMP_B, ""] + [bad_formula.get(abbr_of[c], 0) for c in comp_cols])
buf2 = io.BytesIO()
wb2.save(buf2)
f2 = frappe.get_doc({"doctype": "File", "file_name": f"unit2-{RUN}.xlsx", "is_private": 1, "content": buf2.getvalue()}).insert(
	ignore_permissions=True
)
try:
	payslip_admin.import_upload(f2.file_url, confirm_warnings=0)
	check("import needs warning confirmation", "imported", "refused")
except frappe.ValidationError:
	check("import needs warning confirmation", "refused", "refused")
res = payslip_admin.import_upload(f2.file_url, confirm_warnings=1)
check("import: 2 drafts", res["rows"], 2)
check("import: upload file deleted", frappe.db.exists("File", {"file_url": f2.file_url}), None)
check("import: status Draft", frappe.db.get_value("TIQN Payslip", {"employee": EMP_A, "period": "2030-07"}, "status"), "Draft")
check("draft invisible in app", code(call(api.get_payslip, token=TOKEN_A, period="2030-07")), "NOT_FOUND")

res = payslip_admin.publish_period("2030-07")
check("publish: 2", res["published"], 2)
check("published visible in app", call(api.get_payslip, token=TOKEN_A, period="2030-07")["ok"], True)
n = call(api.get_notifications, token=TOKEN_A)
mine = [i for i in n["data"]["items"] if i["target"]["id"] == "2030-07"]
check("notification created", (len(mine), mine[0]["type"] if mine else None), (1, "PAYSLIP_PUBLISHED"))

b_note = frappe.get_all("TIQN Portal Notification", {"employee": EMP_B, "target_id": "2030-07"}, pluck="name")[0]
call(api.mark_notifications_read, token=TOKEN_A, ids=b_note)
check("A cannot mark B's notification read", frappe.db.get_value("TIQN Portal Notification", b_note, "is_read"), 0)
r = call(api.mark_notifications_read, token=TOKEN_A, ids=mine[0]["id"])
check("A marks own notification read", frappe.db.get_value("TIQN Portal Notification", mine[0]["id"], "is_read"), 1)

check("re-import over Published refused", bool(payslip_admin.parse_upload(f.file_url)["rows"][0]["errors"]), True)
res = payslip_admin.withdraw_period("2030-07")
check("withdraw: 2", res["withdrawn"], 2)
check("withdrawn invisible in app", code(call(api.get_payslip, token=TOKEN_A, period="2030-07")), "NOT_FOUND")
check("withdraw removes unread B notification", frappe.db.exists("TIQN Portal Notification", b_note), None)

# Template layout (15/10): Period | Period From | Period To | Employee | ... + components.
wb3 = Workbook()
ws3 = wb3.active
ws3.append(list(payslip_admin.TEMPLATE_IDENT) + comp_cols)
ws3.append(["2030-07", getdate("2030-06-26"), "2030-07-25", EMP_A, "", "Office", "HR-GA", "IT"] + [good.get(abbr_of[c], 0) for c in comp_cols])
ws3.append(["2030-08", "2030-07-20", "2030-08-25", EMP_B, "", "", "", ""] + [good.get(abbr_of[c], 0) for c in comp_cols])
ws3.append(["2030-08", "abc", None, EMP_A, "", "", "", ""] + [good.get(abbr_of[c], 0) for c in comp_cols])
buf3 = io.BytesIO()
wb3.save(buf3)
f3 = frappe.get_doc({"doctype": "File", "file_name": f"unit3-{RUN}.xlsx", "is_private": 1, "content": buf3.getvalue()}).insert(
	ignore_permissions=True
)
data3 = payslip_admin.parse_upload(f3.file_url)
check("template layout: no header errors", (data3["header_errors"], data3["missing_components"]), ([], []))
rows3 = {r["row"]: r for r in data3["rows"]}
check("template layout: matching Period From/To ok", (rows3[2]["errors"], rows3[2]["section"], rows3[2]["group"]), ([], "HR-GA", "IT"))
check("template layout: wrong Period From is an error", any("2030-07-20" in e for e in rows3[3]["errors"]), True)
check("template layout: unreadable Period From is an error", bool(rows3[4]["errors"]), True)
payslip_admin.discard_upload(f3.file_url)

# Re-importing a Withdrawn payslip keeps it Withdrawn (published once: view log + notification
# link to it), so "Delete Drafts" never tries to delete it; Publish takes it again.
wb4 = Workbook()
ws4 = wb4.active
ws4.append(list(payslip_admin.TEMPLATE_IDENT) + comp_cols)
ws4.append(["2030-07", None, None, EMP_A, "", "", "", ""] + [good.get(abbr_of[c], 0) for c in comp_cols])
buf4 = io.BytesIO()
wb4.save(buf4)
f4 = frappe.get_doc({"doctype": "File", "file_name": f"unit4-{RUN}.xlsx", "is_private": 1, "content": buf4.getvalue()}).insert(
	ignore_permissions=True
)
payslip_admin.import_upload(f4.file_url, confirm_warnings=1)
check("re-import withdrawn: stays Withdrawn", frappe.db.get_value("TIQN Payslip", {"employee": EMP_A, "period": "2030-07"}, "status"), "Withdrawn")
check("delete drafts skips re-imported withdrawn", payslip_admin.delete_draft_period("2030-07")["deleted"], 0)
check("publish takes re-imported withdrawn", payslip_admin.publish_period("2030-07")["published"], 2)


# ---------------------------------------------------------------------------
print("\n=== M2: home / attendance / leave (read) ===")
from customize_erpnext.employee_portal import attendance_data as ad
from customize_erpnext.employee_portal import documents

for f in ("attendance", "overtime", "leave_view", "explanation_create"):
	frappe.db.set_single_value("Employee Portal Settings", f"feature_{f}", 1)
frappe.clear_document_cache("Employee Portal Settings", "Employee Portal Settings")

r = call(api.get_home, token=TOKEN_A)
check("home: ok", r["ok"], True)
check("home: today card", bool(r["data"]["today"] and r["data"]["today"]["state"]), True)
check("home: annual leave", r["data"]["annual_leave"] is not None, True)
check("home: every contract key", sorted(r["data"]), sorted(["employee", "access", "today", "annual_leave", "attendance", "overtime", "latest_payslip", "notifications", "oa"]))

r = call(api.get_attendance_calendar, token=TOKEN_A, month="2026-09")
days = r["data"]["days"]
check("calendar: every day of the month", len(days), 30)
check("calendar: 02/09 is a holiday", days[1]["display"], "HOLIDAY")
check("calendar: holiday label translated", days[1]["label"], "Quốc khánh")
check("calendar: displays in the closed set", {d["display"] for d in days} <= {"PRESENT", "LATE_EARLY", "LEAVE", "HALF_LEAVE", "ABSENT", "HOLIDAY", "DAY_OFF", "NO_DATA", "TODAY", "FUTURE"}, True)
check("calendar: bad month", code(call(api.get_attendance_calendar, token=TOKEN_A, month="2026-13")), "VALIDATION")

r = call(api.get_attendance_day, token=TOKEN_A, date=add_days(today(), 3))
check("future day cannot be explained", r["data"]["explain_blocked"]["code"], "FUTURE_DATE")
r = call(api.get_attendance_day, token=TOKEN_A, date="2026-09-08")
check("day: punches carry direction", all(p["direction"] in ("IN", "OUT") for p in r["data"]["punches"]), True)
check("day: no approver -> blocked", r["data"]["explain_blocked"]["code"] if r["data"]["explain_blocked"] else None,
      None if frappe.db.get_value("Employee", EMP_A, "leave_approver") else "NO_APPROVER")

r = call(api.get_attendance_summary, token=TOKEN_A, period="2030-03")
# 2030-03 has a PUBLISHED payslip: totals still come from Attendance (D14 dropped 15/10).
check("summary: published period still from Attendance", (r["data"]["payable_days"]["source"], r["data"]["overtime"]["source"]), ("ERP", "ERP"))
check("summary: payable NOT taken from payslip", r["data"]["payable_days"]["value"] == amounts_a["1.2"], False)
check("summary: cutoff = 25th", r["data"]["cutoff_date"], "2030-03-25")
check("summary: adjust until day before pay day", r["data"]["adjust_until"], "2030-04-04")
check("summary: future period provisional", r["data"]["provisional"], True)
check("provisional until adjust_until (04/10)", ad.period_summary(EMP_A, "2026-09", today="2026-10-04")["provisional"], True)
check("closed after adjust_until", ad.period_summary(EMP_A, "2026-09", today="2026-10-05")["provisional"], False)
check("published fake payslip does not close the period", ad.period_summary(EMP_A, "2026-07", today="2026-07-30")["provisional"], True)
s_att = ad.period_summary(EMP_A, "2026-09")
att_ot = frappe.db.sql("""SELECT SUM(custom_final_overtime_duration) FROM tabAttendance WHERE employee=%s AND docstatus<2
	AND attendance_date BETWEEN '2026-08-26' AND '2026-09-25'""", EMP_A)[0][0]
check("summary OT = sum of Attendance in period", s_att["ot_hours"], round(flt(att_ot), 2))

# OT registrations: insert raw rows (no hooks - the OT hooks recalculate attendance).
ot = frappe.new_doc("Overtime Registration")
ot.update({"name": f"UNIT-OT-{RUN}", "request_date": "2030-03-10", "workflow_state": "Draft", "docstatus": 0})
ot.db_insert()
for i, (emp, begin, end) in enumerate(((EMP_A, "17:00:00", "19:30:00"), (EMP_B, "17:00:00", "18:00:00"))):
	row = frappe.new_doc("Overtime Registration Detail")
	row.update({"name": f"UNIT-OTD-{RUN}-{i}", "parent": ot.name, "parenttype": "Overtime Registration", "parentfield": "ot_employees",
	            "employee": emp, "date": "2030-03-10", "begin_time": begin, "end_time": end, "reason": "unit", "idx": i + 1})
	row.db_insert()
r = call(api.get_overtime, token=TOKEN_A, period="2030-03")
mine = [i for i in r["data"]["items"] if i["registration_id"] == ot.name]
expected_status = "REGISTERED" if ad.include_draft_ot() else "DRAFT"
check("OT: only own rows", len(mine), 1)
check("OT: draft status follows include_draft_ot", (mine[0]["status"], mine[0]["hours"], mine[0]["id"]), (expected_status, 2.5, ot.name))
check("OT: draft hours counted only when REGISTERED", r["data"]["registered_approved_hours"] >= 2.5, expected_status == "REGISTERED")

# OT merged into the calendar + day detail (contract 1.1.3).
r = call(api.get_attendance_day, token=TOKEN_A, date="2030-03-10")
regs = r["data"]["overtime_registrations"]
check("day: OT registrations of the day", [(x["id"], x["status"], x["begin"], x["end"], x["hours"]) for x in regs], [(ot.name, expected_status, "17:00", "19:30", 2.5)])
check("day: OT status label translated", regs[0]["status_label"], "Đã đăng ký" if expected_status == "REGISTERED" else "Bản nháp")
check("day: no attendance -> approved OT null", r["data"]["approved_overtime_hours"], None)
att_day = frappe.db.sql("""SELECT attendance_date, custom_final_overtime_duration f, custom_approved_overtime_duration a FROM tabAttendance
	WHERE employee=%s AND docstatus<2 AND custom_final_overtime_duration>0 ORDER BY attendance_date DESC LIMIT 1""", EMP_A, as_dict=True)
if att_day:
	dd = att_day[0]
	r = call(api.get_attendance_day, token=TOKEN_A, date=str(dd.attendance_date))
	check("day: approved OT from Attendance", r["data"]["approved_overtime_hours"], round(flt(dd.a), 2))
	month = str(dd.attendance_date)[:7]
	r = call(api.get_attendance_calendar, token=TOKEN_A, month=month)
	day = next(x for x in r["data"]["days"] if x["date"] == str(dd.attendance_date))
	check("calendar: day OT = final OT", day["overtime_hours"], round(flt(dd.f), 2))
	sums = frappe.db.sql("""SELECT SUM(custom_final_overtime_duration), SUM(custom_approved_overtime_duration) FROM tabAttendance
		WHERE employee=%s AND docstatus<2 AND attendance_date LIKE %s""", (EMP_A, month + "-%"))[0]
	check("calendar: OT summary = month sums", (r["data"]["overtime_summary"]["actual_hours"], r["data"]["overtime_summary"]["approved_hours"]),
	      (round(flt(sums[0]), 2), round(flt(sums[1]), 2)))
	check("calendar: no-OT day -> null", all(x["overtime_hours"] is None or x["overtime_hours"] > 0 for x in r["data"]["days"]), True)
frappe.db.set_single_value("Employee Portal Settings", "feature_overtime", 0)
frappe.clear_document_cache("Employee Portal Settings", "Employee Portal Settings")
r = call(api.get_attendance_calendar, token=TOKEN_A, month="2030-03")
check("overtime feature off: no OT in calendar", r["data"]["overtime_summary"], None)
check("overtime feature off: no OT registrations on day", call(api.get_attendance_day, token=TOKEN_A, date="2030-03-10")["data"]["overtime_registrations"], [])
frappe.db.set_single_value("Employee Portal Settings", "feature_overtime", 1)
frappe.clear_document_cache("Employee Portal Settings", "Employee Portal Settings")
frappe.db.set_value("Overtime Registration", ot.name, {"workflow_state": "Rejected", "docstatus": 1}, update_modified=False)
r = call(api.get_overtime, token=TOKEN_A, period="2030-03")
check("OT: rejected registration hidden", any(i["registration_id"] == ot.name for i in r["data"]["items"]), False)

r = call(api.get_leave_balances, token=TOKEN_A)
check("balances: annual present", r["data"]["annual"]["leave_type"] in ad.annual_leave_types(), True)
check("balances: available = remaining - pending", r["data"]["annual"]["available"], round(r["data"]["annual"]["remaining"] - r["data"]["annual"]["pending"], 2))
r = call(api.get_leave_applications, token=TOKEN_A, year=2026)
check("leave list: counts add up", r["data"]["counts"]["ALL"], sum(v for k, v in r["data"]["counts"].items() if k != "ALL"))
check("leave list: bad status", code(call(api.get_leave_applications, token=TOKEN_A, status="x")), "VALIDATION")

other_la = frappe.db.get_value("Leave Application", {"employee": ["!=", EMP_A]}, "name")
check("leave detail of someone else -> NOT_FOUND", code(call(api.get_leave_application, token=TOKEN_A, id=other_la)), "NOT_FOUND")
own_la = frappe.db.get_value("Leave Application", {"employee": EMP_A}, "name")
if own_la:
	check("leave detail of own", call(api.get_leave_application, token=TOKEN_A, id=own_la)["data"]["id"], own_la)

other_ar = frappe.db.get_value("Attendance Request", {"employee": ["!=", EMP_A]}, "name")
if other_ar:
	check("explanation of someone else -> NOT_FOUND", code(call(api.get_attendance_request, token=TOKEN_A, id=other_ar)), "NOT_FOUND")

print("\n=== signed document links ===")
if own_la:
	fdoc = frappe.get_doc({"doctype": "File", "file_name": f"unit-{RUN}.txt", "is_private": 1, "content": b"hello",
	                       "attached_to_doctype": "Leave Application", "attached_to_name": own_la}).insert(ignore_permissions=True)
	sig, _exp = documents.sign(fdoc.name, EMP_A)
	frappe.local.response = frappe._dict()
	api.download_document(sig=sig)
	content = frappe.local.response.get("filecontent")
	check("download: own file streams", content.decode() if isinstance(content, bytes) else content, "hello")
	refused = []
	for label, bad in (("tampered", sig[:-2] + ("AA" if not sig.endswith("AA") else "BB")),
	                   ("signed for B", documents.sign(fdoc.name, EMP_B)[0]),
	                   ("expired", documents.sign(fdoc.name, EMP_A, ttl=-5)[0])):
		try:
			api.download_document(sig=bad)
			refused.append((label, "served"))
		except frappe.PermissionError:
			refused.append((label, "refused"))
	check("download: tampered / other employee / expired refused", [x[1] for x in refused], ["refused"] * 3)


# ---------------------------------------------------------------------------
print("\n=== readiness report ===")
from customize_erpnext.employee_portal.report.portal_readiness.portal_readiness import execute as readiness

cols, rows_r, *_rest = readiness({"issue": "Shared Phone"})
check("readiness: shared-phone rows exist (2 known pairs)", len(rows_r) >= 2, True)


# ---------------------------------------------------------------------------
frappe.db.commit = _REAL_COMMIT
frappe.flags.in_test = False
_REAL_ROLLBACK()
left = frappe.db.count("TIQN Portal Account", {"name": ["like", f"unit-{RUN}%"]}) + frappe.db.count(
	"TIQN Payslip", {"import_batch": f"UNIT-{RUN}"}
)
check("rollback left no UNIT records", left, 0)
print(f"\n{ok} passed, {fail} failed")

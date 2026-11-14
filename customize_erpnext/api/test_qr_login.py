"""Tests for qr_login. Nothing is kept: every DB change is rolled back.

    bench --site erp.tiqn.local execute customize_erpnext.api.test_qr_login.run_all
"""

import frappe

from customize_erpnext.api import qr_login as q

USER = "tiqn-0057@tiqn.com.vn"


def _set_version(user, v):
	frappe.db.set_value("User", user, q.FIELD, v, update_modified=False)


def test_sign_verify_revoke():
	_set_version(USER, 0)
	assert q.verify_payload(f"{q.PREFIX}.{USER}.0.{q._sign(USER, 0)}") is None, "version 0 = off"

	_set_version(USER, 1)
	p1 = q.make_payload(USER)
	assert p1.startswith(f"QRL1.{USER}.1.") and len(p1.rsplit(".", 1)[1]) == q.SIG_LEN
	assert q.verify_payload(p1) == USER
	assert q.verify_payload("  " + p1 + "\n") == USER, "scanner whitespace"

	# tampering
	assert q.verify_payload(p1[:-1] + ("0" if p1[-1] != "0" else "1")) is None
	assert q.verify_payload(p1.replace(USER, "tiqn-0058@tiqn.com.vn")) is None
	assert q.verify_payload(p1.replace(".1.", ".2.")) is None
	assert q.verify_payload(USER) is None
	assert q.verify_payload("") is None and q.verify_payload(None) is None
	assert q.verify_payload("QRL1.x") is None

	# revoke -> old card dead, new card works
	_set_version(USER, 2)
	assert q.verify_payload(p1) is None
	assert q.verify_payload(q.make_payload(USER)) == USER


def test_disabled_and_blocked_users():
	_set_version(USER, 1)
	p = q.make_payload(USER)
	frappe.db.set_value("User", USER, "enabled", 0, update_modified=False)
	assert q.verify_payload(p) is None, "disabled user"
	frappe.db.set_value("User", USER, "enabled", 1, update_modified=False)

	_set_version("Administrator", 1)
	p_admin = f"{q.PREFIX}.Administrator.1.{q._sign('Administrator', 1)}"
	assert q.verify_payload(p_admin) is None, "Administrator never via QR"


def test_enable_revoke_disable_api():
	frappe.set_user("Administrator")
	_set_version(USER, 0)
	assert q.enable(USER) == 1
	assert q.enable(USER) == 1, "enable twice keeps the card"
	assert q.revoke(USER) == 2
	assert q.disable(USER) == 0
	try:
		q.enable("Administrator")
		raise AssertionError("Administrator must be refused")
	except frappe.ValidationError:
		pass


def test_safe_next():
	assert q.safe_next("/app/overtime-registration/new") == "/app/overtime-registration/new"
	assert q.safe_next("/app") == "/app"
	for bad in (None, "", "https://evil.test/app", "//evil.test", "/login", "/app\\..", "/x/app", 5):
		assert q.safe_next(bad) == "/app", bad


def test_card_context():
	frappe.set_user("Administrator")
	_set_version(USER, 1)
	ctx = q.get_card_context(USER)
	assert ctx["employee"] == "TIQN-0057" and ctx["version"] == 1
	assert ctx["qr_svg"].lstrip().startswith("<?xml") or "<svg" in ctx["qr_svg"]


def run_all():
	tests = [
		test_sign_verify_revoke,
		test_disabled_and_blocked_users,
		test_enable_revoke_disable_api,
		test_safe_next,
		test_card_context,
	]
	user = frappe.session.user
	try:
		for t in tests:
			t()
			print("PASS", t.__name__)
	finally:
		frappe.db.rollback()
		frappe.set_user(user)
	print(f"ALL {len(tests)} PASSED")

# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Vietnamese translations of customize_erpnext live in `customize_erpnext/locale/vi.po`.

That ONE file holds two layers, each entry tagged with an extracted comment:
  `#. source: tiqn`        — strings of this app (code, DocType JSON, fixtures, DB
                             labels of our customisations). Always win.
  `#. source: erpnext2vi`  — Vietnamese for frappe / erpnext / hrms / insights / lms /
                             payments from github.com/n8n2erpnext/erpnext2vi (public,
                             community). Pinned by commit: ERPNEXT2VI_SHA.
Load order (frappe/translate.py): each app's .csv then .mo, apps in install order
frappe → erpnext → hrms → insights → customize_erpnext → lms → payments; later wins.
So this .mo overrides the core apps' own Vietnamese (user decision 21/10/2026:
"ưu tiên erpnext2vi; vi.csv thắng cho text riêng của customize_erpnext").

🔴 RULES
- NEVER run `bench update-po-files --app customize_erpnext` or Poedit "Update from
  POT": they drop every msgid not in this app's code = all ~19k erpnext2vi entries.
  Add this app's new strings with `add_new_strings` below instead.
- After editing vi.po, compile: `bench compile-po-to-mo --app customize_erpnext`
  (`bench build` also does it). The .mo lives in sites/assets/locale (not in git).
- Do not put a `translations/vi.csv` back: in the same app the .csv loads BEFORE the
  .mo, so it would silently lose to erpnext2vi.

Commands (bench --site <site> execute customize_erpnext.scripts.vi_po.<fn>):
  build              rebuild vi.po: erpnext2vi@ERPNEXT2VI_SHA + tiqn layer
                     (first time from translations/vi.csv(.old); later from the
                     `source: tiqn` entries of vi.po). Writes a diff report.
  add_new_strings    add msgids of this app's code missing from vi.po (empty
                     msgstr, tagged tiqn). Never removes anything.
  check              placeholders, empty/duplicate entries, entry count.
"""

import csv
import json
import os
import re
import tempfile
import urllib.request
from collections import Counter

import frappe

APP = "customize_erpnext"
ERPNEXT2VI_REPO = "n8n2erpnext/erpnext2vi"
ERPNEXT2VI_SHA = "44c665f506e8875b33421967ce1e62d8cbbe3bd4"  # 2026-09-06
ERPNEXT2VI_APPS = ("frappe", "erpnext", "hrms", "insights", "lms", "payments")
TAG_TIQN, TAG_E2V = "source: tiqn", "source: erpnext2vi"
# Core strings where TIQN's meaning beats erpnext2vi (user choice 21/10/2026):
# "Section" is our custom_section (Bộ phận), not a form section; Relieving Date is the
# FIRST day off at TIQN; Submit/Submitted, Delivery Note/Purchase Receipt are house terms;
# "Signed On" is a signing date (Labor Contract, CRM Contract), not "logged in".
TIQN_KEEP = ("Section", "Relieving Date", "Submit", "Submitted", "Delivery Note", "Purchase Receipt", "Signed On")
PLACEHOLDER = re.compile(r"\{[^{}]*\}|%\([a-z_]+\)s|%[sd]")


# ----------------------------------------------------------------- helpers


def po_path():
	return frappe.get_app_path(APP, "locale", "vi.po")


def _key(msgid, context):
	return f"{msgid}:{context}" if context else msgid


def _read_po(path):
	from babel.messages.pofile import read_po

	with open(path, "rb") as f:
		return read_po(f)


def _app_strings(app):
	"""{(msgid, context)} of an app's code — the same extraction as `bench generate-pot-file`,
	in memory (nothing written)."""
	from babel.messages.extract import extract_from_dir

	from frappe.gettext.translate import (
		PYTHON_KEYWORDS,
		_get_ignored_strings,
		get_is_gitignored_function_for_app,
		get_method_map,
	)

	is_gitignored = get_is_gitignored_function_for_app(app)

	def directory_filter(d):
		if is_gitignored(str(d)):
			return False
		name = os.path.basename(d)
		return not (name.startswith(".") or name.startswith("_"))

	method_map = ([] if app == "frappe" else get_method_map(app)) + get_method_map("frappe")
	ignored = _get_ignored_strings(app)
	out = set()
	for _file, _line, message, _comments, context in extract_from_dir(
		frappe.get_pymodule_path(app, ".."), method_map, directory_filter=directory_filter, keywords=PYTHON_KEYWORDS
	):
		if message and isinstance(message, str) and (message, context) not in ignored:
			out.add((message, context))
	return out


def _db_strings():
	"""Labels, options and names that live only in the DB (custom fields, workspaces,
	sidebars…) plus record names of translated DocTypes (Country, Gender, UOM…)."""
	out = set()
	queries = [
		("select label from `tabCustom Field`", False),
		("select description from `tabCustom Field`", False),
		("select options from `tabCustom Field` where fieldtype = 'Select'", True),
		("select value from `tabProperty Setter` where property in ('label', 'description', 'options')", True),
		("select label from tabWorkspace", False),
		("select label from `tabWorkspace Link`", False),
		("select label from `tabWorkspace Shortcut`", False),
		("select label from `tabSidebar Item`", False),
		("select title from tabSidebar", False),
		("select label from `tabDesktop Icon`", False),
		("select label from `tabNumber Card`", False),
		("select chart_name from `tabDashboard Chart`", False),
		("select name from tabReport", False),
		("select title from tabPage", False),
		("select name from tabRole", False),
		("select name from `tabModule Def`", False),
	]
	for doctype in frappe.get_all("DocType", filters={"translated_doctype": 1}, pluck="name"):
		queries.append((f"select name from `tab{doctype}`", False))
	for sql, split in queries:
		try:
			rows = frappe.db.sql(sql)
		except Exception:
			continue
		for (value,) in rows:
			for part in (value or "").split("\n") if split else [value or ""]:
				if part.strip():
					out.add(part.strip())
	return out


def _csv_rows(path):
	"""[(msgid, context, msgstr)] in file order; later rows win like Frappe's loader."""
	rows = []
	with open(path, encoding="utf-8") as f:
		for r in csv.reader(f):
			if len(r) >= 2 and r[0] and r[1].strip():
				rows.append((r[0], (r[2].strip() or None) if len(r) >= 3 else None, r[1].strip()))
	return rows


def _erpnext2vi(source_dir=None):
	"""{key: (msgid, context, msgstr, app)} from the pinned erpnext2vi catalogs."""
	if not source_dir:
		source_dir = tempfile.mkdtemp(prefix="erpnext2vi-")
		for app in ERPNEXT2VI_APPS:
			url = f"https://raw.githubusercontent.com/{ERPNEXT2VI_REPO}/{ERPNEXT2VI_SHA}/{app}_vi_v2.po"
			urllib.request.urlretrieve(url, os.path.join(source_dir, f"{app}_vi_v2.po"))
	out = {}
	for app in ERPNEXT2VI_APPS:  # first app wins on a shared msgid (frappe > erpnext > …)
		path = os.path.join(source_dir, f"{app}_vi_v2.po")
		if not os.path.exists(path):
			continue
		for m in _read_po(path):
			if m.id and isinstance(m.id, str) and isinstance(m.string, str) and m.string.strip():
				out.setdefault(_key(m.id, m.context), (m.id, m.context, m.string, app))
	return out


def _tiqn_layer():
	"""{key: (msgid, context, msgstr)} — current vi.po `source: tiqn` entries, or the
	legacy translations/vi.csv (or vi.csv.old) the first time."""
	if os.path.exists(po_path()):
		return {
			_key(m.id, m.context): (m.id, m.context, m.string)
			for m in _read_po(po_path())
			if m.id and TAG_TIQN in (m.auto_comments or []) and isinstance(m.string, str)
		}
	for name in ("vi.csv", "vi.csv.old"):
		path = frappe.get_app_path(APP, "translations", name)
		if os.path.exists(path):
			return {_key(i, c): (i, c, s) for i, c, s in _csv_rows(path)}
	return {}


def _effective(app_dicts):
	"""What frappe.translate builds: apps in install order, .csv then .mo, later wins."""
	from frappe.gettext.translate import get_translations_from_mo
	from frappe.translate import get_translations_from_csv

	out = {}
	for app in frappe.get_installed_apps():
		if app in app_dicts:
			out.update(app_dicts[app])
		else:
			out.update(get_translations_from_csv("vi", app) or {})
			out.update(get_translations_from_mo("vi", app) or {})
	return out


# ----------------------------------------------------------------- commands


def build(source_dir=None, report_path=None, write=1):
	"""Merge erpnext2vi + the tiqn layer into locale/vi.po (write=0: report only)."""
	from babel.messages.catalog import Catalog
	from babel.messages.pofile import write_po

	e2v = _erpnext2vi(source_dir)
	tiqn = _tiqn_layer()
	own_code = {_key(i, c) for i, c in _app_strings(APP)}
	core = set()
	for app in frappe.get_installed_apps():
		if app != APP:
			core |= {_key(i, c) for i, c in _app_strings(app)}
	db = _db_strings()
	used = own_code | core | db
	# "Text riêng" = only this app (or only our DB customisations) uses it. A generic
	# string our code also uses ("Employee", "Status") is core text: erpnext2vi wins.
	own = (own_code | db) - core
	own |= set(TIQN_KEEP)

	entries = {}  # key -> (msgid, context, msgstr, tag)
	stats = Counter()
	for key, (msgid, ctx, s, _app) in e2v.items():
		entries[key] = (msgid, ctx, s, TAG_E2V)
		stats["erpnext2vi"] += 1
	for key, (msgid, ctx, s) in tiqn.items():
		if key in own:
			stats["tiqn: own text" + (" (over erpnext2vi)" if key in entries else "")] += 1
			entries[key] = (msgid, ctx, s, TAG_TIQN)
		elif key in entries:
			stats["tiqn dropped: erpnext2vi wins"] += 1
		elif key in used:
			stats["tiqn: fills a gap of erpnext2vi"] += 1
			entries[key] = (msgid, ctx, s, TAG_TIQN)
		else:
			stats["tiqn dropped: not used anywhere"] += 1

	catalog = Catalog(locale="vi", project=APP, fuzzy=False)
	catalog.language_team = "TIQN IT"
	for key in sorted(entries, key=lambda k: (entries[k][3] != TAG_TIQN, k.lower())):
		msgid, ctx, s, tag = entries[key]
		catalog.add(msgid, s, context=ctx, auto_comments=[tag])

	after_app = {key: v[2] for key, v in entries.items()}
	before = _effective({})
	after = _effective({APP: after_app})
	changed = {k: (before[k], after[k]) for k in after if k in before and before[k] != after[k]}
	added = {k: after[k] for k in after if k not in before}
	lost_all = {k: before[k] for k in before if k not in after}
	lost = {k: v for k, v in lost_all.items() if k in used}  # would really show English
	unused_removed = len(lost_all) - len(lost)
	report = {
		"erpnext2vi_sha": ERPNEXT2VI_SHA,
		"entries": len(entries),
		"stats": dict(stats),
		"screen": {
			"changed": len(changed),
			"english_to_vi": len(added),
			"vi_to_english": len(lost),
			"unused_keys_removed": unused_removed,
		},
		"changed": changed,
		"added": added,
		"lost": lost,
	}
	report_path = report_path or os.path.join(tempfile.gettempdir(), "vi_po_build_report.json")
	with open(report_path, "w", encoding="utf-8") as f:
		json.dump(report, f, ensure_ascii=False, indent=1)

	if int(write):
		os.makedirs(os.path.dirname(po_path()), exist_ok=True)
		with open(po_path(), "wb") as f:
			write_po(f, catalog, width=0, sort_output=False, include_previous=False)
	print(json.dumps({k: v for k, v in report.items() if k in ("entries", "stats", "screen")}, ensure_ascii=False, indent=1))
	print("report:", report_path, "| vi.po written:", bool(int(write)))
	return report_path


def add_new_strings():
	"""Add this app's msgids missing from vi.po (empty msgstr, tagged tiqn). Removes nothing."""
	from babel.messages.pofile import write_po

	catalog = _read_po(po_path())
	have = {_key(m.id, m.context) for m in catalog if m.id}
	new = sorted((i, c) for i, c in _app_strings(APP) if _key(i, c) not in have)
	for msgid, ctx in new:
		catalog.add(msgid, "", context=ctx, auto_comments=[TAG_TIQN])
	with open(po_path(), "wb") as f:
		write_po(f, catalog, width=0, sort_output=False, include_previous=False)
	untranslated = sum(1 for m in catalog if m.id and not m.string)
	print(f"added {len(new)} new string(s); untranslated in vi.po: {untranslated}")
	return [i for i, _c in new]


def check(min_entries=15000):
	"""Placeholders kept, no duplicate keys, entry count did not collapse."""
	catalog = _read_po(po_path())
	msgs = [m for m in catalog if m.id]
	bad = [m.id for m in msgs if m.string and sorted(PLACEHOLDER.findall(m.id)) != sorted(PLACEHOLDER.findall(m.string))]
	tags = Counter(next((c for c in (m.auto_comments or []) if c.startswith("source:")), "untagged") for m in msgs)
	ok = len(msgs) >= int(min_entries)
	print(f"entries {len(msgs)} {'OK' if ok else '❌ below ' + str(min_entries)} | {dict(tags)} | placeholder mismatches {len(bad)}")
	for msgid in bad[:20]:
		print("  placeholder:", msgid[:90])
	return {"entries": len(msgs), "ok": ok, "placeholder_mismatches": bad}

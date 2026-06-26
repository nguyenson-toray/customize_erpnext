"""
Import Vietnamese administrative units (provinces / wards) into the site DB.

Source: https://github.com/thanglequoc/vietnamese-provinces-database (2-tier,
post-2025 merge: province -> ward, no district). The repo is kept up to date
with each government decree, so re-running this command refreshes the data.

Tables created (plain MySQL tables in the site DB, NOT Frappe DocTypes):
    administrative_regions, administrative_units, provinces, wards

Usage (admin / CLI):
    bench --site <site> execute \
        customize_erpnext.api.vn_address.import_vn_units.import_vn_units
"""

import os
import subprocess
import tempfile

import frappe
import requests
from frappe import _

RAW_BASE = (
    "https://raw.githubusercontent.com/thanglequoc/"
    "vietnamese-provinces-database/master/mysql"
)
CREATE_URL = f"{RAW_BASE}/mysql_CreateTables_vn_units.sql"
IMPORT_URL = f"{RAW_BASE}/mysql_ImportData_vn_units.sql"

_TABLES = ("wards", "provinces", "administrative_units", "administrative_regions")


def _fetch(url):
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.text


def _build_sql():
    """Download both SQL files and wrap them into one idempotent script."""
    create_sql = _fetch(CREATE_URL)
    import_sql = _fetch(IMPORT_URL)

    # Drop first (FK checks off) so the command can be re-run to refresh data.
    drop_stmt = "DROP TABLE IF EXISTS " + ", ".join(_TABLES) + ";"

    return "\n".join(
        [
            "SET FOREIGN_KEY_CHECKS=0;",
            "SET NAMES utf8mb4;",
            drop_stmt,
            create_sql,
            import_sql,
            "SET FOREIGN_KEY_CHECKS=1;",
        ]
    )


def _run_sql_script(sql_text):
    """Pipe the SQL script into the site DB via the mariadb/mysql CLI.

    Using the CLI (rather than splitting statements by hand) keeps multi-row
    INSERTs and UTF-8 escaping intact.
    """
    conf = frappe.conf
    db_name = conf.db_name
    db_user = conf.db_user or conf.db_name
    db_password = conf.db_password
    db_host = conf.db_host or "127.0.0.1"
    db_port = str(conf.db_port or 3306)

    client = "mariadb" if _which("mariadb") else "mysql"
    cmd = [
        client,
        "-h", db_host,
        "-P", db_port,
        "-u", db_user,
        "--default-character-set=utf8mb4",
        db_name,
    ]

    env = dict(os.environ)
    if db_password:
        env["MYSQL_PWD"] = db_password  # avoids password on the command line

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sql", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(sql_text)
            tmp_path = fh.name

        with open(tmp_path, "rb") as stdin:
            result = subprocess.run(
                cmd,
                stdin=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
        if result.returncode != 0:
            frappe.throw(
                _("VN address import failed: {0}").format(
                    result.stderr.decode("utf-8", "replace")[:2000]
                )
            )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _which(binary):
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(path, binary)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


@frappe.whitelist()
def import_vn_units():
    """Download the latest dataset from GitHub and (re)load it into the DB.

    Whitelisted for System Manager so it can also be triggered from the desk;
    runs unrestricted from `bench execute` (Administrator).
    """
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Manager can import address data"), frappe.PermissionError)

    sql_text = _build_sql()
    _run_sql_script(sql_text)

    counts = {
        t: frappe.db.sql(f"SELECT COUNT(*) FROM `{t}`")[0][0] for t in _TABLES
    }
    frappe.clear_cache()
    msg = _("Imported VN address data: {0} provinces, {1} wards").format(
        counts.get("provinces"), counts.get("wards")
    )
    frappe.msgprint(msg)
    return {"status": "success", "counts": counts, "message": msg}

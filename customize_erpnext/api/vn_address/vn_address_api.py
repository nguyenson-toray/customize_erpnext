"""
Vietnamese address API (2-tier: Province -> Ward) backed by the imported
`provinces` / `wards` tables (see import_vn_units.py).

All endpoints are guest-accessible because the self-update web page is served
to employees without an ERP login. They are read-only lookups.
"""

import frappe
from frappe import _

_CACHE_PROVINCES = "vn_address_provinces"
_CACHE_WARDS = "vn_address_wards"  # per-province, suffixed with the code


def _tables_ready():
    return bool(
        frappe.db.sql(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = 'provinces' LIMIT 1"
        )
    )


@frappe.whitelist(allow_guest=True)
def get_provinces():
    """Return all provinces ordered by name: [{code, name}] (name = full_name)."""
    cached = frappe.cache().get_value(_CACHE_PROVINCES)
    if cached:
        return cached

    if not _tables_ready():
        frappe.throw(_("Address data not imported yet. Run import_vn_units."))

    rows = frappe.db.sql(
        "SELECT code, full_name AS name FROM provinces ORDER BY name",
        as_dict=True,
    )
    frappe.cache().set_value(_CACHE_PROVINCES, rows, expires_in_sec=86400)
    return rows


@frappe.whitelist(allow_guest=True)
def get_wards(province_code):
    """Return wards of a province ordered by name: [{code, name}]."""
    if not province_code:
        return []

    cache_key = f"{_CACHE_WARDS}:{province_code}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    rows = frappe.db.sql(
        "SELECT code, full_name AS name FROM wards "
        "WHERE province_code = %s ORDER BY name",
        (province_code,),
        as_dict=True,
    )
    frappe.cache().set_value(cache_key, rows, expires_in_sec=86400)
    return rows


@frappe.whitelist(allow_guest=True)
def search_ward(ward_name, province_name=""):
    """Best-effort lookup of a ward by (accent-insensitive) name.

    Returns {province: {code, name}, ward: {code, name}} or None. Useful for
    QR-CCCD auto-fill; not required by the basic cascade UI.
    """
    if not ward_name:
        return None

    conditions = "w.full_name LIKE %(w)s OR w.name LIKE %(w)s"
    params = {"w": f"%{ward_name.strip()}%"}
    if province_name:
        conditions = f"({conditions}) AND (p.full_name LIKE %(p)s OR p.name LIKE %(p)s)"
        params["p"] = f"%{province_name.strip()}%"

    rows = frappe.db.sql(
        f"""
        SELECT w.code AS ward_code, w.full_name AS ward_name,
               p.code AS province_code, p.full_name AS province_name
        FROM wards w
        JOIN provinces p ON p.code = w.province_code
        WHERE {conditions}
        LIMIT 1
        """,
        params,
        as_dict=True,
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "province": {"code": r.province_code, "name": r.province_name},
        "ward": {"code": r.ward_code, "name": r.ward_name},
    }


# ===========================================================================
# HƯỚNG DẪN TEST API TỪ TRÌNH DUYỆT
# ---------------------------------------------------------------------------
# Các endpoint dưới đây là `allow_guest=True` (không cần đăng nhập). Cách nhanh
# nhất để kiểm tra là gõ thẳng URL vào thanh địa chỉ trình duyệt — trình duyệt
# gửi GET, không cần CSRF token cho method guest read-only.
#
#   1) Lấy danh sách tỉnh/thành (34 tỉnh):
#      https://<site>/api/method/customize_erpnext.api.vn_address.vn_address_api.get_provinces
#
#   2) Lấy phường/xã của 1 tỉnh (truyền province_code qua query string):
#      .../get_wards?province_code=01            (01 = Thành phố Hà Nội)
#      .../get_wards?province_code=79            (79 = TP. Hồ Chí Minh)
#
#   3) Tra cứu phường/xã theo tên (dùng cho QR CCCD):
#      .../search_ward?ward_name=Ba Đình
#      .../search_ward?ward_name=Long Xuyên&province_name=An Giang
#
# Kết quả trả về dạng JSON, bọc trong khoá "message", ví dụ:
#      {"message":[{"code":"01","name":"Thành phố Hà Nội"}, ...]}
#
# Test bằng JS Console (F12) trên trang đã đăng nhập của site:
#      frappe.call("customize_erpnext.api.vn_address.vn_address_api.get_wards",
#                  {province_code: "01"}).then(r => console.log(r.message));
#
# Test bằng curl (guest, qua HTTPS cổng 8888):
#      curl -k "https://<site>:8888/api/method/customize_erpnext.api.vn_address.\
#              vn_address_api.get_provinces"
#
# ===========================================================================
# KHI TÁC GIẢ GITHUB CẬP NHẬT DỮ LIỆU (nghị định mới → đổi tỉnh/xã)
# ---------------------------------------------------------------------------
# Repo nguồn (cập nhật theo từng nghị định của Chính phủ):
#   https://github.com/thanglequoc/vietnamese-provinces-database  (thư mục mysql/)
#
# Toàn bộ dữ liệu được tải TRỰC TIẾP từ GitHub mỗi lần chạy lệnh import, nên
# KHÔNG cần sửa code. Chỉ cần chạy lại lệnh import để nạp bản mới nhất:
#
#      bench --site <site> execute \
#        customize_erpnext.api.vn_address.import_vn_units.import_vn_units
#
# Lệnh này tự động:
#   - Tải mysql_CreateTables_vn_units.sql + mysql_ImportData_vn_units.sql từ GitHub
#   - DROP + tạo lại 4 bảng: administrative_regions, administrative_units,
#     provinces, wards (idempotent — chạy lại bao nhiêu lần cũng được)
#   - Nạp dữ liệu mới và xoá cache (frappe.clear_cache) → API trả ngay dữ liệu mới
#
# Sau khi chạy, kiểm tra số liệu in ra (vd "34 provinces, 3321 wards").
#
# LƯU Ý nếu cấu trúc bảng thay đổi (tác giả thêm/đổi cột, hoặc quay lại 3 cấp
# Tỉnh→Huyện→Xã): khi đó cần cập nhật câu SELECT trong file này (get_provinces /
# get_wards) cho khớp tên cột mới. Hiện tại đang dùng cột: provinces(code,
# full_name) và wards(code, full_name, province_code). Kiểm tra nhanh cấu trúc:
#      bench --site <site> mariadb -e "DESCRIBE provinces; DESCRIBE wards;"
# ===========================================================================

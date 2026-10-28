"""
Employee Self Update Info API

A dynamic, field-picker driven self-service page. HR chooses any Employee field
(including custom fields) in `Employee Self Update Info Setting`; employees review
the current value of each field and update what changed. Submissions are stored as
JSON on `Employee Self Update Info` and exported to Excel — they are NOT synced back
to the Employee record.

Public (allow_guest=True):
    get_field_config        -> field list built from settings + Employee meta
    get_eligible_employees  -> employees configured in the setting
    get_form_data           -> current Employee values overlaid with any draft
    save_form_data          -> store submitted values as JSON

HR (login required):
    download_excel          -> xlsx with old (Employee) vs new (submitted) columns
"""

# Mặt tiền (27/10/2026): code đã tách nguyên văn theo mảng việc vào các module cùng thư mục —
#   rules    hằng số + luật dùng chung (khoá data_json, kiểu field, bảng con)
#   config   Setting → config field (trang www / Desk / phiếu), Info for Sign config
#   values   chuẩn hoá, kiểm tra, định dạng giá trị; bảng con; hồ sơ nộp kèm
#   access   quyền vào trang www (danh sách NV, mã, khoá, token tải phiếu)
#   receipt  phiếu PDF / PNG (phiếu NV + phiếu HR luôn 1 trang)
#   export   Excel All Info + Info for Sign (Excel / PDF gộp / PDF tách)
#   portal   API trang www (guest)
#   desk     form Desk: xem / sửa phiếu, Tình trạng hồ sơ, Generate PDF
#   sync     Review + Sync vào Employee
# Phụ thuộc 1 chiều theo đúng thứ tự trên (module dưới import module trên, không ngược lại).
# Mọi đường dẫn whitelist `customize_erpnext.api.self_update_info.self_update_info_api.<hàm>` (trang www,
# Desk JS, controller) và mọi tên test dùng (`api.<tên>`) vẫn giữ nguyên nhờ re-export bên dưới.
# ⚠ Thay tạm (monkeypatch) 1 hàm: phải gán vào MỌI module đang giữ tên đó (xem _set trong test), gán
#   vào mặt tiền thôi thì code trong module khác vẫn gọi hàm cũ.

# Tên file gốc từng import ở đầu file (test dùng api.CCCD_ISSUE_FIELD…).
from customize_erpnext.api.employee.cccd_expiry import DOB_FIELD as CCCD_DOB_FIELD  # noqa: F401
from customize_erpnext.api.employee.cccd_expiry import EXPIRY_FIELD as CCCD_EXPIRY_FIELD  # noqa: F401
from customize_erpnext.api.employee.cccd_expiry import ISSUE_FIELD as CCCD_ISSUE_FIELD  # noqa: F401
from customize_erpnext.api.employee.cccd_expiry import cccd_expiry_iso  # noqa: F401

from .rules import (  # noqa: F401
	SETTING_DT,
	INFO_DT,
	REMARKS_KEY,
	DOCUMENTS_KEY,
	_SIGNATURE_PREFIX,
	_SIGNATURE_MAX_LEN,
	COMMITMENT_TEXT,
	_ALLOWED_FIELDTYPES,
	_LINK_AS_SELECT,
	_FIELD_DEPENDS,
	_ALLOWED_TABLES,
	_TABLE_REQUIRED_IF,
	_TABLE_MAX_ROWS,
	_TABLE_COLUMN_TYPES,
)
from .config import (  # noqa: F401
	_option_labels,
	_get_setting,
	_commitment_html,
	_selected_rows,
	_build_config,
	_layout_width,
	_table_columns,
	_table_required_if,
	_is_table,
	_employee_scalar_fields,
	_validation_meta,
	_config_fieldnames,
	_setting_documents,
	_info_for_sign_wanted,
	_info_for_sign_config,
	_address_pairs,
)
from .values import (  # noqa: F401
	_dep_parent_value,
	_apply_depends,
	_column_required,
	_column_hidden,
	_employee_table_rows,
	_employee_tables,
	_is_blank,
	_fill_from_employee,
	_table_list,
	_table_rows_equal,
	_table_text,
	_value_text,
	_clean_table_value,
	_VALIDATION_PATTERNS,
	_NORMALIZE_TYPES,
	_WORD_DIGIT,
	_EMAIL_LIKE,
	_SENTENCE_START,
	_normalize_text,
	_validate_value,
	_apply_cccd_expiry,
	_portal_address_errors,
	_documents_snapshot,
	_clean_documents,
	_document_status,
	_status_text_vi,
	_fmt_date_vn,
	_fmt,
	_EMERGENCY_FIELDS,
	_CCCD_FIELDS,
	_LICENSE_FIELDS,
	_UNIFORM_FIELDS,
	_SIGN_GROUPS,
	_sign_join,
	_sign_value_vi,
)
from .access import (  # noqa: F401
	_require_hr,
	_eligible_ids,
	_dob_day,
	_num_eq,
	_code_ok,
	_is_hr,
	_ensure_eligible,
	_gate,
	_already_submitted,
	_unlock_ok,
	_is_locked,
	_gate_edit,
	_dl_secret,
	_dl_windows,
	_make_download_token,
	_download_token_ok,
	_receipt_download_allowed,
	_gate_receipt,
)
from .receipt import (  # noqa: F401
	HR_RECEIPT_ZOOM_STEPS,
	_hr_receipt_pdf,
	_HR_HEADER_LINES,
	_HR_HEADER_COL_WIDTHS,
	HR_RECEIPT_SIDE_MARGIN,
	HR_RECEIPT_TB_MARGIN,
	_hr_receipt_html,
	_document_checklist_html,
	_receipt_base,
	_html_to_png,
	_logo_data_uri,
	_strip_section_no,
	_table_html,
	_build_submission_html,
	_receipt_value,
	_receipt_row,
	_receipt_rows,
	_receipt_id_lines,
	_receipt_sign_block,
	_receipt_page,
)
from .export import (  # noqa: F401
	download_excel,
	get_info_for_sign_fields,
	_sign_labels,
	_sign_items,
	INFO_FOR_SIGN_HEADER,
	INFO_FOR_SIGN_TITLE,
	_info_for_sign_people,
	INFO_FOR_SIGN_PDF_FIRST,
	INFO_FOR_SIGN_PDF_PER_PAGE,
	_SIGN_PDF_FALLBACK,
	_SIGN_PDF_MIN_FONT,
	_SIGN_PDF_MAX_FONT,
	_SIGN_PDF_COL_WIDTHS,
	_SIGN_PDF_SAMPLE_PAGES,
	INFO_FOR_SIGN_PDF_MAX_RECORDS,
	_info_for_sign_pdf_pages,
	_info_for_sign_pdf_html,
	_download_info_for_sign_pdf,
	_download_info_for_sign_pdf_split,
	_download_info_for_sign,
)
from .portal import (  # noqa: F401
	_submit_device_info,
	get_field_config,
	verify_employee,
	get_access_info,
	unlock_access,
	get_eligible_employees,
	get_form_data,
	save_form_data,
	download_submission_pdf,
	download_submission_image,
	_load_submission_receipt,
)
from .desk import (  # noqa: F401
	download_pdf_for_hr,
	apply_document_status,
	_TEXT_EDITABLE_TYPES,
	_MULTILINE_TYPES,
	_hr_editor,
	_PORTAL_ONLY_FIELDS,
	validate_desk_edit,
	get_submission_view,
)
from .sync import (  # noqa: F401
	_ADDRESS_GROUPS,
	_coerce_for_employee,
	_row_key,
	_sync_table_rows,
	_rows_with_names,
	_rebuild_address_full,
	review_forms,
	get_syncable_fields,
	sync_to_employee,
)

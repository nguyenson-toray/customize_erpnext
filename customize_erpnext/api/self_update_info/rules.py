"""Hằng số + luật dùng chung (khoá data_json, kiểu field, bảng con, cam kết mặc định).

Tách nguyên văn từ self_update_info_api.py (27/10/2026) — mặt tiền đó re-export mọi tên."""




SETTING_DT = "Employee Self Update Info Setting"


INFO_DT = "Employee Self Update Info"


# Reserved key inside data_json for the employee's free-text remarks.
REMARKS_KEY = "__remarks"


# Hồ sơ nộp kèm (user 27/10/2026): bản chụp danh sách Setting → Document Checklist lúc lưu phiếu,
# [{document, required, checked}] — Setting đổi sau thì phiếu cũ vẫn đúng như lúc nộp. Không Sync.
DOCUMENTS_KEY = "__documents"


# Chữ ký vẽ trên trang www: PNG data URL; canvas ~600x200 nét đen thường < 30 KB.
_SIGNATURE_PREFIX = "data:image/png;base64,"


_SIGNATURE_MAX_LEN = 400_000


# Câu cam kết mặc định — HR sửa ở Setting.commitment_text; để trống thì dùng câu này.
COMMITMENT_TEXT = (
	"Tôi cam kết các thông tin đã khai ở trên là đúng sự thật và chịu trách nhiệm "
	"về thông tin đã cung cấp."
)


# Fieldtypes the dynamic renderer knows how to handle (v1: flat + Link + Text).
_ALLOWED_FIELDTYPES = {
	"Data", "Date", "Datetime", "Time", "Int", "Float", "Currency",
	"Select", "Check", "Small Text", "Text", "Long Text", "Link", "Phone",
	# 4 field Tỉnh/Xã của Employee là Autocomplete (api/vn_address_search). Thiếu dòng này
	# thì _build_config bỏ qua chúng im lặng → trang mất ô địa chỉ. Trang render theo widget
	# Address Province/Ward nên không cần biết fieldtype.
	"Autocomplete",
}


# Field Link trỏ tới danh mục nhỏ → trang www hiện như Select (dropdown) thay vì ô gõ chữ tự do.
# Giá trị = các bản ghi được chọn (theo thứ tự); bản ghi không tồn tại bị bỏ. Gender có 7 bản ghi
# chuẩn của Frappe nhưng Employee chỉ dùng Male/Female (user 16/10/2026).
_LINK_AS_SELECT = {
	"Gender": ("Male", "Female"),
}


# Field chỉ hiện (và khi hiện thì BẮT BUỘC) khi field khác có giá trị trong danh sách; ẩn → xoá trắng
# (trang www, save_form_data, validate_desk_edit). Chỉ áp khi field điều kiện cũng có trong Setting.
# Desk Employee dùng depends_on của chính Custom Field.
_FIELD_DEPENDS = {
	"custom_driving_license_status": ("custom_driving_license", ("Chưa",)),
}


# Bảng con của Employee cho NV khai (16/10/2026) — CHỈ allow-list: `internal_work_history` do override
# Transfer/Promotion dựng lại, `custom_fingerprints` là dữ liệu máy chấm công → không mở.
# Giá trị = cột mặc định (fieldname, nhãn, bắt buộc) khi ô "Table Columns" của dòng Setting để trống.
_ALLOWED_TABLES = {
	"education": (
		("level", "Trình độ", 1),   # đầu tiên: quyết định Trường/Ngành/Năm có ẩn / bắt buộc không
		("school_univ", "Trường", 0),
		("maj_opt_subj", "Ngành học", 0),
		("year_of_passing", "Năm tốt nghiệp", 0),
	),
	"external_work_history": (
		("company_name", "Công ty", 1),
		("designation", "Chức vụ", 0),
		("total_experience", "Tổng thời gian làm (năm)", 0),
	),
}


# Cột phụ thuộc giá trị 1 cột khác của cùng dòng (user 16/10/2026), Học vấn:
# - Trung cấp trở lên (`values`): hiện `columns` (Trường, Ngành, Năm TN); bắt buộc `required` (Trường, Ngành —
#   Năm tốt nghiệp KHÔNG bắt buộc);
# - đã chọn trình độ khác (THCS / THPT): `columns` ẨN và bị xoá trắng; chưa chọn: vẫn hiện, không bắt buộc.
# Trang www + Desk + server cùng đọc field["required_if"] (chỉ giữ cột có trong cấu hình).
_TABLE_REQUIRED_IF = {
	"education": {
		"column": "level",
		"values": ("Trung cấp", "Cao đẳng", "Đại học", "Sau đại học"),
		"columns": ("school_univ", "maj_opt_subj", "year_of_passing"),
		"required": ("school_univ", "maj_opt_subj"),
	},
}


_TABLE_MAX_ROWS = 3


_TABLE_COLUMN_TYPES = {"Data", "Small Text", "Text", "Int", "Float", "Select", "Date"}

// Tỉnh/Xã cho field Autocomplete: tìm không dấu, đủ 168 xã, chỉ nhận giá trị trong danh sách.
//
// CHƯA được nạp ở đâu (không có trong hooks.py). Plan + cách nối vào employee.js:
// customize_erpnext/api/vn_address_search/README.md
//
// Vì sao phải có file này — đọc từ frappe/public/js/frappe/form/controls/autocomplete.js:
//   - list chỉ đọc df.options lúc make_input → nạp lại phải gọi control.set_data()
//   - filter mặc định FILTER_CONTAINS phân biệt dấu: "ba to" không ra "Ba Tơ"
//   - maxItems mặc định 99, tỉnh nhiều xã nhất có 168
//   - rời ô là lưu nguyên chữ đã gõ, không bắt chọn trong list

frappe.provide("customize_erpnext.vn_address");

(function () {
	const API = "customize_erpnext.api.vn_address_search.vn_address_search_api";
	const MAX_ITEMS = 200;

	// NFD không tách "đ" thành "d" + dấu, nên phải thay riêng.
	function deburr(s) {
		return String(s || "")
			.normalize("NFD")
			.replace(/[̀-ͯ]/g, "")
			.replace(/đ/g, "d")
			.replace(/Đ/g, "D")
			.toLowerCase();
	}

	let provinces_promise = null;
	const wards_cache = {};

	function load_provinces() {
		if (!provinces_promise) {
			provinces_promise = frappe
				.xcall(`${API}.get_province_options`)
				.catch((e) => {
					provinces_promise = null;
					throw e;
				});
		}
		return provinces_promise;
	}

	function load_wards(province) {
		if (!province) return Promise.resolve([]);
		if (!wards_cache[province]) {
			wards_cache[province] = frappe
				.xcall(`${API}.get_ward_options`, { province })
				.catch((e) => {
					delete wards_cache[province];
					throw e;
				});
		}
		return wards_cache[province];
	}

	// Gắn filter bỏ dấu + nâng maxItems. Gọi lại bao nhiêu lần cũng được.
	function enhance_control(control) {
		if (!control || !control.awesomplete || control._vn_address_ready) return;
		control.awesomplete.maxItems = MAX_ITEMS;
		control.awesomplete.filter = function (item, input) {
			const needle = deburr(input).trim();
			return !needle || deburr(item.label).includes(needle);
		};
		control._vn_address_ready = true;
	}

	// Thay cho frm.set_df_property(fieldname, "options", ...) — cách đó không làm mới
	// list của Autocomplete đã dựng.
	function set_options(frm, fieldname, options) {
		const control = frm.fields_dict[fieldname];
		if (!control) return;
		control.df.options = options || [];
		if (control.awesomplete) {
			enhance_control(control);
			control.set_data(options || []);
		}
	}

	// true nếu giá trị hiện tại rỗng hoặc có trong list đang nạp (so khớp chính xác, có dấu).
	// List chưa nạp / rỗng → không phán xử (tránh xoá nhầm lúc API chậm); server validate chặn sau.
	function is_valid_choice(frm, fieldname) {
		const value = frm.doc[fieldname];
		if (!value) return true;
		const control = frm.fields_dict[fieldname];
		const data = (control && control.get_data && control.get_data()) || [];
		if (!data.length) return true;
		return data.some((d) => d.value === value);
	}

	// Gọi trong event change: giá trị không có trong list → xoá + báo. Trả về false nếu đã xoá.
	function enforce_choice(frm, fieldname) {
		if (is_valid_choice(frm, fieldname)) return true;
		frm.set_value(fieldname, "");
		frappe.show_alert({
			message: __("Please select a value from the list"),
			indicator: "orange",
		});
		return false;
	}

	Object.assign(customize_erpnext.vn_address, {
		deburr,
		load_provinces,
		load_wards,
		enhance_control,
		set_options,
		is_valid_choice,
		enforce_choice,
	});
})();

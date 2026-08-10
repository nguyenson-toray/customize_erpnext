# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Nạp giá trị hiện hành cho `TIQN Payroll Settings`.

Idempotent: chỉ thêm dòng còn thiếu, KHÔNG ghi đè số HR đã sửa. Chạy lại nhiều lần
được — cần thiết vì `bench migrate` có thể chạy lại patch sau khi HR đã chỉnh.

Nguồn số liệu: `overrides/payroll_docs/PLAN_PAYROLL_SETTINGS.md` mục 3.1 và
`QUY_CHE_LUONG_2025.md`. Mọi con số ở đây đều đã đối chiếu với 9 phiếu lương thật.

⚠ Patch này KHÔNG bật `enable_pit_auto` / `enable_insurance_auto` — hai cờ đó phải do
người dùng bật thủ công sau khi đã kiểm tra dữ liệu (cùng tinh thần với RULE #1 về email:
không tự ý kích hoạt thứ ảnh hưởng ra ngoài).
"""

import frappe

SETTINGS = "TIQN Payroll Settings"

# Giảm trừ gia cảnh — from_date, bản thân, mỗi NPT, căn cứ
DEDUCTION_RATES = [
	("2020-07-01", 11_000_000, 4_400_000, "Nghị quyết 954/2020/UBTVQH14"),
	("2026-01-01", 15_500_000, 6_200_000, "Nghị quyết 110/2025 — từ kỳ tính thuế 2026"),
]

# Biểu thuế luỹ tiến từng phần theo THÁNG (Luật Thuế TNCN).
# bracket, income_from, income_to (0 = không giới hạn), rate %, số trừ nhanh
TAX_BRACKETS_2026 = [
	(1, 0, 5_000_000, 5, 0),
	(2, 5_000_000, 10_000_000, 10, 250_000),
	(3, 10_000_000, 18_000_000, 15, 750_000),
	(4, 18_000_000, 32_000_000, 20, 1_650_000),
	(5, 32_000_000, 52_000_000, 25, 3_250_000),
	(6, 52_000_000, 80_000_000, 30, 5_850_000),
	(7, 80_000_000, 0, 35, 9_850_000),
]

# Tỷ lệ bảo hiểm — from_date, BHXH, BHYT, BHTN (phần NLĐ), phần công ty hoàn khi thử việc
INSURANCE_RATES = [
	("2022-01-01", 8.0, 1.5, 1.0, 21.5),
]

PROBATION_TYPES = [
	"30 Days Probationary Contract",
	"60 Days Probationary Contract",
]


def execute():
	doc = frappe.get_single(SETTINGS)

	added = []
	added += _seed_deduction_rates(doc)
	added += _seed_tax_brackets(doc)
	added += _seed_insurance_rates(doc)
	added += _seed_probation_types(doc)

	if not added:
		print("TIQN Payroll Settings: đã đủ dữ liệu, không thêm gì.")
		return

	# ignore_permissions vì patch chạy dưới Administrator trong ngữ cảnh migrate
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	for line in added:
		print("  +", line)


def _seed_deduction_rates(doc) -> list:
	existing = {str(r.from_date) for r in doc.deduction_rates or []}
	out = []
	for from_date, personal, dependent, basis in DEDUCTION_RATES:
		if from_date in existing:
			continue
		doc.append("deduction_rates", {
			"from_date": from_date,
			"personal_deduction": personal,
			"dependent_deduction": dependent,
			"legal_basis": basis,
		})
		out.append(f"Giảm trừ {from_date}: {personal:,} / {dependent:,}")
	return out


def _seed_tax_brackets(doc) -> list:
	if doc.tax_brackets:
		return []
	for bracket, income_from, income_to, rate, quick in TAX_BRACKETS_2026:
		doc.append("tax_brackets", {
			"from_date": "2020-07-01",
			"bracket": bracket,
			"income_from": income_from,
			"income_to": income_to,
			"rate_percent": rate,
			"quick_deduction": quick,
		})
	return [f"Biểu thuế 7 bậc (hiệu lực 2020-07-01)"]


def _seed_insurance_rates(doc) -> list:
	existing = {str(r.from_date) for r in doc.insurance_rates or []}
	out = []
	for from_date, si, hi, ui, refund in INSURANCE_RATES:
		if from_date in existing:
			continue
		doc.append("insurance_rates", {
			"from_date": from_date,
			"si_percent": si,
			"hi_percent": hi,
			"ui_percent": ui,
			"employer_refund_percent": refund,
		})
		out.append(f"Tỷ lệ BH {from_date}: {si}/{hi}/{ui}, hoàn {refund}%")
	return out


def _seed_probation_types(doc) -> list:
	existing = {r.employment_type for r in doc.probation_employment_types or []}
	out = []
	for et in PROBATION_TYPES:
		if et in existing:
			continue
		if not frappe.db.exists("Employment Type", et):
			# Không throw: Employment Type do module Labor Contract tạo, có thể chưa có
			print(f"  ! bỏ qua Employment Type chưa tồn tại: {et}")
			continue
		doc.append("probation_employment_types", {"employment_type": et})
		out.append(f"Loại HĐ thử việc: {et}")
	return out

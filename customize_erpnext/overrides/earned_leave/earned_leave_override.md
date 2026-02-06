# Earned Leave Override

**Last Updated:** 2026-02-05

## Mục đích

1. Hỗ trợ tất cả `allocate_on_day` options: First Day, Last Day, Date of Joining, 15th of Month
2. Kiểm tra điều kiện đủ probation trước khi phân bổ phép
3. **Seniority bonus:** +1 ngày/5 năm thâm niên (Điều 114 BLLĐ 2019)
4. Phân bổ theo bonus months strategy: 1 ngày/tháng + extra tháng 6 và 12

## Quy định pháp luật (Điều 114 BLLĐ 2019)

| Thâm niên | Bonus | Tổng phép (base 14) |
|-----------|-------|---------------------|
| < 5 năm | 0 | 14 ngày |
| 5-9 năm | +1 | 15 ngày |
| 10-14 năm | +2 | 16 ngày |
| 15-19 năm | +3 | 17 ngày |

## Quy định công ty (TIQN)

| Hạng mục | Giá trị |
|----------|---------|
| Phép năm base | **14 ngày** (từ Leave Type.max_leaves_allowed) |
| Seniority | **+1 ngày/5 năm** |
| Ngày phân bổ | Configurable (First Day, Last Day, DOJ, 15th) |
| Tháng bonus | **Tháng 6 và 12** |
| Điều kiện | Sau thử việc (probation) |
| Không đủ điều kiện | **Bỏ qua, KHÔNG cộng dồn** |

### Bảng phân bổ theo tháng

| Annual | Jan-May | Jun | Jul-Nov | Dec | Total |
|--------|---------|-----|---------|-----|-------|
| 14 | 1×5=5 | 2 | 1×5=5 | 2 | 14 |
| 15 | 1×5=5 | 2 | 1×5=5 | 3 | 15 |
| 16 | 1×5=5 | 3 | 1×5=5 | 3 | 16 |

## Logic kiểm tra đủ điều kiện (Eligibility)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ELIGIBILITY CHECK                                │
├─────────────────────────────────────────────────────────────────────┤
│  (1) Priority: Employee.custom_number_of_probation_days              │
│      └── Nếu có giá trị (> 0) → eligibility_date = DOJ + probation  │
│                                                                      │
│  (2) Fallback: Leave Type.applicable_after                           │
│      └── Nếu (1) null → eligibility_date = DOJ + applicable_after   │
│                                                                      │
│  (3) Không restriction: eligibility_date = DOJ                       │
│                                                                      │
│  ⚠️ Nếu không đủ điều kiện → BỎ QUA, KHÔNG CỘNG DỒN                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Ví dụ

### Employee với seniority bonus

```
Employee A:
- DOJ: 01/03/2020
- LPA created: 15/02/2026
- Seniority: 6 năm → bonus = +1
- Annual: 14 + 1 = 15 ngày

Schedule:
┌─────┬────────────┬────────┬─────────────────────────────┐
│  #  │    Date    │ Leaves │            Note             │
├─────┼────────────┼────────┼─────────────────────────────┤
│ 1   │ 15/02/2026 │ 2      │ Initial: Jan(1) + Feb(1)    │
│ 2   │ 15/03/2026 │ 1      │ Future - Scheduler          │
│ 3   │ 15/04/2026 │ 1      │                             │
│ 4   │ 15/05/2026 │ 1      │                             │
│ 5   │ 15/06/2026 │ 2      │ Bonus month                 │
│ 6   │ 15/07/2026 │ 1      │                             │
│ 7   │ 15/08/2026 │ 1      │                             │
│ 8   │ 15/09/2026 │ 1      │                             │
│ 9   │ 15/10/2026 │ 1      │                             │
│ 10  │ 15/11/2026 │ 1      │                             │
│ 11  │ 15/12/2026 │ 3      │ Bonus + seniority extra     │
├─────┼────────────┼────────┼─────────────────────────────┤
│     │   TOTAL    │ 15     │ ✓                           │
└─────┴────────────┴────────┴─────────────────────────────┘
```

### Employee mới (probation)

```
Employee B:
- DOJ: 06/01/2026
- Probation: 30 days → Eligibility: 05/02/2026
- Seniority: < 5 năm → bonus = 0
- Annual: 14 ngày

Schedule:
┌──────────────┬────────┬────────────────────────────────┐
│ Ngày phân bổ │ Số ngày│ Ghi chú                        │
├──────────────┼────────┼────────────────────────────────┤
│ 15/01/2026   │ SKIP   │ ❌ Chưa đủ điều kiện           │
│ 15/02/2026   │ 1      │ ✓                              │
│ ...          │ 1      │ ✓                              │
│ 15/06/2026   │ 2      │ ✓ Bonus month                  │
│ ...          │ 1      │ ✓                              │
│ 15/12/2026   │ 2      │ ✓ Bonus month                  │
├──────────────┼────────┼────────────────────────────────┤
│ TỔNG         │ 13     │ Mất 1 ngày (tháng 1)           │
└──────────────┴────────┴────────────────────────────────┘
```

## File Structure

```
customize_erpnext/overrides/earned_leave/
├── __init__.py                    # Monkey patches
├── earned_leave.py                # Main override functions
├── earned_leave_config.py         # Config + seniority + allocation dates
├── earned_leave_eligibility.py    # Eligibility check functions
└── earned_leave_override.md       # Documentation (this file)
```

## Config (earned_leave_config.py)

```python
# Seniority (Vietnamese Labor Law)
ENABLE_SENIORITY_BONUS = True
SENIORITY_YEARS_PER_BONUS = 5  # Every 5 years = +1 day

# Allocation strategy
BASE_ANNUAL_ALLOCATION = 14
BONUS_MONTHS = [6, 12]  # June and December

# Functions
calculate_seniority_bonus(doj, reference_date)
get_annual_allocation_with_seniority(base, doj, reference_date)
get_monthly_allocation_for_month(month, annual_allocation)
get_allocation_date_for_month(date, allocate_on_day, doj)
```

## Cấu hình Leave Type

```
Leave Type: Annual Leave
├── is_earned_leave: ✓
├── earned_leave_frequency: Monthly
├── allocate_on_day: [First Day | Last Day | Date of Joining | 15th of Month]
├── max_leaves_allowed: 14
└── applicable_after: 30
```

## Lưu ý quan trọng

1. **Seniority:** Tính từ DOJ đến ngày tạo LPA
2. **Không cộng dồn:** Không đủ điều kiện → skip, không cộng tháng sau
3. **Bonus months:** Extra days từ seniority đi vào Dec trước, rồi Jun
4. **All options:** Hỗ trợ First Day, Last Day, Date of Joining, 15th of Month
5. **Scheduler:** Chạy hourly, check eligibility trước khi allocate

-- Performance indexes for Daily Timesheet bulk operations
-- Run these indexes to improve query performance

-- Index for Employee Checkin lookup (used in generate_additional_info_html)
-- Covers: WHERE employee = X AND DATE(time) = Y ORDER BY time
CREATE INDEX IF NOT EXISTS idx_emp_checkin_emp_time
ON `tabEmployee Checkin` (employee, time);

-- Index for Maternity Tracking lookup
-- Covers: WHERE parent = X AND type IN (...) AND from_date <= Y AND to_date >= Y
CREATE INDEX IF NOT EXISTS idx_maternity_tracking_lookup
ON `tabMaternity Tracking` (parent, type, from_date, to_date);

-- Index for Shift Registration Detail lookup
-- Covers: WHERE employee = X AND begin_date <= Y AND end_date >= Y
CREATE INDEX IF NOT EXISTS idx_shift_reg_detail_lookup
ON `tabShift Registration Detail` (employee, begin_date, end_date);

-- Index for Overtime Registration Detail lookup
-- Covers: WHERE employee = X AND date = Y
CREATE INDEX IF NOT EXISTS idx_overtime_reg_detail_lookup
ON `tabOvertime Registration Detail` (employee, date);

-- Show indexes created
SHOW INDEX FROM `tabEmployee Checkin` WHERE Key_name LIKE 'idx_emp%';
SHOW INDEX FROM `tabMaternity Tracking` WHERE Key_name LIKE 'idx_mat%';
SHOW INDEX FROM `tabShift Registration Detail` WHERE Key_name LIKE 'idx_shift%';
SHOW INDEX FROM `tabOvertime Registration Detail` WHERE Key_name LIKE 'idx_over%';

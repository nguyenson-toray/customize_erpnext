-- Quick check if performance indexes exist
-- Run: bench --site [your-site] mariadb < customize_erpnext/overrides/shift_type/check_indexes.sql

SELECT
    '===========================================' AS line1,
    'PERFORMANCE INDEXES CHECK' AS title,
    '===========================================' AS line2;

-- Count indexes per table
SELECT
    'Employee Checkin' AS table_name,
    COUNT(*) AS indexes_found,
    CASE
        WHEN COUNT(*) >= 2 THEN '✅ OK'
        ELSE '❌ MISSING - Run add_performance_indexes.sql'
    END AS status
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'tabEmployee Checkin'
  AND index_name LIKE 'idx_emp_checkin%'

UNION ALL

SELECT
    'Attendance',
    COUNT(*),
    CASE
        WHEN COUNT(*) >= 3 THEN '✅ OK'
        ELSE '❌ MISSING - Run add_performance_indexes.sql'
    END
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'tabAttendance'
  AND index_name LIKE 'idx_attendance%'

UNION ALL

SELECT
    'Shift Assignment',
    COUNT(*),
    CASE
        WHEN COUNT(*) >= 1 THEN '✅ OK'
        ELSE '❌ MISSING - Run add_performance_indexes.sql'
    END
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'tabShift Assignment'
  AND index_name LIKE 'idx_shift_assign%'

UNION ALL

SELECT
    'Maternity Tracking ⭐',
    COUNT(*),
    CASE
        WHEN COUNT(*) >= 1 THEN '✅ OK - CRITICAL INDEX EXISTS'
        ELSE '❌ MISSING - CRITICAL! Run add_performance_indexes.sql NOW'
    END
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'tabMaternity Tracking'
  AND index_name LIKE 'idx_maternity%'

UNION ALL

SELECT
    'Employee',
    COUNT(*),
    CASE
        WHEN COUNT(*) >= 2 THEN '✅ OK'
        ELSE '❌ MISSING - Run add_performance_indexes.sql'
    END
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'tabEmployee'
  AND index_name LIKE 'idx_employee%'

UNION ALL

SELECT
    'Shift Type',
    COUNT(*),
    CASE
        WHEN COUNT(*) >= 1 THEN '✅ OK'
        ELSE '❌ MISSING - Run add_performance_indexes.sql'
    END
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'tabShift Type'
  AND index_name LIKE 'idx_shift_type%';

SELECT
    '===========================================' AS line1,
    'If any shows ❌ MISSING, run:' AS instruction,
    'bench --site [site] mariadb < add_performance_indexes.sql' AS command,
    '===========================================' AS line2;

import 'dart:math';

import 'package:attandance_client/functions/myFunctions.dart';
import 'package:attandance_client/model/attLog.dart';
import 'package:attandance_client/model/employee.dart';
import 'package:attandance_client/model/otRegister.dart';
import 'package:attandance_client/model/shiftRegister.dart';
import 'package:attandance_client/model/timeSheetDate.dart';
import 'package:attandance_client/main.dart';
import 'package:syncfusion_flutter_xlsio/xlsio.dart' as xl;
import 'package:intl/intl.dart';
import 'package:oktoast/oktoast.dart';

// ── Internal types ────────────────────────────────────────────────────────────

class _ShiftParam {
  final int beginHour, beginMin, endHour, endMin, restHour;
  const _ShiftParam(
    this.beginHour,
    this.beginMin,
    this.endHour,
    this.endMin,
    this.restHour,
  );
}

class _OtResult {
  final double otActual, otApproved, otFinal;
  const _OtResult(this.otActual, this.otApproved, this.otFinal);
}

// ── Public result wrapper ─────────────────────────────────────────────────────

class TimesheetResult {
  final List<TimeSheetDate> data;
  final List<String> anomalies;
  const TimesheetResult(this.data, this.anomalies);
}

// ── TimesheetFunctions ────────────────────────────────────────────────────────

class TimesheetFunctions {
  // ── Shift defaults (fallback when DB has no records) ─────────────────────
  static const _defaultShiftParams = <String, _ShiftParam>{
    'Day': _ShiftParam(8, 0, 17, 0, 1),
    'Shift 1': _ShiftParam(6, 0, 14, 0, 0),
    'Shift 2': _ShiftParam(14, 0, 22, 0, 0),
    'Canteen': _ShiftParam(7, 0, 16, 0, 1),
  };

  /// Find shift param from DB by exact name + date.
  /// Falls back to hardcoded defaults if no matching DB record.
  static _ShiftParam _getShiftParam(String shiftName, DateTime date) {
    final match = App.gValue.shiftParams.where(
      (s) =>
          s.name == shiftName &&
          !date.isBefore(s.effectiveFrom) &&
          !date.isAfter(s.effectiveTo),
    );
    if (match.isNotEmpty) {
      final s = match.first;
      return _ShiftParam(
        s.beginHour,
        s.beginMin,
        s.endHour,
        s.endMin,
        s.restHour,
      );
    }
    return _defaultShiftParams[shiftName] ?? _defaultShiftParams['Day']!;
  }

  /// For group-based shifts (e.g. Canteen), find the effective shift name
  /// by searching DB for any entry whose name contains [keyword] and covers [date].
  /// Returns the matching shift name, or [keyword] as fallback.
  static String _resolveGroupShift(String keyword, DateTime date) {
    final match = App.gValue.shiftParams.where(
      (s) =>
          s.name.contains(keyword) &&
          !date.isBefore(s.effectiveFrom) &&
          !date.isAfter(s.effectiveTo),
    );
    return match.isNotEmpty ? match.first.name : keyword;
  }

  /// Floor OT hours to nearest block.
  /// Returns 0 if total minutes < minOtMinute.
  static double _floorToBlock(double hours) {
    final minOtMin = App.gValue.timesheetSettings.minOtMinute;
    final otBlock = App.gValue.timesheetSettings.otBlockMinute;
    final totalMin = (hours * 60).floor();
    if (totalMin < minOtMin) return 0;
    final blockedMin = (totalMin ~/ otBlock) * otBlock;
    return blockedMin / 60;
  }

  /// Floor working hours to nearest working block.
  static double _floorWorkingToBlock(double hours) {
    final workBlock = App.gValue.timesheetSettings.workingBlockMinute;
    if (workBlock <= 1) return hours;
    final totalMin = (hours * 60).floor();
    final blockedMin = (totalMin ~/ workBlock) * workBlock;
    return blockedMin / 60;
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  static String _dayKey(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  static bool _sameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;

  /// Treat the sentinel value 2099-12-31 (DB default = "not set") as null.
  static DateTime? _matDate(DateTime? d) =>
      (d == null || d.year >= 2099) ? null : d.toBeginDay();

  static String _note(String existing, String addition) {
    if (addition.isEmpty) return existing;
    return existing.isEmpty ? addition : '$existing ; $addition';
  }

  static DateTime? _parseShiftTime(DateTime date, String hhmm) {
    final parts = hhmm.split(':');
    if (parts.length < 2) return null;
    final h = int.tryParse(parts[0]);
    final m = int.tryParse(parts[1]);
    if (h == null || m == null) return null;
    return DateTime.utc(date.year, date.month, date.day, h, m);
  }

  // ── Main entry point ─────────────────────────────────────────────────────────

  /// Compute [TimeSheetDate] records for every (employee × date) in [dateRange].
  static TimesheetResult createTimesheets({
    required List<Employee> employees,
    required List<AttLog> attLogs,
    required List<ShiftRegister> shiftRegisters,
    required List<OtRegister> otRegisters,
    required List<DateTime> dateRange,
  }) {
    final result = <TimeSheetDate>[];
    final anomalies = <String>[];
    if (employees.isEmpty || attLogs.isEmpty)
      return TimesheetResult(result, anomalies);

    // ── Pre-index data for O(1) lookups ────────────────────────────────────
    // AttLogs → Map<dayKey, Map<empId, List<AttLog>>>
    final logIndex = <String, Map<String, List<AttLog>>>{};
    final datesWithLogs = <String>{};
    for (final l in attLogs) {
      final dk = _dayKey(l.timestamp);
      datesWithLogs.add(dk);
      (logIndex[dk] ??= {}).putIfAbsent(l.empId, () => []).add(l);
    }
    // remove employees have workStatus = 'reSigned' and resignOn.year = 2099
    employees.removeWhere(
      (e) =>
          (e.workStatus ?? '').contains('Resigned') &&
          (e.resignOn == null || e.resignOn!.year >= 2099),
    );
    // remove excluded employee IDs from settings
    final excludeIds = App.gValue.timesheetSettings.excludeEmpIds;
    if (excludeIds.isNotEmpty) {
      employees.removeWhere((e) => excludeIds.contains(e.empId));
    }

    // ShiftRegisters → Map<dayKey, Map<shiftName, Set<empId>>>
    final shiftIndex = <String, Map<String, Set<String>>>{};
    for (final sr in shiftRegisters) {
      for (
        var d = sr.fromDate.toBeginDay();
        !d.isAfter(sr.toDate.toBeginDay());
        d = d.add(const Duration(days: 1))
      ) {
        final dk = _dayKey(d);
        (shiftIndex[dk] ??= {}).putIfAbsent(sr.shift, () => {}).add(sr.empId);
      }
    }

    // OtRegisters → Map<dayKey, Map<empId, List<OtRegister>>>
    final otIndex = <String, Map<String, List<OtRegister>>>{};
    for (final o in otRegisters) {
      final dk = _dayKey(o.otDate);
      (otIndex[dk] ??= {}).putIfAbsent(o.empId, () => []).add(o);
    }

    // Enumerate every date in [dateRange[0], dateRange[1]]
    final dates = <DateTime>[];
    for (
      var d = dateRange[0].toBeginDay();
      !d.isAfter(dateRange[1].toBeginDay());
      d = d.add(const Duration(days: 1))
    ) {
      dates.add(d);
    }

    for (final date in dates) {
      final dk = _dayKey(date);
      final dayLogMap = logIndex[dk];
      if (dayLogMap == null || dayLogMap.isEmpty) continue;

      // Shift assignments for this date (O(1) lookup)
      final shiftDay = shiftIndex[dk];
      final shift1Ids = shiftDay?['Shift 1'] ?? const {};
      final shift2Ids = shiftDay?['Shift 2'] ?? const {};

      // OT records for this date (O(1) lookup)
      final otByEmp = otIndex[dk] ?? const <String, List<OtRegister>>{};
      final empIdOT = otByEmp.keys.toSet();

      for (final emp in employees) {
        // Guard: date before joining date
        if (emp.joiningDate != null &&
            date.isBefore(emp.joiningDate!.toBeginDay()))
          continue;

        final empLogs = dayLogMap[emp.empId] ?? [];

        // Guard: resigned and absent → skip
        if (empLogs.isEmpty &&
            (emp.workStatus ?? '').contains('Resigned') &&
            emp.resignOn != null &&
            !date.isBefore(emp.resignOn!.toBeginDay()))
          continue;

        // ── Determine shift ─────────────────────────────────────────────────
        String shift = 'Day';
        if ((emp.group ?? '') == 'Canteen')
          shift = _resolveGroupShift('Canteen', date);
        if (shift1Ids.contains(emp.empId)) shift = 'Shift 1';
        if (shift2Ids.contains(emp.empId)) shift = 'Shift 2';
        if (date.weekday == DateTime.sunday)
          shift = 'Day'; // Sunday always Day base

        final p = _getShiftParam(shift, date);
        var shiftBegin = DateTime.utc(
          date.year,
          date.month,
          date.day,
          p.beginHour,
          p.beginMin,
        );
        var shiftEnd = DateTime.utc(
          date.year,
          date.month,
          date.day,
          p.endHour,
          p.endMin,
        );

        // Sunday → override shift window from OT register if employee has one
        // Use same record selection as OT dedup: highest id wins
        if (date.weekday == DateTime.sunday) {
          final sunOt = otByEmp[emp.empId] ?? [];
          if (sunOt.isNotEmpty) {
            final sunRec = sunOt.reduce((a, b) => a.id >= b.id ? a : b);
            shiftBegin =
                _parseShiftTime(date, sunRec.otTimeBegin) ?? shiftBegin;
            shiftEnd = _parseShiftTime(date, sunRec.otTimeEnd) ?? shiftEnd;
          }
        }

        // Rest window: always 12:00-13:00 on Sunday (regardless of OT register time);
        // on weekdays: 4h after shift start with shift's restHour.
        final restBegin = date.weekday == DateTime.sunday
            ? DateTime.utc(date.year, date.month, date.day, 12, 0)
            : shiftBegin.add(const Duration(hours: 4));
        final restEnd = date.weekday == DateTime.sunday
            ? DateTime.utc(date.year, date.month, date.day, 13, 0)
            : restBegin.add(Duration(hours: p.restHour));

        // ── Per-employee variables ──────────────────────────────────────────
        double normalHrs = 0, otActual = 0, otApproved = 0, otFinal = 0;
        String noteCheckin = '', noteSunday = '';
        DateTime? firstIn, lastOut;

        // Regime detection — date-based only.
        // The timesheet date determines which regime applies, not the current workStatus.
        // This ensures correctness regardless of current employment status (active/resigned).
        // Prerequisite: maternity date fields must be filled correctly in the DB.
        //   Pregnant regime  : maternityBegin ≤ date < maternityLeaveBegin
        //   Young child regime: maternityLeaveEnd ≤ date ≤ maternityEnd
        final mBegin = _matDate(emp.maternityBegin);
        final mLeaveBegin = _matDate(emp.maternityLeaveBegin);
        final mLeaveEnd = _matDate(emp.maternityLeaveEnd);
        final mEnd = _matDate(emp.maternityEnd);

        // Pregnant: mBegin ≤ date < (mLeaveBegin ?? mEnd)
        // If maternityLeaveBegin is not set, the employee is still working while
        // pregnant → use maternityEnd as the upper bound.
        final pregnantUpperBound = mLeaveBegin ?? mEnd;

        // Determine regime FIRST so isYoungChild is correct for shiftEnd & afternoon calc
        final bool isPregnant =
            mBegin != null &&
            pregnantUpperBound != null &&
            !date.isBefore(mBegin) &&
            date.isBefore(pregnantUpperBound);
        final bool isYoungChild =
            !isPregnant &&
            mLeaveEnd != null &&
            mEnd != null &&
            !date.isBefore(mLeaveEnd) &&
            !date.isAfter(mEnd);

        if (isYoungChild || isPregnant) {
          shiftEnd = shiftEnd.subtract(const Duration(hours: 1));
        }

        if (empLogs.isEmpty) {
          // absent — zeros
        } else if (empLogs.length == 1) {
          firstIn = empLogs.first.timestamp;
          noteCheckin = 'Chỉ có 1 lần chấm công';
        } else {
          var fi = empLogs.first.timestamp;
          var lo = fi;
          for (int i = 1; i < empLogs.length; i++) {
            final t = empLogs[i].timestamp;
            if (t.isBefore(fi)) fi = t;
            if (t.isAfter(lo)) lo = t;
          }
          firstIn = fi;
          lastOut = lo;

          if (lo.compareTo(shiftBegin) <= 0) {
            noteCheckin = 'Không chấm công RA';
          } else if (fi.compareTo(shiftEnd) >= 0) {
            noteCheckin = 'Không chấm công VÀO';
          } else if (fi != lo) {
            // ── Normal hours ──────────────────────────────────────────────
            double morning = 0, afternoon = 0;
            if (!fi.isAfter(restBegin)) {
              morning = _normalMorning(fi, lo, shiftBegin, restBegin);
            }
            if (isYoungChild || isPregnant) {
              // shiftEnd already reduced by 1h (= reducedShiftEnd)
              // Credit: 4h if arrived at reducedShiftEnd; else 4 - earlyBy
              afternoon = _youngChildAfternoon(lo, restEnd, shiftEnd);
            } else {
              if (!lo.isBefore(restEnd)) {
                afternoon = _normalAfternoon(fi, lo, shiftEnd, restEnd);
              }
            }
            normalHrs = _floorWorkingToBlock(
              (morning + afternoon).clamp(0, double.infinity),
            );

            // Late / early leave notes
            if (fi.isAfter(shiftBegin)) {
              noteCheckin = _note(noteCheckin, 'Vào trễ');
            }
            if (lo.isBefore(shiftEnd)) {
              noteCheckin = _note(noteCheckin, 'Ra sớm');
            }
          }
        }

        // ── Unified OT block (runs for all log counts: 0 / 1 / ≥2) ──────────
        // Base OT = time after shiftEnd; 0 when no lastOut
        if (lastOut != null) {
          otActual = _floorToBlock(
            (lastOut.difference(shiftEnd).inMinutes / 60.0).clamp(
              0.0,
              double.infinity,
            ),
          );
        }

        if (empIdOT.contains(emp.empId)) {
          // Deduplicate OT records
          var otRecs = (otByEmp[emp.empId] ?? []).toList();
          if (otRecs.length > 1) {
            final uniq = <String, OtRegister>{};
            for (final o in otRecs) {
              if (!uniq.containsKey(o.uniqueKeyWithoutId) ||
                  o.id > uniq[o.uniqueKeyWithoutId]!.id) {
                uniq[o.uniqueKeyWithoutId] = o;
              }
            }
            otRecs = uniq.values.toList();
          }

          if (lastOut != null) {
            // Full path: actual + approved (needs firstIn/lastOut)
            bool otRestHour = false;
            // Filter OT record that covers rest hour (weekday only)
            if (p.restHour > 0 && date.weekday != DateTime.sunday) {
              int restIdx = -1;
              for (int i = 0; i < otRecs.length; i++) {
                final ob =
                    int.tryParse(otRecs[i].otTimeBegin.split(':')[0]) ?? 0;
                final oe = int.tryParse(otRecs[i].otTimeEnd.split(':')[0]) ?? 0;
                if (ob <= restBegin.hour && oe >= restEnd.hour) {
                  otRestHour = true;
                  restIdx = i;
                  break;
                }
              }
              if (restIdx >= 0) {
                otRecs = [
                  for (int i = 0; i < otRecs.length; i++)
                    if (i != restIdx) otRecs[i],
                ];
              }
            }
            if (otRecs.isNotEmpty) {
              // _calcOtRecords computes otFinal per-segment (clamp before summing).
              // Do NOT override with a global clamp afterwards — that would be wrong
              // when one segment is under-actual and another is over-actual.
              final otRes = _calcOtRecords(
                date,
                otRecs,
                firstIn!,
                lastOut,
                shiftBegin,
                shiftEnd,
                otActual,
              );
              otActual = otRes.otActual;
              otApproved = otRes.otApproved;
              otFinal = otRes.otFinal;
            } else {
              // No OT records (all filtered or empty): final = 0
              otFinal = otActual.clamp(0.0, otApproved);
            }
            if (otRestHour && App.gValue.timesheetSettings.allowOtInRestTime) {
              // Rest-hour OT is always fully granted; add to each component separately.
              otActual += p.restHour;
              otApproved += p.restHour;
              otFinal += p.restHour;
              noteCheckin = _note(noteCheckin, 'OT giờ nghỉ trưa');
            }
          } else {
            // 0 or 1 log: approved only — actual stays 0 (no lastOut)
            otApproved = _calcOtApproved(date, otRecs, shiftBegin, shiftEnd);
            // otActual = 0, so otFinal = 0 regardless of otApproved
          }
        }

        // ── Anomaly detection ─────────────────────────────────────────────
        if (empLogs.isNotEmpty && firstIn != null && lastOut != null) {
          final datStr = DateFormat('yyyy-MM-dd').format(date);
          final empTag = '${emp.empId} ${emp.name}';

          // 1. Has resignOn date and attendance on/after that date
          if (emp.resignOn != null &&
              emp.resignOn!.year < 2099 &&
              !date.isBefore(emp.resignOn!.toBeginDay())) {
            anomalies.add(
              '[Resigned + Att] $datStr $empTag — resigned on '
              '${DateFormat('yyyy-MM-dd').format(emp.resignOn!)}'
              ', has ${empLogs.length} log(s)',
            );
          }

          // 2. Day-shift employee leaves 16:xx without a regime — likely missing
          //    maternity/young-child dates in DB.
          if (shift == 'Day' &&
              (emp.workStatus ?? '') == 'Working' &&
              !isYoungChild &&
              !isPregnant &&
              date.weekday != DateTime.sunday &&
              lastOut.hour == 16) {
            anomalies.add(
              '[Ra 16-17h] $datStr $empTag — last out ${DateFormat('HH:mm').format(lastOut)}'
              ' (shift: $shift)',
            );
          }

          // 3. Came in ≥1h early but no OT register covering before-shift
          if (shiftBegin.difference(firstIn).inMinutes >= 60) {
            bool hasBefore =
                empIdOT.contains(emp.empId) &&
                (otByEmp[emp.empId] ?? []).any((r) {
                  final eh = int.tryParse(r.otTimeEnd.split(':')[0]) ?? 0;
                  return eh <= shiftBegin.hour;
                });
            if (!hasBefore) {
              noteCheckin = _note(
                noteCheckin,
                'Vào sớm ≥1h, không có ĐK OT trước ca',
              );
            }
          }

          // 4. Left ≥1h late but no OT register covering after-shift
          // shiftEnd already accounts for regime (pregnant/youngChild = reduced by 1h)
          if (lastOut.difference(shiftEnd).inMinutes >= 60) {
            bool hasAfter =
                empIdOT.contains(emp.empId) &&
                (otByEmp[emp.empId] ?? []).any((r) {
                  final eh = int.tryParse(r.otTimeEnd.split(':')[0]) ?? 0;
                  return eh > shiftEnd.hour;
                });
            if (!hasAfter) {
              noteCheckin = _note(
                noteCheckin,
                'Ra trễ ≥1h, không có ĐK OT sau ca',
              );
            }
          }
        }
        if (isPregnant) {
          noteCheckin = _note(noteCheckin, 'Chế độ mang thai');
        } else if (isYoungChild) {
          noteCheckin = _note(noteCheckin, 'Chế độ con nhỏ');
        }
        // ── Sunday: all worked hours become OT ────────────────────────────
        if (date.weekday == DateTime.sunday) {
          if (otApproved > 0) {
            otApproved = shiftEnd.difference(shiftBegin).inMinutes / 60;
            if (shiftBegin.hour < 12 && shiftEnd.hour > 13) otApproved -= 1;
          }
          otActual = normalHrs;
          normalHrs = 0;
          otFinal = otActual.clamp(0.0, otApproved);
          if (otActual > 0) {
            noteSunday = 'OT ngày CN';
            if (otActual > 4 &&
                firstIn != null &&
                lastOut != null &&
                lastOut.isAfter(restEnd) &&
                firstIn.isBefore(restBegin)) {
              noteSunday = _note(noteSunday, 'Có phụ cấp cơm trưa');
            }
          }
        }
        if (date.isBefore(DateTime(2026, 6, 26))) {
          // Round down to 1 decimal place for legacy behavior before 26 June 2026 : copy từ version cũ
          otActual = _roundDownDouble(otActual, 1);
          otApproved = _roundDownDouble(otApproved, 1);
          otFinal = _roundDownDouble(otFinal, 1);
        } else {
          otActual = _r1(otActual);
          otApproved = _r1(otApproved);
          otFinal = _r1(otFinal);
        }
        result.add(
          TimeSheetDate(
            date: date,
            empId: emp.empId ?? '',
            attFingerId: emp.attFingerId ?? 0,
            name: emp.name ?? '',
            department: emp.department ?? '',
            section: emp.section ?? '',
            group: emp.group ?? '',
            shift: shift,
            firstIn: firstIn,
            lastOut: lastOut,
            normalHours: _r2(normalHrs),
            normalDays: _r2(normalHrs / 8),
            otHours: otActual,
            otHoursApproved: otApproved,
            otHoursFinal: otFinal,
            attNote2: noteCheckin,
            attNote3: noteSunday,
          ),
        );
      }
    }

    return TimesheetResult(result, anomalies);
  }

  // ── Normal hours helpers ─────────────────────────────────────────────────────
  //
  //  Morning  = clipped work between [shiftBegin, restBegin]
  //  Afternoon= clipped work between [restEnd,    shiftEnd]
  //  When restHour == 0, restEnd == restBegin → the two halves are seamless.

  static double _normalMorning(
    DateTime fi,
    DateTime lo,
    DateTime shiftBegin,
    DateTime restBegin,
  ) {
    final start = fi.isBefore(shiftBegin) ? shiftBegin : fi;
    final end = lo.isBefore(restBegin) ? lo : restBegin;
    return (end.difference(start).inMinutes / 60).clamp(0, double.infinity);
  }

  static double _normalAfternoon(
    DateTime fi,
    DateTime lo,
    DateTime shiftEnd,
    DateTime restEnd,
  ) {
    final start = fi.isAfter(restEnd) ? fi : restEnd;
    final end = lo.isAfter(shiftEnd) ? shiftEnd : lo;
    return (end.difference(start).inMinutes / 60).clamp(0, double.infinity);
  }

  /// Afternoon hours for "young child / pregnant" employees.
  ///
  /// [shiftEnd] is already the **reduced** end (original − 1h).
  /// Rules:
  ///   • lo < restEnd              → 0 h  (didn't work the afternoon)
  ///   • lo ≥ reducedShiftEnd      → 4 h  (full afternoon credit = 8 - 0)
  ///   • lo < reducedShiftEnd      → 4 − earlyBy  where earlyBy = (reducedShiftEnd − lo) in h
  ///     Combined with morning (4h): total = 8 − earlyBy (regardless of whether lo falls
  ///     in afternoon, rest window, or even morning — the clamp prevents negative values).
  ///   floor at 0; cap at 4.
  static double _youngChildAfternoon(
    DateTime lo,
    DateTime restEnd,
    DateTime reducedShiftEnd,
  ) {
    if (!lo.isBefore(reducedShiftEnd)) return 4; // on time or later
    // Left before the reduced end → partial credit: 8 - earlyBy total (incl. morning 4h)
    final earlyBy = reducedShiftEnd.difference(lo).inMinutes / 60;
    return (4 - earlyBy).clamp(0, 4);
  }

  // ── OT calculation: process all records, split before/after shift ────────────

  /// Calculate only otApproved from OT registers (no fi/lo needed).
  /// Used when empLogs.length == 1 — actual OT is 0 but approved is still valid.
  static double _calcOtApproved(
    DateTime date,
    List<OtRegister> recs,
    DateTime shiftBegin,
    DateTime shiftEnd,
  ) {
    double approved = 0;
    DateTime? beforeEarliestBegin, beforeLatestEnd;
    DateTime? afterEarliestBegin, afterLatestEnd;

    for (final rec in recs) {
      final b = _parseShiftTime(date, rec.otTimeBegin);
      final e = _parseShiftTime(date, rec.otTimeEnd);
      if (b == null || e == null) continue;
      final bh = b.hour, eh = e.hour;

      if (date.weekday == DateTime.sunday && bh < 12 && eh > 13) {
        // Sunday full-day: approved = duration − 1h lunch
        approved += e.difference(b).inMinutes / 60.0 - 1;
      } else if (eh <= shiftBegin.hour) {
        // Before shift
        if (beforeEarliestBegin == null || b.isBefore(beforeEarliestBegin))
          beforeEarliestBegin = b;
        if (beforeLatestEnd == null || e.isAfter(beforeLatestEnd))
          beforeLatestEnd = e;
      } else if (bh >= shiftEnd.hour) {
        // After shift
        if (afterEarliestBegin == null || b.isBefore(afterEarliestBegin))
          afterEarliestBegin = b;
        if (afterLatestEnd == null || e.isAfter(afterLatestEnd))
          afterLatestEnd = e;
      }
    }
    if (beforeEarliestBegin != null && beforeLatestEnd != null) {
      approved +=
          beforeLatestEnd.difference(beforeEarliestBegin).inMinutes / 60.0;
    }
    if (afterEarliestBegin != null && afterLatestEnd != null) {
      approved +=
          afterLatestEnd.difference(afterEarliestBegin).inMinutes / 60.0;
    }
    return approved;
  }

  /// Calculate OT from a list of OT records, separating before-shift and
  /// after-shift independently. Each part applies _floorToBlock and _minOtMin.
  /// Sunday full-day records are handled as a special case.
  static _OtResult _calcOtRecords(
    DateTime date,
    List<OtRegister> recs,
    DateTime fi,
    DateTime lo,
    DateTime shiftBegin,
    DateTime shiftEnd,
    double baseOtActual,
  ) {
    double totalActual = 0, totalApproved = 0, totalFinal = 0;
    // Classify records into before/after/sunday-full
    final beforeRecs = <OtRegister>[];
    final afterRecs = <OtRegister>[];
    OtRegister? sundayFullRec;

    for (final rec in recs) {
      final beginOT = _parseShiftTime(date, rec.otTimeBegin);
      final endOT = _parseShiftTime(date, rec.otTimeEnd);
      if (beginOT == null || endOT == null) continue;

      final bh = beginOT.hour, eh = endOT.hour;

      // Sunday full-day spanning noon
      if (date.weekday == DateTime.sunday && bh < 12 && eh > 13) {
        sundayFullRec = rec;
      }
      // Before shift: ends at or before shift start
      else if (eh <= shiftBegin.hour) {
        beforeRecs.add(rec);
      }
      // After shift: starts at or after shift end
      else if (bh >= shiftEnd.hour) {
        afterRecs.add(rec);
      }
    }

    // ── Sunday full-day ──
    if (sundayFullRec != null) {
      final beginOT = _parseShiftTime(date, sundayFullRec.otTimeBegin)!;
      final endOT = _parseShiftTime(date, sundayFullRec.otTimeEnd)!;
      double otApproved =
          endOT.difference(beginOT).inMinutes / 60.0 - 1; // deduct lunch
      double otActual = baseOtActual;
      if (fi.isBefore(shiftBegin) && fi.hour <= shiftBegin.hour) {
        otActual = (shiftBegin.difference(fi).inMinutes / 60.0).clamp(
          0.0,
          double.infinity,
        );
      }
      final double otFinal = otActual.clamp(0.0, otApproved);
      return _OtResult(otActual, otApproved, otFinal);
    }

    // ── Before shift ──
    if (beforeRecs.isNotEmpty) {
      // Use earliest begin and latest end across all before records
      DateTime? earliestBegin, latestEnd;
      for (final rec in beforeRecs) {
        final b = _parseShiftTime(date, rec.otTimeBegin);
        final e = _parseShiftTime(date, rec.otTimeEnd);
        if (b == null || e == null) continue;
        if (earliestBegin == null || b.isBefore(earliestBegin))
          earliestBegin = b;
        if (latestEnd == null || e.isAfter(latestEnd)) latestEnd = e;
      }
      if (earliestBegin != null && latestEnd != null) {
        final double otApproved =
            latestEnd.difference(earliestBegin).inMinutes / 60;
        // Actual = time employee arrived early, capped to approved window
        final earliestStart = shiftBegin.subtract(
          Duration(minutes: (otApproved * 60).toInt()),
        );
        double rawActual = fi.isBefore(earliestStart)
            ? otApproved
            : (shiftBegin.difference(fi).inMinutes / 60.0).clamp(
                0.0,
                double.infinity,
              );
        final otActual = _floorToBlock(rawActual);
        final double otFinal = otActual.clamp(0.0, otApproved);

        totalActual += otActual;
        totalApproved += otApproved;
        totalFinal += otFinal;
      }
    }

    // ── After shift ──
    if (afterRecs.isNotEmpty) {
      // Use earliest begin and latest end across all after records
      DateTime? earliestBegin, latestEnd;
      for (final rec in afterRecs) {
        final b = _parseShiftTime(date, rec.otTimeBegin);
        final e = _parseShiftTime(date, rec.otTimeEnd);
        if (b == null || e == null) continue;
        if (earliestBegin == null || b.isBefore(earliestBegin))
          earliestBegin = b;
        if (latestEnd == null || e.isAfter(latestEnd)) latestEnd = e;
      }
      if (earliestBegin != null && latestEnd != null) {
        final double otApproved =
            latestEnd.difference(earliestBegin).inMinutes / 60;
        // Actual = real time worked after shift end (lo - shiftEnd), NOT capped by OT register.
        // OT Final handles the cap via clamp(0, otApproved).
        final double rawActual = lo.isAfter(shiftEnd)
            ? (lo.difference(shiftEnd).inMinutes / 60.0).clamp(
                0.0,
                double.infinity,
              )
            : 0.0;
        final otActual = _floorToBlock(rawActual);
        final double otFinal = otActual.clamp(0.0, otApproved);

        totalActual += otActual;
        totalApproved += otApproved;
        totalFinal += otFinal;
      }
    }

    // If no classified records matched, fall back to base OT (no register match)
    if (beforeRecs.isEmpty && afterRecs.isEmpty && sundayFullRec == null) {
      return _OtResult(_floorToBlock(baseOtActual), 0, 0);
    }

    return _OtResult(totalActual, totalApproved, totalFinal);
  }

  // ── Excel export ─────────────────────────────────────────────────────────────

  /// Round to 1 decimal, half-up (OT values: 1.25 → 1.3)
  static double _r1(double v) => double.parse(v.toStringAsFixed(1));

  /// Round to 2 decimals, half-up (normal hours: 1.235 → 1.24)
  static double _r2(double v) => double.parse(v.toStringAsFixed(2));
  static double _roundDownDouble(double value, int places) {
    num mod = pow(10.0, places);
    // Thay .round() bằng .floor()
    return ((value * mod).floor().toDouble() / mod);
  }

  // Create an xl.Table with tableStyleMedium16 style
  static void _xlsTable(
    xl.Worksheet sheet,
    int lastRow,
    int lastCol,
    String name, {
    bool clearDataBorders = false,
  }) {
    if (lastRow < 2 || lastCol < 1) return;
    final range = sheet.getRangeByIndex(1, 1, lastRow, lastCol);
    final table = sheet.tableCollection.create(name, range);
    table.builtInTableStyle = xl.ExcelTableBuiltInStyle.tableStyleMedium16;
    table.showBandedRows = true;
    table.showFirstColumn = false;
    table.showLastColumn = false;
    if (clearDataBorders && lastRow > 1) {
      final dataRange = sheet.getRangeByIndex(2, 1, lastRow, lastCol);
      dataRange.cellStyle.borders.all.lineStyle = xl.LineStyle.none;
    }
  }

  static Future<void> exportTimesheets(
    TimesheetResult tsResult, {
    required List<Employee> employees,
    List<DateTime>? dateRange,
  }) async {
    final data = tsResult.data;
    final anomalies = tsResult.anomalies;
    if (data.isEmpty) {
      showToast('No timesheet data to export');
      return;
    }
    try {
      final workbook = xl.Workbook();

      // Build employee lookup
      final empLookup = <String, Employee>{
        for (final e in employees)
          if (e.empId != null) e.empId!: e,
      };

      DateTime? _joiningDate(Employee? emp) {
        if (emp?.joiningDate == null || emp!.joiningDate!.year <= 1900)
          return null;
        return emp.joiningDate;
      }

      DateTime? _resignDate(Employee? emp) {
        if (emp?.resignOn == null || emp!.resignOn!.year >= 2099) return null;
        if (!(emp.workStatus ?? '').contains('Resigned')) return null;
        return emp.resignOn;
      }

      void _setDate(xl.Range cell, DateTime? d) {
        if (d == null) return;
        cell.setDateTime(d);
        cell.numberFormat = 'dd/MM/yyyy';
      }

      void _setTime(xl.Range cell, DateTime? t) {
        if (t == null) return;
        cell.setDateTime(t);
        cell.numberFormat = 'HH:mm';
      }

      void _setNum(xl.Range cell, double v) {
        cell.setNumber(_r2(v));
        cell.numberFormat = '0.00';
      }

      void setOtNum(xl.Range cell, double v) {
        cell.setNumber(_r1(v));
        cell.numberFormat = '0.0';
      }

      // ── Sheet 0: Important Note ─────────────────────────────────────────────
      final noteSheet = workbook.worksheets[0];
      noteSheet.name = 'Important Note';
      noteSheet
          .getRangeByIndex(1, 1)
          .setText(
            'Important Note — generated ${DateFormat('dd/MM/yyyy HH:mm').format(DateTime.now())}',
          );
      noteSheet.getRangeByIndex(3, 1).setText('Type');
      noteSheet.getRangeByIndex(3, 2).setText('Detail');
      final noteHdr = noteSheet.getRangeByIndex(3, 1, 3, 2);
      noteHdr.cellStyle.bold = true;
      noteHdr.cellStyle.backColor = '#D9E2F3';
      noteHdr.cellStyle.hAlign = xl.HAlignType.center;
      noteHdr.cellStyle.borders.all.lineStyle = xl.LineStyle.thin;

      int noteRow = 4;
      if (anomalies.isEmpty) {
        noteSheet.getRangeByIndex(noteRow, 2).setText('No anomalies detected.');
        noteRow++;
      } else {
        for (final a in anomalies) {
          final typeEnd = a.indexOf(']');
          noteSheet
              .getRangeByIndex(noteRow, 1)
              .setText(typeEnd > 0 ? a.substring(0, typeEnd + 1) : '');
          noteSheet
              .getRangeByIndex(noteRow, 2)
              .setText(typeEnd > 0 ? a.substring(typeEnd + 2) : a);
          noteRow++;
        }
      }
      if (noteRow > 4) {
        noteSheet
                .getRangeByIndex(4, 1, noteRow - 1, 2)
                .cellStyle
                .borders
                .all
                .lineStyle =
            xl.LineStyle.thin;
      }
      noteSheet.getRangeByIndex(1, 1).columnWidth = 20;
      noteSheet.getRangeByIndex(1, 2).columnWidth = 80;

      // ── Sheet 1: Detail ─────────────────────────────────────────────────────
      final detail = workbook.worksheets.addWithName('Detail');
      const detailHdrs = [
        'No',
        'Date',
        'Employee ID',
        'Finger ID',
        'Full name',
        'Department',
        'Section',
        'Group',
        'Shift',
        'First In',
        'Last Out',
        'Working (hour)',
        'Working (day)',
        'OT Actual (hours)',
        'OT Approved (hours)',
        'OT Final',
        'Note Checkin',
        'Note Sunday',
        'Joining Date',
        'Resign Date',
      ];
      for (int c = 0; c < detailHdrs.length; c++) {
        detail.getRangeByIndex(1, c + 1).setText(detailHdrs[c]);
      }

      // Sort Detail: date ASC, then empId ASC
      final detailData = [...data]
        ..sort((a, b) {
          final dc = a.date.compareTo(b.date);
          return dc != 0 ? dc : a.empId.compareTo(b.empId);
        });

      int detailNo = 1;
      for (final ts in detailData) {
        final row = detailNo + 1;
        final emp = empLookup[ts.empId];
        detail.getRangeByIndex(row, 1).setNumber(detailNo.toDouble());
        _setDate(detail.getRangeByIndex(row, 2), ts.date);
        detail.getRangeByIndex(row, 3).setText(ts.empId);
        detail.getRangeByIndex(row, 4).setNumber(ts.attFingerId.toDouble());
        detail.getRangeByIndex(row, 5).setText(ts.name);
        detail.getRangeByIndex(row, 6).setText(ts.department);
        detail.getRangeByIndex(row, 7).setText(ts.section);
        detail.getRangeByIndex(row, 8).setText(ts.group);
        detail.getRangeByIndex(row, 9).setText(ts.shift);
        _setTime(detail.getRangeByIndex(row, 10), ts.firstIn);
        _setTime(detail.getRangeByIndex(row, 11), ts.lastOut);
        _setNum(detail.getRangeByIndex(row, 12), ts.normalHours);
        _setNum(detail.getRangeByIndex(row, 13), ts.normalDays);
        setOtNum(detail.getRangeByIndex(row, 14), ts.otHours);
        setOtNum(detail.getRangeByIndex(row, 15), ts.otHoursApproved);
        setOtNum(detail.getRangeByIndex(row, 16), ts.otHoursFinal);
        detail.getRangeByIndex(row, 17).setText(ts.attNote2);
        detail.getRangeByIndex(row, 18).setText(ts.attNote3);
        _setDate(detail.getRangeByIndex(row, 19), _joiningDate(emp));
        _setDate(detail.getRangeByIndex(row, 20), _resignDate(emp));
        detailNo++;
      }
      _xlsTable(detail, data.length + 1, detailHdrs.length, 'TableDetail');
      // Fixed column widths + header height/wrap
      const detailWidths = [
        4.0,
        10.0,
        10.0,
        6.0,
        24.0,
        10.0,
        14.0,
        18.0,
        7.0,
        8.0,
        8.0,
        8.0,
        8.0,
        8.0,
        8.0,
        8.0,
        20.0,
        20.0,
        10.0,
        10.0,
      ];
      for (int i = 0; i < detailWidths.length; i++) {
        detail.getRangeByIndex(1, i + 1).columnWidth = detailWidths[i];
      }
      detail.getRangeByIndex(1, 1, 1, detailHdrs.length).rowHeight = 50;
      detail.getRangeByIndex(1, 1, 1, detailHdrs.length).cellStyle.wrapText =
          true;

      // ── Unified fixed columns for Summary / pivot sheets / Shift ────────────
      // Order: No, Employee ID, Joining Date, Resign Date, Full name, Group, Section, Position
      const empFixed = 8;
      const empFixedHdrs = [
        'No',
        'Employee ID',
        'Full name',
        'Joining Date',
        'Resign Date',
        'Group',
        'Section',
        'Position',
      ];
      const empFixedWidths = [4.0, 12.0, 24.0, 10.0, 10.0, 18.0, 14.0, 14.0];

      // Write fixed employee columns (1‥8) for a data row and apply border.
      void writeFixed(
        xl.Worksheet s,
        int row,
        int no,
        String empId,
        Employee? emp, {
        String name = '',
        String section = '',
        String group = '',
      }) {
        s.getRangeByIndex(row, 1).setNumber(no.toDouble());
        s.getRangeByIndex(row, 2).setText(empId);
        s.getRangeByIndex(row, 3).setText(emp?.name ?? name);
        _setDate(s.getRangeByIndex(row, 4), _joiningDate(emp));
        _setDate(s.getRangeByIndex(row, 5), _resignDate(emp));
        s.getRangeByIndex(row, 6).setText(emp?.group ?? group);
        s.getRangeByIndex(row, 7).setText(emp?.section ?? section);
        s.getRangeByIndex(row, 8).setText(emp?.position ?? '');
      }

      // Apply fixed header labels + wrapText/height to a sheet.
      void writeFixedHeader(
        xl.Worksheet s,
        int lastCol,
        List<String> extraHdrs,
      ) {
        for (int c = 0; c < empFixedHdrs.length; c++) {
          s.getRangeByIndex(1, c + 1).setText(empFixedHdrs[c]);
        }
        for (int i = 0; i < extraHdrs.length; i++) {
          s.getRangeByIndex(1, empFixed + 1 + i).setText(extraHdrs[i]);
        }
        final hdr = s.getRangeByIndex(1, 1, 1, lastCol);
        hdr.cellStyle.wrapText = true;
        hdr.rowHeight = 50;
      }

      // Apply fixed column widths + extra widths to a sheet.
      void applyWidths(xl.Worksheet s, List<double> extraWidths) {
        for (int i = 0; i < empFixedWidths.length; i++) {
          s.getRangeByIndex(1, i + 1).columnWidth = empFixedWidths[i];
        }
        for (int i = 0; i < extraWidths.length; i++) {
          s.getRangeByIndex(1, empFixed + 1 + i).columnWidth = extraWidths[i];
        }
      }

      // ── Sheet 2: Summary ────────────────────────────────────────────────────
      final totals = <String, _EmpSummary>{};
      for (final ts in data) {
        totals.putIfAbsent(
          ts.empId,
          () => _EmpSummary(
            empId: ts.empId,
            name: ts.name,
            section: ts.section,
            group: ts.group,
          ),
        );
        final s = totals[ts.empId]!;
        s.totalNormalHours += ts.normalHours;
        s.totalWorkingDays += ts.normalDays;
        s.totalOtActual += ts.otHours;
        s.totalOtApproved += ts.otHoursApproved;
        s.totalOtFinal += ts.otHoursFinal;
      }
      // Sort by empId ASC
      final sumEmpOrder = totals.keys.toList()..sort();

      const sumExtraHdrs = [
        'Total Working (hours)',
        'Total Working (days)',
        'Total OT Actual (hours)',
        'Total OT Approved (hours)',
        'Total OT Final (hours)',
      ];
      const sumLastCol = empFixed + 5;

      final summary = workbook.worksheets.addWithName('Summary');
      writeFixedHeader(summary, sumLastCol, sumExtraHdrs);

      int sumNo = 1;
      for (final empId in sumEmpOrder) {
        final s = totals[empId]!;
        final emp = empLookup[empId];
        final row = sumNo + 1;
        writeFixed(
          summary,
          row,
          sumNo,
          empId,
          emp,
          name: s.name,
          section: s.section,
          group: s.group,
        );
        _setNum(summary.getRangeByIndex(row, empFixed + 1), s.totalNormalHours);
        _setNum(summary.getRangeByIndex(row, empFixed + 2), s.totalWorkingDays);
        setOtNum(summary.getRangeByIndex(row, empFixed + 3), s.totalOtActual);
        setOtNum(summary.getRangeByIndex(row, empFixed + 4), s.totalOtApproved);
        setOtNum(summary.getRangeByIndex(row, empFixed + 5), s.totalOtFinal);
        sumNo++;
      }
      _xlsTable(
        summary,
        sumEmpOrder.length + 1,
        sumLastCol,
        'TableSummary',
        clearDataBorders: true,
      );
      applyWidths(summary, [8.0, 8.0, 8.0, 8.0, 8.0]);
      summary.getRangeByIndex(1, 1, 1, sumLastCol).rowHeight = 50;
      summary.getRangeByIndex(1, 1, 1, sumLastCol).cellStyle.wrapText = true;

      // ── Shared pivot data (sorted by empId) ──────────────────────────────────
      // Build emp order + date map from all data; sort by empId.
      final pivotEmpSet = <String>{};
      final pivotEmpInfo = <String, TimeSheetDate>{};
      final pivotDateMap = <String, DateTime>{};
      for (final ts in data) {
        final dk = _dayKey(ts.date);
        pivotDateMap[dk] = ts.date;
        if (pivotEmpSet.add(ts.empId)) {
          pivotEmpInfo[ts.empId] = ts;
        }
      }
      final pivotEmpOrder = pivotEmpSet.toList()..sort();

      // Build continuous date list from dateRange; fall back to dates in data.
      final List<DateTime> allPivotDates;
      if (dateRange != null && dateRange.length >= 2) {
        final from = dateRange.first;
        final to = dateRange.last;
        allPivotDates = [
          for (var d = from; !d.isAfter(to); d = d.add(const Duration(days: 1)))
            d,
        ];
      } else {
        final sortedKeys = pivotDateMap.keys.toList()..sort();
        allPivotDates = [for (final k in sortedKeys) pivotDateMap[k]!];
      }
      final sortedPivotDates = [for (final d in allPivotDates) _dayKey(d)];
      final pivotDateCols = sortedPivotDates.length;
      final pivotTotalCol = empFixed + pivotDateCols + 1;
      final dateFmtPivot = DateFormat('dd/MM');
      const sundayGray = '#D9D9D9';

      // Write a numeric pivot sheet (Timesheet / Overtime).
      void writePivotSheet({
        required String sheetName,
        required String tableName,
        required String numberFmt,
        required Map<String, Map<String, double>> pivotValues,
        bool skipZeroRows = false,
      }) {
        final sheet = workbook.worksheets.addWithName(sheetName);
        final dateHdrs = [
          for (final d in allPivotDates) dateFmtPivot.format(d),
          'Total',
        ];
        writeFixedHeader(sheet, pivotTotalCol, dateHdrs);

        void applyCell(xl.Range cell, double val) {
          if (val > 0) {
            cell.setNumber(val);
            cell.numberFormat = val == val.truncateToDouble() ? '0' : numberFmt;
          }
          cell.cellStyle.hAlign = xl.HAlignType.center;
        }

        int rowNo = 1;
        for (final empId in pivotEmpOrder) {
          final dayMap = pivotValues[empId] ?? {};
          final total = dayMap.values.fold(0.0, (a, b) => a + b);
          if (skipZeroRows && total == 0) continue;

          final row = rowNo + 1;
          final info = pivotEmpInfo[empId]!;
          final emp = empLookup[empId];
          writeFixed(
            sheet,
            row,
            rowNo,
            empId,
            emp,
            name: info.name,
            section: info.section,
            group: info.group,
          );
          for (int ci = 0; ci < pivotDateCols; ci++) {
            final val = dayMap[sortedPivotDates[ci]] ?? 0.0;
            applyCell(sheet.getRangeByIndex(row, empFixed + 1 + ci), val);
          }
          applyCell(sheet.getRangeByIndex(row, pivotTotalCol), total);
          rowNo++;
        }

        _xlsTable(
          sheet,
          rowNo, // rowNo = actual data rows written + 1 (header)
          pivotTotalCol,
          tableName,
          clearDataBorders: true,
        );
        applyWidths(sheet, [
          for (int ci = 0; ci <= pivotDateCols; ci++)
            ci < pivotDateCols ? 6.0 : 8.0,
        ]);

        // Sunday: gray header cell only; explicitly reset data rows to white
        // (Syncfusion propagates backColor to the whole column, so we undo it)
        final dataLastRow = rowNo - 1; // last data row index (1-based)
        for (int ci = 0; ci < pivotDateCols; ci++) {
          if (allPivotDates[ci].weekday != DateTime.sunday) continue;
          final col = empFixed + 1 + ci;
          sheet.getRangeByIndex(1, col, 1, col).cellStyle.backColor =
              sundayGray;
          if (dataLastRow >= 2) {
            sheet
                    .getRangeByIndex(2, col, dataLastRow, col)
                    .cellStyle
                    .backColor =
                '#FFFFFF';
          }
        }
      }

      // ── Sheet 3: Timesheet pivot (Working day) ───────────────────────────────
      {
        final tsPivot = <String, Map<String, double>>{};
        for (final ts in data) {
          tsPivot.putIfAbsent(ts.empId, () => {});
          final dk = _dayKey(ts.date);
          tsPivot[ts.empId]![dk] =
              (tsPivot[ts.empId]![dk] ?? 0) + ts.normalDays;
        }
        writePivotSheet(
          sheetName: 'Timesheet',
          tableName: 'TableTimesheet',
          numberFmt: '0.##',
          pivotValues: tsPivot,
        );
      }

      // ── Sheet 4: Overtime pivot (OT Final hours) ─────────────────────────────
      {
        final otPivot = <String, Map<String, double>>{};
        for (final ts in data) {
          if (ts.otHoursFinal <= 0) continue;
          otPivot.putIfAbsent(ts.empId, () => {});
          final dk = _dayKey(ts.date);
          otPivot[ts.empId]![dk] =
              (otPivot[ts.empId]![dk] ?? 0) + ts.otHoursFinal;
        }
        writePivotSheet(
          sheetName: 'Overtime',
          tableName: 'TableOvertime',
          numberFmt: '0.#',
          pivotValues: otPivot,
          skipZeroRows: true,
        );
      }

      // ── Sheet 5: Shift pivot ─────────────────────────────────────────────────
      final shiftDataMap = <String, Map<String, String>>{};
      final shiftEmpSet = <String>{};
      for (final ts in data) {
        if (ts.shift != 'Shift 1' && ts.shift != 'Shift 2') continue;
        shiftEmpSet.add(ts.empId);
        shiftDataMap.putIfAbsent(ts.empId, () => {})[_dayKey(ts.date)] =
            ts.shift;
      }

      if (shiftDataMap.isNotEmpty) {
        final shiftEmpOrder = shiftEmpSet.toList()..sort();
        // Use the same continuous date range as Timesheet/Overtime
        final shiftLastCol = empFixed + pivotDateCols;
        final shiftSheet = workbook.worksheets.addWithName('Shift');

        writeFixedHeader(shiftSheet, shiftLastCol, [
          for (final d in allPivotDates) dateFmtPivot.format(d),
        ]);

        const shift1Color = '#C55A11'; // dark orange
        const shift2Color = '#1F4E79'; // dark blue

        int shiftRow = 1;
        for (final empId in shiftEmpOrder) {
          final row = shiftRow + 1;
          final emp = empLookup[empId];
          final shiftMap = shiftDataMap[empId]!;
          writeFixed(shiftSheet, row, shiftRow, empId, emp);
          for (int ci = 0; ci < pivotDateCols; ci++) {
            final dk = sortedPivotDates[ci];
            final val = shiftMap[dk] ?? '';
            final cell = shiftSheet.getRangeByIndex(row, empFixed + 1 + ci);
            cell.setText(val);
            cell.cellStyle.hAlign = xl.HAlignType.center;
            cell.cellStyle.bold = true;
            if (val == 'Shift 1') cell.cellStyle.fontColor = shift1Color;
            if (val == 'Shift 2') cell.cellStyle.fontColor = shift2Color;
          }
          shiftRow++;
        }

        _xlsTable(
          shiftSheet,
          shiftEmpOrder.length + 1,
          shiftLastCol,
          'TableShift',
          clearDataBorders: true,
        );
        applyWidths(shiftSheet, [
          for (int ci = 0; ci < pivotDateCols; ci++) 8.0,
        ]);

        // Sunday: gray header only (no data cell backColor to reset)
        for (int ci = 0; ci < pivotDateCols; ci++) {
          if (allPivotDates[ci].weekday != DateTime.sunday) continue;
          final col = empFixed + 1 + ci;
          shiftSheet.getRangeByIndex(1, col, 1, col).cellStyle.backColor =
              sundayGray;
        }
      }

      await MyFunctions.saveAndOpenWorkbook(
        workbook,
        MyFunctions.exportFileName('Timesheet', dateRange: dateRange),
      );
    } catch (e) {
      showToast('Export error: $e');
    }
  }
}

// ── Helper for summary aggregation ───────────────────────────────────────────

class _EmpSummary {
  final String empId, name, section, group;
  double totalNormalHours = 0;
  double totalWorkingDays = 0;
  double totalOtActual = 0;
  double totalOtApproved = 0;
  double totalOtFinal = 0;

  _EmpSummary({
    required this.empId,
    required this.name,
    required this.section,
    required this.group,
  });
}

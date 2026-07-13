import 'dart:convert' show utf8;
import 'dart:io';
import 'dart:typed_data';
import 'package:archive/archive.dart';
import 'package:attandance_client/appColors.dart';
import 'package:attandance_client/main.dart';
import 'package:attandance_client/model/attLog.dart';
import 'package:attandance_client/model/employee.dart';
import 'package:attandance_client/model/otRegister.dart';
import 'package:attandance_client/model/shiftRegister.dart';
import 'package:syncfusion_flutter_xlsio/xlsio.dart' as xl;
import 'package:file_picker/file_picker.dart';
import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:loader_overlay/loader_overlay.dart';
import 'package:oktoast/oktoast.dart';
import 'package:syncfusion_flutter_datagrid/datagrid.dart';
import 'package:syncfusion_flutter_datepicker/datepicker.dart';

/// Hàm nhận vào chuỗi mã và trả về List chứa [startDate, endDate]
class MyFunctions {
  /// Extract [start, end] directly from a PickerDateRange — works in release.
  static List<DateTime> extractDateRangeFromPicker(dynamic value) {
    if (value == null) return [];
    // Cast to PickerDateRange to avoid toString() tree-shaking in release
    try {
      final range = value as PickerDateRange;
      final start = range.startDate;
      final end = range.endDate ?? range.startDate;
      if (start == null) return [];
      return [start.toBeginDay(), end!.toEndDay()];
    } catch (_) {
      // fallback to string parsing for any unexpected type
      return extractDateRange(value.toString());
    }
  }

  static List<DateTime> extractDateRange(String input) {
    // Biểu thức chính quy để tìm chuỗi ngày tháng năm
    RegExp regExp = RegExp(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}');
    Iterable<Match> matches = regExp.allMatches(input);

    if (matches.length >= 2) {
      DateTime startDate = DateTime.parse(matches.elementAt(0).group(0)!);
      DateTime endDate = DateTime.parse(
        matches.elementAt(1).group(0)!,
      ).toEndDay();

      // Trả về list chứa 2 phần tử theo đúng yêu cầu
      return [startDate, endDate];
    }
    if (matches.length == 1) {
      DateTime startDate = DateTime.parse(
        matches.elementAt(0).group(0)!,
      ).toBeginDay();

      DateTime endDate = startDate.toEndDay();
      return [startDate, endDate]; // endDate lấy giá trị của startDate
    }

    // Trả về list rỗng nếu chuỗi đầu vào không hợp lệ hoặc không đủ dữ liệu
    return [];
  }

  static Future<void> loadData(String type, BuildContext context) async {
    showToast('Loading : $type', backgroundColor: AppColors.textSecondary);
    context.loaderOverlay.show();
    switch (type) {
      case 'employee':
        // Load employee data
        App.gValue.employees = await App.mongoDb.getEmployees();

        break;
      case 'attLog':
        // Load attendance log data
        App.gValue.attLogs = await App.mongoDb.getAttLogs(
          App.gValue.dateRangeAtt,
        );
        break;
      case 'overtime':
        App.gValue.otRegisters = await App.mongoDb.getOvertime(
          App.gValue.dateRangeOvertime,
        );
        break;
      case 'shift':
        App.gValue.shiftRegisters = await App.mongoDb.getShiftRegisters(
          App.gValue.dateRangeShift,
        );
        break;
      case 'history':
        App.gValue.histories = await App.mongoDb.getHistory(
          App.gValue.dateRangeHistory,
        );
        break;
      case 'all':
        // Load all
        App.gValue.employees = await App.mongoDb.getEmployees();
        App.gValue.attLogs = await App.mongoDb.getAttLogs(
          App.gValue.dateRangeAtt,
        );
        App.gValue.otRegisters = await App.mongoDb.getOvertime(
          App.gValue.dateRangeOvertime,
        );
        App.gValue.shiftRegisters = await App.mongoDb.getShiftRegisters(
          App.gValue.dateRangeShift,
        );
        break;
      default:
    }
    context.loaderOverlay.hide();
  }

  /// Returns a map with keys 'present' and 'absent', each containing a list of [Employee].
  /// Active on [date] = workStatus contains 'Working', OR workStatus contains 'Resigned' but resignOn > date.
  static Map<String, List<Employee>> getPresentAbsent(
    DateTime date, {
    List<AttLog>? attLogs,
    List<Employee>? employees,
  }) {
    final logs = attLogs ?? App.gValue.attLogs;
    final emps = employees ?? App.gValue.employees;
    final dayStart = DateTime(date.year, date.month, date.day);
    final dayEnd = dayStart.add(const Duration(days: 1));

    final activeEmployees = emps.where((e) {
      final status = e.workStatus ?? '';
      if (status.contains('Working')) return true;
      if (status.contains('Resigned')) {
        return e.resignOn != null && e.resignOn!.isAfter(date);
      }
      return false;
    }).toList();

    final presentEmpIds = logs
        .where(
          (l) => l.timestamp.isAfter(dayStart) && l.timestamp.isBefore(dayEnd),
        )
        .map((l) => l.empId)
        .toSet();

    final present = activeEmployees
        .where((e) => presentEmpIds.contains(e.empId))
        .toList();
    final absent = activeEmployees
        .where((e) => !presentEmpIds.contains(e.empId))
        .toList();

    return {'present': present, 'absent': absent};
  }

  static Map<String, String> getEmployeeMap() {
    Map<String, String> employeeMap = {};
    for (var emp in App.gValue.employees) {
      // filter : eclude workStatus = 'resigned' and resignedOn < DateTime.now() -30 days
      if (emp.workStatus == 'Resigned' && emp.resignOn != null) {
        if (emp.resignOn!.isBefore(
          DateTime.now().subtract(Duration(days: 30)),
        )) {
          continue; // skip employee resigned more than 30 days
        }
      }
      employeeMap[emp.empId ?? ''] = '${emp.empId!} ${emp.name!} ${emp.group!}';
    }
    return employeeMap;
  }

  /// Generate a file name with timestamp: [type]_YYMMDD_HHMMSS
  /// If [dateRange] is provided: [type]_fromYYMMDD_toYYMMDD_HHMMSS
  static String exportFileName(String type, {List<DateTime>? dateRange}) {
    final now = DateTime.now();
    final ts = DateFormat('yyMMdd_HHmmss').format(now);
    if (dateRange != null && dateRange.length == 2) {
      final from = DateFormat('yyMMdd').format(dateRange[0]);
      final to = DateFormat('yyMMdd').format(dateRange[1]);
      return '${type}_${from}_${to}_$ts';
    }
    return '${type}_$ts';
  }

  /// Save workbook bytes to file, show toast, and open the file.
  static Future<void> saveAndOpenWorkbook(
    xl.Workbook workbook,
    String fileName,
  ) async {
    await Future.delayed(const Duration(milliseconds: 50));
    final bytes = Uint8List.fromList(workbook.saveAsStream());
    workbook.dispose();
    final path = await FileSaver.instance.saveFile(
      name: fileName,
      bytes: bytes,
      fileExtension: 'xlsx',
      mimeType: MimeType.microsoftExcel,
    );
    showToast('Exported at Download\\$fileName.xlsx');
    if (Platform.isWindows) Process.run('explorer', [path]);
  }

  // Set a cell value using the appropriate xlsio method
  static void _setCellValue(xl.Range range, dynamic v) {
    if (v == null) {
      range.setText('');
      return;
    }
    if (v is int) {
      range.setNumber(v.toDouble());
      return;
    }
    if (v is double) {
      range.setNumber(v);
      range.numberFormat = '0.00';
      return;
    }
    if (v is DateTime) {
      range.setDateTime(v);
      range.numberFormat = 'dd/MM/yyyy';
      return;
    }
    range.setText(v.toString());
  }

  // Apply column widths: data-driven (long header names don't inflate width)
  static void _applyColumnWidths(
    xl.Worksheet sheet,
    List<String> headers,
    List<List<dynamic>> rows,
  ) {
    for (int ci = 0; ci < headers.length; ci++) {
      final col = ci + 1;
      final hLen = headers[ci].length.toDouble();
      int maxData = 0;
      for (final row in rows) {
        if (ci < row.length) {
          final len = row[ci]?.toString().length ?? 0;
          if (len > maxData) maxData = len;
        }
      }
      final d = maxData.toDouble();
      final softMin = (hLen * 0.5).clamp(8.0, 15.0);
      final effective = d > softMin ? d : softMin;
      sheet.getRangeByIndex(1, col).columnWidth = (effective * 1.1 + 2.0).clamp(
        8.0,
        55.0,
      );
    }
  }

  // Create an Excel native Table with Medium2 style
  static void createTable(
    xl.Worksheet sheet,
    int lastRow,
    int lastCol,
    String name,
  ) {
    if (lastRow < 2 || lastCol < 1) return;
    final range = sheet.getRangeByIndex(1, 1, lastRow, lastCol);
    final table = sheet.tableCollection.create(name, range);
    table.builtInTableStyle = xl.ExcelTableBuiltInStyle.tableStyleMedium2;
    table.showBandedRows = true;
    table.showFirstColumn = false;
    table.showLastColumn = false;
  }

  /// Export template with sample data from the DataGridSource.
  /// [columnIndices] maps each template header to the column index in the source.
  static Future<void> exportTemplate({
    required List<String> headers,
    required String type,
    DataGridSource? source,
    List<int>? columnIndices,
    int sampleRows = 10,
  }) async {
    try {
      final workbook = xl.Workbook();
      final sheet = workbook.worksheets[0];
      sheet.name = type;

      // Header row
      for (int c = 0; c < headers.length; c++) {
        sheet.getRangeByIndex(1, c + 1).setText(headers[c]);
      }

      // Sample data rows
      final srcRows = source?.rows ?? [];
      final count = srcRows.length < sampleRows ? srcRows.length : sampleRows;
      final dataForWidth = <List<dynamic>>[];

      for (int r = 0; r < count; r++) {
        final cells = srcRows[r].getCells();
        final rowData = <dynamic>[];
        if (columnIndices != null) {
          for (final idx in columnIndices) {
            rowData.add(idx < cells.length ? cells[idx].value : '');
          }
        } else {
          for (int c = 0; c < headers.length && c < cells.length; c++) {
            rowData.add(cells[c].value);
          }
        }
        for (int c = 0; c < rowData.length; c++) {
          _setCellValue(sheet.getRangeByIndex(r + 2, c + 1), rowData[c]);
        }
        dataForWidth.add(rowData);
      }

      final lastRow = count + 1;
      createTable(
        sheet,
        lastRow < 2 ? 2 : lastRow,
        headers.length,
        '${type}_Template',
      );
      _applyColumnWidths(sheet, headers, dataForWidth);

      await saveAndOpenWorkbook(workbook, exportFileName('${type}_Template'));
    } catch (e) {
      showToast('Export error: $e');
    }
  }

  /// Export a DataGridSource to an Excel file.
  /// [headers] must match the column order in the DataGridSource rows.
  static Future<void> exportGridToExcel({
    required DataGridSource source,
    required List<String> headers,
    required String type,
  }) async {
    try {
      final workbook = xl.Workbook();
      final sheet = workbook.worksheets[0];
      sheet.name = type;

      // Header row
      for (int c = 0; c < headers.length; c++) {
        sheet.getRangeByIndex(1, c + 1).setText(headers[c]);
      }

      // Data rows
      final rows = source.rows;
      final dataForWidth = <List<dynamic>>[];
      for (int r = 0; r < rows.length; r++) {
        final cells = rows[r].getCells();
        final rowData = cells.map((c) => c.value).toList();
        for (int c = 0; c < cells.length; c++) {
          _setCellValue(sheet.getRangeByIndex(r + 2, c + 1), cells[c].value);
        }
        dataForWidth.add(rowData);
      }

      createTable(sheet, rows.length + 1, headers.length, type);
      _applyColumnWidths(sheet, headers, dataForWidth);
      await saveAndOpenWorkbook(workbook, exportFileName(type));
    } catch (e) {
      showToast('Export error: $e');
    }
  }

  // ─── helpers ──────────────────────────────────────────────────────────────

  // xlsio is write-only; reading is done via the excel package (separate import flow).
  // _cell and _pickAndDecodeExcel are intentionally removed; import functions
  // use file_picker + the excel package separately where needed.

  static DateTime? _parseDate(String s) {
    if (s.isEmpty) return null;
    // Excel serial date number (e.g. 45808)
    final asNum = double.tryParse(s);
    if (asNum != null && asNum > 25569) {
      // Excel epoch: 1900-01-01 with the bug offset
      final days = asNum.toInt() - 25569;
      return DateTime.utc(1970, 1, 1).add(Duration(days: days));
    }
    // Try multiple date formats
    for (final fmt in [
      DateFormat('yyyy-MM-dd'),
      DateFormat('dd/MM/yyyy'),
      DateFormat('MM/dd/yyyy'),
      DateFormat('yyyy/MM/dd'),
      DateFormat('dd-MM-yyyy'),
    ]) {
      try {
        return fmt.parseStrict(s);
      } catch (_) {}
    }
    try {
      return DateTime.parse(s);
    } catch (_) {
      return null;
    }
  }

  static DateTime? _parseDateTime(String s) {
    if (s.isEmpty) return null;
    try {
      return DateFormat('yyyy-MM-dd HH:mm').parseStrict(s);
    } catch (_) {
      try {
        return DateTime.parse(s);
      } catch (_) {
        return null;
      }
    }
  }

  // ─── pick xlsx bytes ──────────────────────────────────────────────────────
  static Future<Uint8List?> _pickXlsxBytes() async {
    final result = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['xlsx'],
      withData: true,
    );
    return result?.files.single.bytes;
  }

  // ─── minimal xlsx reader (archive pkg — compatible with xlsio's archive ^4) ──
  // Returns a 0-indexed [row][col] string grid; row 0 = header.
  static List<List<String>> _readXlsx(Uint8List bytes) {
    final archive = ZipDecoder().decodeBytes(bytes);

    // Shared strings table
    final ss = <String>[];
    final ssEntry = archive.findFile('xl/sharedStrings.xml');
    if (ssEntry != null) {
      final xml = utf8.decode(ssEntry.content as List<int>);
      for (final m in RegExp(r'<si>([\s\S]*?)</si>').allMatches(xml)) {
        final t =
            RegExp(
              r'<t[^>]*>([\s\S]*?)</t>',
            ).firstMatch(m.group(1)!)?.group(1) ??
            '';
        ss.add(_unescXml(t));
      }
    }

    // Worksheet (first sheet)
    final sheetEntry = archive.findFile('xl/worksheets/sheet1.xml');
    if (sheetEntry == null) return [];
    final xml = utf8.decode(sheetEntry.content as List<int>);

    final result = <List<String>>[];
    for (final rowM in RegExp(
      r'<row\b[^>]*\br="(\d+)"[^>]*>([\s\S]*?)</row>',
    ).allMatches(xml)) {
      final rowIdx = int.parse(rowM.group(1)!) - 1;
      while (result.length <= rowIdx) result.add([]);
      final rowXml = rowM.group(2)!;

      for (final cM in RegExp(
        r'<c\b r="([A-Z]+)\d+"([^>]*)>([\s\S]*?)</c>',
      ).allMatches(rowXml)) {
        final colIdx = _xlColIdx(cM.group(1)!) - 1;
        final attrs = cM.group(2)!;
        final inner = cM.group(3)!;
        while (result[rowIdx].length <= colIdx) result[rowIdx].add('');

        final type = RegExp(r'\bt="([^"]*)"').firstMatch(attrs)?.group(1) ?? '';
        final vText =
            RegExp(r'<v>([\s\S]*?)</v>').firstMatch(inner)?.group(1) ?? '';

        String value;
        if (type == 's') {
          final idx = int.tryParse(vText) ?? 0;
          value = idx < ss.length ? ss[idx] : '';
        } else if (type == 'inlineStr' || type == 'str') {
          value = _unescXml(
            RegExp(r'<t[^>]*>([\s\S]*?)</t>').firstMatch(inner)?.group(1) ??
                vText,
          );
        } else {
          value = vText; // number / date serial / empty
        }
        result[rowIdx][colIdx] = value;
      }
    }
    return result;
  }

  static int _xlColIdx(String col) {
    int r = 0;
    for (final c in col.codeUnits) r = r * 26 + (c - 64);
    return r;
  }

  /// Convert Excel time serial (e.g. "0.5" = 12:00) to "HH:mm".
  /// If the value already contains ":" it is returned as-is.
  static String _xlTimeToHhmm(String v) {
    if (v.contains(':')) return v;
    final d = double.tryParse(v);
    if (d == null || d < 0 || d >= 1) return v;
    final totalMin = (d * 24 * 60).round();
    final h = totalMin ~/ 60;
    final m = totalMin % 60;
    return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}';
  }

  static String _unescXml(String s) => s
      .replaceAll('&amp;', '&')
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll('&quot;', '"')
      .replaceAll('&apos;', "'");

  static Employee _findEmployee(String empId) {
    return App.gValue.employees.firstWhere(
      (e) => e.empId == empId,
      orElse: () => Employee(empId: empId),
    );
  }

  // ─── attLog import ────────────────────────────────────────────────────────
  // Template columns: Finger ID | Employee ID | Timestamp | Machine No
  static Future<List<AttLog>?> importAttLogs() async {
    final bytes = await _pickXlsxBytes();
    if (bytes == null) return null;
    List<List<String>> xlRows;
    try {
      xlRows = _readXlsx(bytes);
    } catch (e) {
      showToast('Cannot read file: $e');
      return null;
    }
    final logs = <AttLog>[];
    final skipped = <String>[];
    for (int r = 1; r < xlRows.length; r++) {
      final row = xlRows[r];
      String at(int c) => c < row.length ? row[c].trim() : '';
      final fingerId = int.tryParse(at(0)) ?? 0;
      final empId = at(1);
      final tsStr = at(2);
      final machineNo = int.tryParse(at(3)) ?? 0;
      if (empId.isEmpty && tsStr.isEmpty) continue;
      if (empId.isEmpty) {
        skipped.add('Row ${r + 1}: missing Employee ID');
        continue;
      }
      if (tsStr.isEmpty) {
        skipped.add('Row ${r + 1}: missing Timestamp');
        continue;
      }
      final ts = _parseDateTime(tsStr);
      if (ts == null) {
        skipped.add('Row ${r + 1}: invalid Timestamp "$tsStr"');
        continue;
      }
      final emp = _findEmployee(empId);
      logs.add(
        AttLog(
          objectId: '',
          attFingerId: fingerId,
          empId: empId,
          name: emp.name ?? empId,
          timestamp: ts,
          machineNo: machineNo,
        ),
      );
    }
    if (logs.isEmpty) {
      showToast(
        'No valid rows found${skipped.isNotEmpty ? '\n${skipped.join('\n')}' : ''}',
        duration: const Duration(seconds: 5),
      );
      return [];
    }
    if (skipped.isNotEmpty) {
      showToast(
        'Skipped ${skipped.length} row(s):\n${skipped.join('\n')}',
        duration: const Duration(seconds: 5),
      );
    }
    return logs;
  }

  // ─── overtime import ──────────────────────────────────────────────────────
  // Template columns: OT Date | Begin | End | Emp ID
  static Future<List<OtRegister>?> importOtRegisters() async {
    final bytes = await _pickXlsxBytes();
    if (bytes == null) return null;
    List<List<String>> xlRows;
    try {
      xlRows = _readXlsx(bytes);
    } catch (e) {
      showToast('Cannot read file: $e');
      return null;
    }
    final ots = <OtRegister>[];
    final skipped = <String>[];
    final baseId = DateTime.now().millisecondsSinceEpoch;
    final now = DateTime.now();
    final nowStr = DateFormat('yyyyMMddHHmm').format(now);
    for (int r = 1; r < xlRows.length; r++) {
      final row = xlRows[r];
      String at(int c) => c < row.length ? row[c].trim() : '';
      final otDateStr = at(0);
      final otTimeBegin = _xlTimeToHhmm(at(1));
      final otTimeEnd = _xlTimeToHhmm(at(2));
      final empId = at(3);
      if (empId.isEmpty && otDateStr.isEmpty) continue;
      if (empId.isEmpty) {
        skipped.add('Row ${r + 1}: missing Emp ID');
        continue;
      }
      if (otDateStr.isEmpty) {
        skipped.add('Row ${r + 1}: missing OT Date');
        continue;
      }
      final otDate = _parseDate(otDateStr);
      if (otDate == null) {
        skipped.add('Row ${r + 1}: invalid date "$otDateStr"');
        continue;
      }
      final emp = _findEmployee(empId);
      final empSuffix = empId.length > 5 ? empId.substring(5) : empId;
      ots.add(
        OtRegister(
          id: baseId + r,
          requestNo: '${nowStr}_$empSuffix',
          requestDate: now,
          otDate: otDate,
          otTimeBegin: otTimeBegin,
          otTimeEnd: otTimeEnd,
          empId: empId,
          name: emp.name ?? empId,
        ),
      );
    }
    if (ots.isEmpty) {
      showToast(
        'No valid rows found${skipped.isNotEmpty ? '\n${skipped.join('\n')}' : ''}',
        duration: const Duration(seconds: 5),
      );
      return [];
    }
    if (skipped.isNotEmpty) {
      showToast(
        'Skipped ${skipped.length} row(s):\n${skipped.join('\n')}',
        duration: const Duration(seconds: 5),
      );
    }
    return ots;
  }

  // ─── shift import ─────────────────────────────────────────────────────────
  // Template columns: From Date | To Date | Shift | Emp ID
  static Future<List<ShiftRegister>?> importShiftRegisters() async {
    final bytes = await _pickXlsxBytes();
    if (bytes == null) return null;
    List<List<String>> xlRows;
    try {
      xlRows = _readXlsx(bytes);
    } catch (e) {
      showToast('Cannot read file: $e');
      return null;
    }
    final srs = <ShiftRegister>[];
    final skipped = <String>[];
    for (int r = 1; r < xlRows.length; r++) {
      final row = xlRows[r];
      String at(int c) => c < row.length ? row[c].trim() : '';
      final fromDateStr = at(0);
      final toDateStr = at(1);
      final shift = at(2);
      final empId = at(3);
      if (empId.isEmpty && fromDateStr.isEmpty) continue;
      if (empId.isEmpty) {
        skipped.add('Row ${r + 1}: missing Emp ID');
        continue;
      }
      if (fromDateStr.isEmpty) {
        skipped.add('Row ${r + 1}: missing From Date');
        continue;
      }
      final fromDate = _parseDate(fromDateStr);
      if (fromDate == null) {
        skipped.add('Row ${r + 1}: invalid From Date "$fromDateStr"');
        continue;
      }
      final toDate = _parseDate(toDateStr);
      if (toDate == null) {
        skipped.add('Row ${r + 1}: invalid To Date "$toDateStr"');
        continue;
      }
      final emp = _findEmployee(empId);
      srs.add(
        ShiftRegister(
          objectId: '',
          empId: empId,
          name: emp.name ?? empId,
          fromDate: fromDate,
          toDate: toDate,
          shift: shift,
        ),
      );
    }
    if (srs.isEmpty) {
      showToast(
        'No valid rows found${skipped.isNotEmpty ? '\n${skipped.join('\n')}' : ''}',
        duration: const Duration(seconds: 5),
      );
      return [];
    }
    if (skipped.isNotEmpty) {
      showToast(
        'Skipped ${skipped.length} row(s):\n${skipped.join('\n')}',
        duration: const Duration(seconds: 5),
      );
    }
    return srs;
  }
}

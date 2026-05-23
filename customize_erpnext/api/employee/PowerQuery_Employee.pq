// ============================================================
// Power Query M – Employee List from ERPNext
// ============================================================
let
    // ╔══════════════════════════════════════════════════════╗
    // ║                    CONFIGURATION                    ║
    // ╚══════════════════════════════════════════════════════╝
    // Thử lần lượt theo thứ tự ưu tiên:
    //   Nếu có reverse-proxy (port 443):  "https://erp.tiqn.com.vn:8888"
    //   Nếu truy cập nội bộ (port 8888):  "https://erp.tiqn.local:8888"
    //   Hoặc dùng IP trực tiếp:           "https://10.0.1.20:8888"
    BaseUrl = "https://erp.tiqn.com.vn:8888",
    ApiMethod = "/api/method/customize_erpnext.api.employee.employee_utils.get_employees_for_excel",

    // true  → load ALL records in 1 request (recommended)
    // false → paginate by PageSize below
    LoadAll  = true,
    PageSize = if LoadAll then 0 else 500,   // 0 = no limit; max 2000 when paginating
    // ── LANGUAGE ─────────────────────────────────────────────
    // "en"  → English labels  (Employee ID, Full Name, …)
    // "vi"  → Vietnamese labels (Mã NV, Họ và tên, …)
    Lang = "en",
    // ── FIELD SET ────────────────────────────────────────────
    // "all"   → 106 fields
    // "basic" → 14 fields: Employee ID, Attendance Device ID,
    //           Full Name, Status, Gender, Grade, Date of Birth,
    //           Date of Joining, Department, Section, Group,
    //           Designation, Relieving Date, Reason for Leaving
    FieldSet = "all",
    // ── FILTERS (null = no filter) ────────────────────────────
    FilterStatus = null,
    // "Active" | "Left" | "Inactive" | null
    FilterDepartment = null,
    FilterSection = null,
    FilterGroup = null,
    FilterDojFrom = null,
    // "YYYY-MM-DD"
    FilterDojTo = null,
    IncludeLeft = "1",
    // "1" = include resigned employees
    // ─────────────────────────────────────────────────────────
    // ╔══════════════════════════════════════════════════════╗
    // ║               INTERNAL FUNCTIONS                    ║
    // ╚══════════════════════════════════════════════════════╝
    // Build query string, skip null params
    BuildQS = (params as record) as text =>
        let
            keys = List.Select(Record.FieldNames(params), each Record.Field(params, _) <> null),
            pairs = List.Transform(keys, each _ & "=" & Uri.EscapeDataString(Text.From(Record.Field(params, _))))
        in
            Text.Combine(pairs, "&"),
    // Fetch one page — Binary.Buffer fixes the Formula Firewall
    // "references other queries or steps" error
    FetchPage = (pageNum as number) as record =>
        let
            qs = BuildQS(
                [
                    status = FilterStatus,
                    department = FilterDepartment,
                    custom_section = FilterSection,
                    custom_group = FilterGroup,
                    date_of_joining_from = FilterDojFrom,
                    date_of_joining_to = FilterDojTo,
                    include_left = IncludeLeft,
                    lang = Lang,
                    field_set = FieldSet,
                    page = Text.From(pageNum),
                    page_size = Text.From(PageSize)
                ]
            ),
            url = BaseUrl & ApiMethod & "?" & qs,
            // Binary.Buffer → caches response in memory,
            // prevents Power Query Formula Firewall from blocking
            // cross-step data source references
            raw = Binary.Buffer(Web.Contents(url, [
                Headers = [#"Accept" = "application/json"]
            ])),
            parsed = Json.Document(raw)
        in
            parsed[message],
    // ╔══════════════════════════════════════════════════════╗
    // ║                  FETCH DATA                         ║
    // ╚══════════════════════════════════════════════════════╝
    Page1      = FetchPage(1),
    TotalPages = Page1[total_pages],
    ColKeys    = Page1[col_keys],
    ColLabels  = Page1[columns],

    // When LoadAll=true, TotalPages=1 → single request, no loop needed
    AllPageData = List.Transform(
        List.Numbers(1, TotalPages),
        each if _ = 1 then Page1[data] else FetchPage(_)[data]
    ),
    AllRecords = List.Combine(AllPageData),
    // ╔══════════════════════════════════════════════════════╗
    // ║               BUILD TABLE                           ║
    // ╚══════════════════════════════════════════════════════╝
    RawTable = Table.FromList(AllRecords, Splitter.SplitByNothing(), {"_row"}, null, ExtraValues.Error),
    Expanded = Table.ExpandRecordColumn(RawTable, "_row", ColKeys, ColKeys),
    Renamed = Table.RenameColumns(Expanded, List.Zip({ColKeys, ColLabels})),
    // ╔══════════════════════════════════════════════════════╗
    // ║               TYPE CONVERSIONS                      ║
    // ╚══════════════════════════════════════════════════════╝
    DateCols_EN = {
        "Date of Birth",
        "Date of Joining",
        "Offer Date",
        "Confirmation Date",
        "Contract End Date",
        "Date of Retirement",
        "ID Card Date of Issue",
        "Old ID Card Date of Issue",
        "Passport Date of Issue",
        "Passport Valid Up To",
        "Resignation Letter Date",
        "Relieving Date",
        "Encashment Date",
        "Exit Interview Held On"
    },
    DateCols_VI = {
        "Ngày sinh",
        "Ngày vào làm",
        "Ngày offer",
        "Ngày xác nhận",
        "Ngày kết thúc HĐ",
        "Ngày nghỉ hưu",
        "Ngày cấp CCCD",
        "Ngày cấp CMND",
        "Ngày cấp HC",
        "Ngày hết hạn HC",
        "Ngày nộp đơn",
        "Ngày nghỉ việc",
        "Ngày thanh toán phép",
        "Ngày phỏng vấn thôi việc"
    },
    DateCols = if Lang = "vi" then DateCols_VI else DateCols_EN,
    ActiveDates = List.Intersect({Table.ColumnNames(Renamed), DateCols}),
    WithDates = Table.TransformColumnTypes(Renamed, List.Transform(ActiveDates, each {_, type date})),
    IntCols_EN = {"Number of Children", "Notice (Days)"},
    IntCols_VI = {"Số con", "Số ngày báo trước"},
    IntCols = if Lang = "vi" then IntCols_VI else IntCols_EN,
    ActiveInts = List.Intersect({Table.ColumnNames(WithDates), IntCols}),
    WithInts = Table.TransformColumnTypes(WithDates, List.Transform(ActiveInts, each {_, Int64.Type})),
    FinalTable = Table.ReplaceValue(WithInts, "", null, Replacer.ReplaceValue, Table.ColumnNames(WithInts))
in
    FinalTable

// ============================================================
// Power Query M – Employee List from ERPNext
// ============================================================
// Columns / labels / order are driven entirely by the Employee
// DocType (minus public/js/hide_export_fields.json), so this
// query never needs editing when a field is added or removed.
// The first 13 columns are always pinned in this order:
//   Employee, Att ID, Full Name, Status, Gender, Department,
//   Section, Group, Designation, Grade, Date of Joining,
//   Date of Birth, Relieving Date.
// Only employees whose ID starts with "TIQN" are returned
// (Intern-* / Test-* records are excluded server-side).
//
// AUTHENTICATION (required – the API is no longer allow_guest)
//   1. ERPNext → User → <api user> → API Access → Generate Keys
//   2. Paste key + secret below.
//   3. Data → Get Data → Web → paste any URL → set the connection
//      to "Anonymous" (the token is sent via the Headers below).
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

    // ── API KEY / SECRET ─────────────────────────────────────
    ApiKey    = "PASTE_API_KEY_HERE",
    ApiSecret = "PASTE_API_SECRET_HERE",
    AuthHeader = "token " & ApiKey & ":" & ApiSecret,

    // true  → load ALL records in 1 request (recommended)
    // false → paginate by PageSize below
    LoadAll  = true,
    PageSize = if LoadAll then 0 else 5000,  // 0 = no limit; max 20000 when paginating

    // ── FILTERS (null = no filter) ────────────────────────────
    FilterStatus = null,
    // "Active" | "Left" | null (= all)
    FilterDepartment = null,
    // "Production" hoặc "Production - TIQN", cả hai đều được
    FilterSection = null,
    FilterGroup = null,
    FilterDojFrom = null,
    // "YYYY-MM-DD"
    FilterDojTo = null,

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
                    page = Text.From(pageNum),
                    page_size = Text.From(PageSize)
                ]
            ),
            url = BaseUrl & ApiMethod & "?" & qs,
            // Binary.Buffer → caches response in memory,
            // prevents Power Query Formula Firewall from blocking
            // cross-step data source references
            raw = Binary.Buffer(Web.Contents(url, [
                Headers = [
                    #"Accept" = "application/json",
                    #"Authorization" = AuthHeader
                ]
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
    ColTypes   = Page1[col_types],

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
    // Expand straight to the DocType labels (col_keys -> columns), so there is
    // no separate rename step that could collide with an existing column name.
    Renamed = Table.ExpandRecordColumn(RawTable, "_row", ColKeys, ColLabels),

    // ╔══════════════════════════════════════════════════════╗
    // ║               TYPE CONVERSIONS                      ║
    // ╚══════════════════════════════════════════════════════╝
    // Empty string → null FIRST, otherwise "" breaks date/number casts
    Blanked = Table.ReplaceValue(Renamed, "", null, Replacer.ReplaceValue, Table.ColumnNames(Renamed)),

    // col_types comes from the API (derived from the DocType fieldtype),
    // so no hard-coded column-name lists to maintain here.
    MapType = (t as text) as type =>
        if t = "Date" then type date
        else if t = "Datetime" then type datetime
        else if t = "Time" then type time
        else if t = "Int" then Int64.Type
        else if t = "Float" then type number
        else type text,
    Transforms = List.Transform(
        List.Zip({ColLabels, ColTypes}),
        each {_{0}, MapType(_{1})}
    ),
    FinalTable = Table.TransformColumnTypes(Blanked, Transforms)
in
    FinalTable

// ============================================================
// Power Query M – Employee Maternity List from ERPNext
//
// AUTHENTICATION (bắt buộc — API không có allow_guest)
//   1. ERPNext → User → <api user> → API Access → Generate Keys
//   2. Dán key + secret vào ApiKey / ApiSecret bên dưới.
//   3. Data → Get Data → Web → dán URL bất kỳ → đặt connection là
//      "Anonymous" (token đi theo Headers, không qua lớp auth của Power Query).
// ============================================================
let
    // ╔══════════════════════════════════════════════════════╗
    // ║                    CONFIGURATION                    ║
    // ╚══════════════════════════════════════════════════════╝
    BaseUrl = "https://erp.tiqn.com.vn:8888",
    ApiMethod = "/api/method/customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity.get_employee_maternity_for_excel",
    // ── API KEY / SECRET ─────────────────────────────────────
    // 🔴 BẮT BUỘC. `get_employee_maternity_for_excel` KHÔNG có `allow_guest` (dữ liệu
    // thai sản là dữ liệu sức khoẻ, không mở cho khách). Thiếu header này thì Web.Contents
    // trả 403 và Power Query báo lỗi khó hiểu, không phải "thiếu quyền".
    ApiKey = "PASTE_API_KEY_HERE",
    ApiSecret = "PASTE_API_SECRET_HERE",
    AuthHeader = "token " & ApiKey & ":" & ApiSecret,
    // true  → load ALL records in 1 request (recommended)
    // false → paginate by PageSize below
    LoadAll = true,
    PageSize = if LoadAll then 0 else 500,
    // 0 = no limit
    // ── LANGUAGE ─────────────────────────────────────────────
    // "en"  → English labels
    // "vi"  → Vietnamese labels
    Lang = "vi",
    // ── FILTERS (null = no filter) ────────────────────────────
    FilterEmployee = null,
    // Employee ID, e.g. "HR-EMP-00001"
    FilterStatus = null,
    // "Pregnant" | "Maternity Leave" | "Young Child" | null
    FilterGroup = null,
    // Group name, e.g. "Stitching"
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
    FetchPage = (pageNum as number) as record =>
        let
            qs = BuildQS(
                [
                    employee = FilterEmployee,
                    status = FilterStatus,
                    group = FilterGroup,
                    lang = Lang,
                    page = Text.From(pageNum),
                    page_size = Text.From(PageSize)
                ]
            ),
            url = BaseUrl & ApiMethod & "?" & qs,
            // Binary.Buffer → cache response trong bộ nhớ, tránh Formula Firewall của
            // Power Query chặn tham chiếu nguồn dữ liệu giữa các bước
            raw = Binary.Buffer(
                Web.Contents(url, [
                    Headers = [
                        #"Accept" = "application/json",
                        #"Authorization" = AuthHeader
                    ]
                ])
            ),
            parsed = Json.Document(raw)
        in
            parsed[message],
    // ╔══════════════════════════════════════════════════════╗
    // ║                  FETCH DATA                         ║
    // ╚══════════════════════════════════════════════════════╝
    Page1 = FetchPage(1),
    TotalPages = Page1[total_pages],
    ColKeys = Page1[col_keys],
    ColLabels = Page1[columns],
    AllPageData = List.Transform(List.Numbers(1, TotalPages), each if _ = 1 then Page1[data] else FetchPage(_)[data]),
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
    // 🔴 PHẢI đổi "" -> null TRƯỚC mọi Table.TransformColumnTypes.
    // API trả chuỗi rỗng cho ô không có giá trị, mà ép "" sang `type date` / `type
    // number` trong M sinh ô **Error**, không phải null — và bước ReplaceValue chạy
    // sau thì không sửa được Error nữa.
    // Trước 04/09/2026 hầu hết dòng đều có "Tuổi thai" nên lỗi này không lộ; từ khi
    // tuổi thai chỉ tính cho giai đoạn Pregnant thì 217/255 dòng là rỗng.
    Blanked = Table.ReplaceValue(Renamed, "", null, Replacer.ReplaceValue, Table.ColumnNames(Renamed)),
    DateCols_EN = {
        "Date of Joining",
        "Pregnant From",
        "Pregnant To",
        "Estimated Due Date",
        "Maternity Leave From",
        "Maternity Leave To",
        "Date of Birth (Child)",
        "Young Child From",
        "Young Child To"
    },
    // Nhãn phải khớp TỪNG KÝ TỰ với `_MATERNITY_LABELS_VI` trong employee_maternity.py —
    // List.Intersect so khớp chuỗi, lệch một dấu cách là cột đó lặng lẽ KHÔNG được ép kiểu.
    DateCols_VI = {
        "Ngày vào làm",
        "Ngày BĐ chế độ mang thai",
        "Ngày KT chế độ mang thai",
        "Ngày dự sinh",
        "Ngày BĐ nghỉ thai sản",
        "Ngày KT nghỉ thai sản",
        "Ngày sinh (con)",
        "Ngày BĐ chế độ con nhỏ",
        "Ngày KT chế độ con nhỏ"
    },
    DateCols = if Lang = "vi" then DateCols_VI else DateCols_EN,
    ActiveDates = List.Intersect({Table.ColumnNames(Blanked), DateCols}),
    WithDates = Table.TransformColumnTypes(Blanked, List.Transform(ActiveDates, each {_, type date})),
    FloatCols_EN = {"Gestational Age (months)"},
    FloatCols_VI = {"Tuổi thai (tháng)"},
    FloatCols = if Lang = "vi" then FloatCols_VI else FloatCols_EN,
    ActiveFloats = List.Intersect({Table.ColumnNames(WithDates), FloatCols}),
    WithFloats = Table.TransformColumnTypes(WithDates, List.Transform(ActiveFloats, each {_, type number})),
    IntCols_EN = {"Seniority (months)", "Apply Hour Reduction"},
    IntCols_VI = {"Thâm niên (tháng)", "Áp dụng giảm 1h"},
    IntCols = if Lang = "vi" then IntCols_VI else IntCols_EN,
    ActiveInts = List.Intersect({Table.ColumnNames(WithFloats), IntCols}),
    WithInts = Table.TransformColumnTypes(WithFloats, List.Transform(ActiveInts, each {_, Int64.Type})),
    // Không cần ReplaceValue lần nữa ở đây — đã làm ở `Blanked` phía trên.
    FinalTable = WithInts
in
    FinalTable

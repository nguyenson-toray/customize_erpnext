// ============================================================
// Power Query M – Employee Maternity List from ERPNext
// ============================================================
let
    // ╔══════════════════════════════════════════════════════╗
    // ║                    CONFIGURATION                    ║
    // ╚══════════════════════════════════════════════════════╝
    BaseUrl   = "https://erp.tiqn.com.vn:8888",
    ApiMethod = "/api/method/customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity.get_employee_maternity_for_excel",

    // true  → load ALL records in 1 request (recommended)
    // false → paginate by PageSize below
    LoadAll  = true,
    PageSize = if LoadAll then 0 else 500,   // 0 = no limit

    // ── LANGUAGE ─────────────────────────────────────────────
    // "en"  → English labels
    // "vi"  → Vietnamese labels
    Lang = "vi",

    // ── FILTERS (null = no filter) ────────────────────────────
    FilterEmployee = null,
    // Employee ID, e.g. "HR-EMP-00001"
    FilterStatus   = null,
    // "Pregnant" | "Maternity Leave" | "Young Child" | null
    FilterGroup    = null,
    // Group name, e.g. "Stitching"

    // ─────────────────────────────────────────────────────────
    // ╔══════════════════════════════════════════════════════╗
    // ║               INTERNAL FUNCTIONS                    ║
    // ╚══════════════════════════════════════════════════════╝
    // Build query string, skip null params
    BuildQS = (params as record) as text =>
        let
            keys  = List.Select(Record.FieldNames(params), each Record.Field(params, _) <> null),
            pairs = List.Transform(keys, each _ & "=" & Uri.EscapeDataString(Text.From(Record.Field(params, _))))
        in
            Text.Combine(pairs, "&"),

    // Fetch one page — Binary.Buffer fixes the Formula Firewall
    FetchPage = (pageNum as number) as record =>
        let
            qs = BuildQS([
                employee  = FilterEmployee,
                status    = FilterStatus,
                group     = FilterGroup,
                lang      = Lang,
                page      = Text.From(pageNum),
                page_size = Text.From(PageSize)
            ]),
            url = BaseUrl & ApiMethod & "?" & qs,
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
    Renamed  = Table.RenameColumns(Expanded, List.Zip({ColKeys, ColLabels})),

    // ╔══════════════════════════════════════════════════════╗
    // ║               TYPE CONVERSIONS                      ║
    // ╚══════════════════════════════════════════════════════╝
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
    DateCols_VI = {
        "Ngày vào làm",
        "Ngày bắt đầu thai kỳ",
        "Ngày kết thúc thai kỳ",
        "Ngày dự sinh",
        "Ngày bắt đầu nghỉ thai sản",
        "Ngày kết thúc nghỉ thai sản",
        "Ngày sinh (con)",
        "Ngày bắt đầu con nhỏ",
        "Ngày kết thúc con nhỏ"
    },
    DateCols    = if Lang = "vi" then DateCols_VI else DateCols_EN,
    ActiveDates = List.Intersect({Table.ColumnNames(Renamed), DateCols}),
    WithDates   = Table.TransformColumnTypes(Renamed, List.Transform(ActiveDates, each {_, type date})),

    FloatCols_EN = {"Gestational Age (months)"},
    FloatCols_VI = {"Tuổi thai (tháng)"},
    FloatCols    = if Lang = "vi" then FloatCols_VI else FloatCols_EN,
    ActiveFloats = List.Intersect({Table.ColumnNames(WithDates), FloatCols}),
    WithFloats   = Table.TransformColumnTypes(WithDates, List.Transform(ActiveFloats, each {_, type number})),

    IntCols_EN = {"Seniority (months)", "Apply Benefit"},
    IntCols_VI = {"Thâm niên (tháng)", "Áp dụng quyền lợi"},
    IntCols    = if Lang = "vi" then IntCols_VI else IntCols_EN,
    ActiveInts = List.Intersect({Table.ColumnNames(WithFloats), IntCols}),
    WithInts   = Table.TransformColumnTypes(WithFloats, List.Transform(ActiveInts, each {_, Int64.Type})),

    FinalTable = Table.ReplaceValue(WithInts, "", null, Replacer.ReplaceValue, Table.ColumnNames(WithInts))
in
    FinalTable

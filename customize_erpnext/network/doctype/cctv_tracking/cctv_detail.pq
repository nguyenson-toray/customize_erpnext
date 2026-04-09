// ============================================================
// Power Query M — CCTV Detail from ERPNext
// Loads: Video Recorded Detail (camera-level per NVR scan)
// ============================================================
let
    // ╔══════════════════════════════════════════════════════╗
    // ║                   CONFIGURATION                     ║
    // ╚══════════════════════════════════════════════════════╝
    BaseUrl   = "https://erp.tiqn.com.vn:8888",
    ApiMethod = "/api/method/customize_erpnext.network.doctype.cctv_tracking.cctv_api.cctv_detail",

    // ── FILTERS (null = no filter) ────────────────────────
    // NVR name, e.g. "NVR-Insite" or "NVR-Outsite"
    FilterNVR  = null,
    // Date filter:
    //   single day  → "2026-04-09"
    //   date range  → "2026-04-01:2026-04-09"
    //   no filter   → null
    FilterDate = null,

    // ╔══════════════════════════════════════════════════════╗
    // ║              INTERNAL FUNCTIONS                     ║
    // ╚══════════════════════════════════════════════════════╝
    BuildQS = (params as record) as text =>
        let
            keys  = List.Select(Record.FieldNames(params), each Record.Field(params, _) <> null),
            pairs = List.Transform(keys, each _ & "=" & Uri.EscapeDataString(Text.From(Record.Field(params, _))))
        in
            Text.Combine(pairs, "&"),

    // ╔══════════════════════════════════════════════════════╗
    // ║                   FETCH DATA                        ║
    // ╚══════════════════════════════════════════════════════╝
    QS  = BuildQS([nvr = FilterNVR, date = FilterDate]),
    Url = BaseUrl & ApiMethod & (if QS = "" then "" else "?" & QS),
    Raw = Binary.Buffer(Web.Contents(Url, [Headers = [#"Accept" = "application/json"]])),
    Parsed  = Json.Document(Raw),
    Payload = Parsed[message],

    ColKeys   = Payload[col_keys],
    ColLabels = Payload[columns],

    // ╔══════════════════════════════════════════════════════╗
    // ║                  BUILD TABLE                        ║
    // ╚══════════════════════════════════════════════════════╝
    RawTable = Table.FromList(Payload[data], Splitter.SplitByNothing(), {"_row"}, null, ExtraValues.Error),
    Expanded = Table.ExpandRecordColumn(RawTable, "_row", ColKeys, ColKeys),
    Renamed  = Table.RenameColumns(Expanded, List.Zip({ColKeys, ColLabels})),

    // ╔══════════════════════════════════════════════════════╗
    // ║               TYPE CONVERSIONS                      ║
    // ╚══════════════════════════════════════════════════════╝
    DateTimeCols = {"Last Time Recorded", "Offline Since", "Last Modified"},
    ActiveDT     = List.Intersect({Table.ColumnNames(Renamed), DateTimeCols}),
    WithDT       = Table.TransformColumnTypes(Renamed, List.Transform(ActiveDT, each {_, type datetime})),

    IntCols    = {"Channel No.", "Priority"},
    ActiveInts = List.Intersect({Table.ColumnNames(WithDT), IntCols}),
    WithInts   = Table.TransformColumnTypes(WithDT, List.Transform(ActiveInts, each {_, Int64.Type})),

    FinalTable = Table.ReplaceValue(WithInts, "", null, Replacer.ReplaceValue, Table.ColumnNames(WithInts))
in
    FinalTable

// ============================================================
// Power Query M — Trigger CCTV Monitor from Excel
// Calls run_monitor API (no email sent)
// Refresh this query to run the monitor on demand.
// ============================================================
let
    // ╔══════════════════════════════════════════════════════╗
    // ║                   CONFIGURATION                     ║
    // ╚══════════════════════════════════════════════════════╝
    BaseUrl   = "https://erp.tiqn.com.vn:8888",
    ApiMethod = "/api/method/customize_erpnext.network.doctype.cctv_tracking.cctv_api.run_monitor",

    // NVR name to run — set to null to run ALL NVRs
    // e.g. "NVR-Insite" | "NVR-Outsite" | null
    FilterNVR = null,

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
    // ║                   CALL API                          ║
    // ╚══════════════════════════════════════════════════════╝
    QS  = BuildQS([nvr = FilterNVR]),
    Url = BaseUrl & ApiMethod & (if QS = "" then "" else "?" & QS),
    Raw = Binary.Buffer(Web.Contents(Url, [Headers = [#"Accept" = "application/json"]])),
    Parsed  = Json.Document(Raw),
    Payload = Parsed[message],

    // ╔══════════════════════════════════════════════════════╗
    // ║                 RESULTS TABLE                       ║
    // ╚══════════════════════════════════════════════════════╝
    Results    = Payload[results],
    RawTable   = Table.FromList(Results, Splitter.SplitByNothing(), {"_row"}, null, ExtraValues.Error),
    ColKeys    = {"nvr", "doc", "ok", "error"},
    Expanded   = Table.ExpandRecordColumn(RawTable, "_row", ColKeys, ColKeys),
    Renamed    = Table.RenameColumns(Expanded, {{"nvr", "NVR"}, {"doc", "Tracking Record"}, {"ok", "Success"}, {"error", "Error"}}),
    WithTypes  = Table.TransformColumnTypes(Renamed, {{"Success", type logical}}),
    FinalTable = Table.ReplaceValue(WithTypes, "", null, Replacer.ReplaceValue, Table.ColumnNames(WithTypes))
in
    FinalTable

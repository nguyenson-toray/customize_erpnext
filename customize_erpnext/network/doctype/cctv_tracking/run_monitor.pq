// ============================================================
// Power Query M — Trigger CCTV Monitor from Excel
// Calls run_monitor API (no email sent)
// Refresh this query to run the monitor on demand.
//
// AUTHENTICATION — điền ApiKey / ApiSecret ở phần CONFIGURATION bên dưới
// ============================================================
let
    // ╔══════════════════════════════════════════════════════╗
    // ║                   CONFIGURATION                     ║
    // ╚══════════════════════════════════════════════════════╝
    BaseUrl   = "https://erp.tiqn.com.vn:8888",
    ApiMethod = "/api/method/customize_erpnext.network.doctype.cctv_tracking.cctv_api.run_monitor",
    // ── API KEY / SECRET ─────────────────────────────────────
    // ERPNext → User → <api user> → API Access → Generate Keys, rồi dán vào đây.
    // Header Authorization đi kèm MỌI request. Endpoint hiện vẫn allow_guest=True
    // nên để nguyên "PASTE_..." vẫn chạy, nhưng điền sẵn thì file Excel không phải
    // sửa lại vào ngày khoá endpoint.
    // Trong Power Query đặt connection là "Anonymous" — token đi theo Headers, KHÔNG
    // qua lớp auth của Power Query.
    ApiKey     = "PASTE_API_KEY_HERE",
    ApiSecret  = "PASTE_API_SECRET_HERE",
    AuthHeader = "token " & ApiKey & ":" & ApiSecret,

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
    // Binary.Buffer → cache response trong bộ nhớ, tránh Formula Firewall của
    // Power Query chặn tham chiếu nguồn dữ liệu giữa các bước
    Raw = Binary.Buffer(
        Web.Contents(Url, [
            Headers = [
                #"Accept"        = "application/json",
                #"Authorization" = AuthHeader
            ]
        ])
    ),
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
    // "" -> null TRƯỚC khi ép kiểu (xem ghi chú ở cctv_detail.pq)
    Blanked    = Table.ReplaceValue(Renamed, "", null, Replacer.ReplaceValue, Table.ColumnNames(Renamed)),
    FinalTable = Table.TransformColumnTypes(Blanked, {{"Success", type logical}})
in
    FinalTable

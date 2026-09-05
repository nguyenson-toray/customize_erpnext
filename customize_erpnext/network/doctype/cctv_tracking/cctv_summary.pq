// ============================================================
// Power Query M — CCTV Summary from ERPNext
// Loads: CCTV Tracking (NVR-level summary per scan)
//
// AUTHENTICATION — điền ApiKey / ApiSecret ở phần CONFIGURATION bên dưới
// ============================================================
let
    // ╔══════════════════════════════════════════════════════╗
    // ║                   CONFIGURATION                     ║
    // ╚══════════════════════════════════════════════════════╝
    BaseUrl   = "https://erp.tiqn.com.vn:8888",
    ApiMethod = "/api/method/customize_erpnext.network.doctype.cctv_tracking.cctv_api.cctv_summary",
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
    // 🔴 PHẢI đổi "" -> null TRƯỚC mọi Table.TransformColumnTypes: API trả chuỗi rỗng
    // cho ô trống, ép "" sang `type datetime`/`type number` sinh ô **Error** chứ không
    // phải null, và ReplaceValue chạy sau thì không sửa được Error nữa.
    // (VD: "Offline Since" rỗng với mọi camera Online, "Gap Info" rỗng khi không có gap.)
    Blanked = Table.ReplaceValue(Renamed, "", null, Replacer.ReplaceValue, Table.ColumnNames(Renamed)),

    DateCols    = {"Date"},
    ActiveDates = List.Intersect({Table.ColumnNames(Blanked), DateCols}),
    WithDates   = Table.TransformColumnTypes(Blanked, List.Transform(ActiveDates, each {_, type date})),

    DateTimeCols = {"Online Since"},
    ActiveDT     = List.Intersect({Table.ColumnNames(WithDates), DateTimeCols}),
    WithDT       = Table.TransformColumnTypes(WithDates, List.Transform(ActiveDT, each {_, type datetime})),

    IntCols    = {"Total Cameras", "Online Cameras", "Offline Cameras"},
    ActiveInts = List.Intersect({Table.ColumnNames(WithDT), IntCols}),
    WithInts   = Table.TransformColumnTypes(WithDT, List.Transform(ActiveInts, each {_, Int64.Type})),

    DecimalCols    = {"Shortest Storage Days"},
    ActiveDecimals = List.Intersect({Table.ColumnNames(WithInts), DecimalCols}),
    WithDecimals   = Table.TransformColumnTypes(WithInts, List.Transform(ActiveDecimals, each {_, type number})),

    // Không ReplaceValue lần nữa — đã làm ở `Blanked`
    FinalTable = WithDecimals
in
    FinalTable

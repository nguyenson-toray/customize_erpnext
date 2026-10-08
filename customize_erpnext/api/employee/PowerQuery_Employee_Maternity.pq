// ============================================================
// Power Query M – Employee Maternity List from ERPNext
//
// API: customize_erpnext.customize_erpnext.doctype.employee_maternity
//      .employee_maternity.get_employee_maternity_for_excel
// Trả về { data, columns, col_keys, total, page, page_size, total_pages }
// — 1 dòng / 1 hồ sơ thai sản (1 chu kỳ). Nhân viên có 2 con = 2 dòng.
//
// AUTHENTICATION (bắt buộc — API không có allow_guest)
//   1. ERPNext → User → <api user> → API Access → Generate Keys
//   2. Dán key + secret vào ApiKey / ApiSecret bên dưới.
//   3. Data → Get Data → Blank Query → Advanced Editor → dán code này.
//      Khi được hỏi credential: chọn "Anonymous" (token đi theo Headers).
//   4. Lỗi Formula.Firewall → File → Options → Query Options → Privacy →
//      "Ignore the Privacy Levels".
//
// CỘT TRẢ VỀ (thứ tự = col_keys của API; nhãn theo Lang)
//   ID / Mã hồ sơ · Employee ID / Mã NV · Full Name / Họ và tên · Group / Nhóm ·
//   Designation / Chức danh · Date of Joining / Ngày vào làm · Status / Trạng thái ·
//   Apply Hour Reduction / Áp dụng giảm 1h · Note / Ghi chú ·
//   Pregnant From / Ngày BĐ chế độ mang thai · Pregnant To / Ngày KT chế độ mang thai ·
//   Estimated Due Date / Ngày dự sinh ·
//   Maternity Leave From / Ngày BĐ nghỉ thai sản · Maternity Leave To / Ngày KT nghỉ thai sản ·
//   Date of Birth (Child) / Ngày sinh (con) ·
//   Young Child From / Ngày BĐ chế độ con nhỏ · Young Child To / Ngày KT chế độ con nhỏ ·
//   Gestational Age (months) / Tuổi thai (tháng) · Seniority (months) / Thâm niên (tháng) ·
//   Child Number / Con thứ mấy · Twins / Sinh đôi ·
//   Pregnancy Notified Date / Ngày nhận thông tin mang thai · Leave Months / Số tháng nghỉ thai sản
//
// Ý NGHĨA DỮ LIỆU (quy tắc hiện tại của hồ sơ)
//   • 3 giai đoạn liên tục: Maternity From = Pregnant To + 1; Young Child From = Maternity To + 1.
//   • Maternity To = Maternity From + Leave Months − 1 ngày.
//     Leave Months mặc định: 6; con thứ 2 = 7; sinh đôi +1 (con thứ 2 sinh đôi = 8).
//   • Young Child To = ngày sinh con + 364; CHƯA có ngày sinh → trống.
//   • Sẩy thai / không sinh: Maternity From … Young Child To đều trống, Ghi chú có
//     "Sẩy thai ngày dd/mm/yyyy", Trạng thái = Inactive sau ngày đó.
//   • Tuổi thai chỉ có ở hồ sơ đang "Pregnant"; các trạng thái khác để trống.
//   • Trạng thái: Pregnant | Maternity Leave | Young Child | Inactive | (trống).
// ============================================================
let
    // ╔══════════════════════════════════════════════════════╗
    // ║                    CONFIGURATION                     ║
    // ╚══════════════════════════════════════════════════════╝
    BaseUrl = "https://erp.tiqn.com.vn:8888",
    ApiMethod = "/api/method/customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity.get_employee_maternity_for_excel",
    // ── API KEY / SECRET ─────────────────────────────────────
    // 🔴 BẮT BUỘC. Dữ liệu thai sản là dữ liệu sức khoẻ, API không mở cho khách.
    // Thiếu / sai header này thì Web.Contents trả 403 và Power Query báo lỗi khó hiểu.
    ApiKey = "PASTE_API_KEY_HERE",
    ApiSecret = "PASTE_API_SECRET_HERE",
    AuthHeader = "token " & ApiKey & ":" & ApiSecret,
    // true  → tải TẤT CẢ trong 1 request (khuyến nghị)
    // false → phân trang theo PageSize (tối đa 2000)
    LoadAll = true,
    PageSize = if LoadAll then 0 else 500,
    // ── LANGUAGE ─────────────────────────────────────────────
    // "en" → nhãn cột tiếng Anh · "vi" → nhãn cột tiếng Việt
    Lang = "vi",
    // ── FILTERS (null = không lọc) ───────────────────────────
    FilterEmployee = null,
    // Mã NV, VD "TIQN-0003"
    FilterStatus = null,
    // "Pregnant" | "Maternity Leave" | "Young Child" | "Inactive" | null
    FilterGroup = null,
    // Tên nhóm, VD "Line 01"
    // ╔══════════════════════════════════════════════════════╗
    // ║                 INTERNAL FUNCTIONS                   ║
    // ╚══════════════════════════════════════════════════════╝
    // Query string, bỏ qua tham số null
    BuildQS = (params as record) as text =>
        let
            keys = List.Select(Record.FieldNames(params), each Record.Field(params, _) <> null),
            pairs = List.Transform(keys, each _ & "=" & Uri.EscapeDataString(Text.From(Record.Field(params, _))))
        in
            Text.Combine(pairs, "&"),
    // Lấy 1 trang — Binary.Buffer cache response trong bộ nhớ, tránh Formula Firewall
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
            raw = Binary.Buffer(
                Web.Contents(BaseUrl & ApiMethod & "?" & qs, [
                    Headers = [
                        #"Accept" = "application/json",
                        #"Authorization" = AuthHeader
                    ]
                ])
            )
        in
            Json.Document(raw)[message],
    // ╔══════════════════════════════════════════════════════╗
    // ║                     FETCH DATA                       ║
    // ╚══════════════════════════════════════════════════════╝
    Page1 = FetchPage(1),
    TotalPages = Page1[total_pages],
    ColKeys = Page1[col_keys],
    ColLabels = Page1[columns],
    AllRecords = List.Combine(
        List.Transform(List.Numbers(1, TotalPages), each if _ = 1 then Page1[data] else FetchPage(_)[data])
    ),
    // ╔══════════════════════════════════════════════════════╗
    // ║                    BUILD TABLE                       ║
    // ╚══════════════════════════════════════════════════════╝
    RawTable = Table.FromList(AllRecords, Splitter.SplitByNothing(), {"_row"}, null, ExtraValues.Error),
    Expanded = Table.ExpandRecordColumn(RawTable, "_row", ColKeys, ColKeys),
    // ╔══════════════════════════════════════════════════════╗
    // ║                  TYPE CONVERSIONS                    ║
    // ╚══════════════════════════════════════════════════════╝
    // Ép kiểu theo col_keys (tên field, KHÔNG đổi theo Lang) rồi mới đổi tên cột —
    // không phải giữ 2 danh sách nhãn en/vi khớp từng ký tự với API.
    //
    // 🔴 PHẢI đổi "" → null TRƯỚC mọi Table.TransformColumnTypes: API trả chuỗi rỗng cho
    // ô trống, ép "" sang date/number sinh ô Error chứ không phải null. Nhiều cột trống
    // thường xuyên: Tuổi thai (chỉ khi Pregnant), các ngày sau của hồ sơ sẩy thai,
    // Young Child To khi chưa có ngày sinh.
    Blanked = Table.ReplaceValue(Expanded, "", null, Replacer.ReplaceValue, Table.ColumnNames(Expanded)),
    DateKeys = {
        "date_of_joining",
        "pregnant_from_date",
        "pregnant_to_date",
        "estimated_due_date",
        "maternity_from_date",
        "maternity_to_date",
        "date_of_birth",
        "youg_child_from_date",
        "youg_child_to_date",
        "pregnancy_notified_date"
    },
    NumberKeys = {"gestational_age"},
    IntKeys = {"seniority", "apply_hour_reduction", "child_order", "is_twins", "leave_months"},
    TextKeys = {"name", "employee", "employee_name", "group", "designation", "status", "note"},
    Typed = Table.TransformColumnTypes(
        Blanked,
        List.Transform(List.Intersect({ColKeys, DateKeys}), each {_, type date})
            & List.Transform(List.Intersect({ColKeys, NumberKeys}), each {_, type number})
            & List.Transform(List.Intersect({ColKeys, IntKeys}), each {_, Int64.Type})
            & List.Transform(List.Intersect({ColKeys, TextKeys}), each {_, type text})
    ),
    // Con thứ mấy = 0 nghĩa là HR chưa điền → để trống cho dễ lọc trong Excel.
    // Chỉ chạy khi API có trả cột này — server chạy code cũ (chưa restart) hoặc Power Query
    // dùng response cũ trong cache thì bỏ qua thay vì báo "column wasn't found".
    ChildBlank =
        if List.Contains(ColKeys, "child_order") then
            Table.TransformColumns(Typed, {{"child_order", each if _ = 0 then null else _, Int64.Type}})
        else
            Typed,
    // ╔══════════════════════════════════════════════════════╗
    // ║                    RENAME COLUMNS                    ║
    // ╚══════════════════════════════════════════════════════╝
    FinalTable = Table.RenameColumns(ChildBlank, List.Zip({ColKeys, ColLabels}))
in
    FinalTable

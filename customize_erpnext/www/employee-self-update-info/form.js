// Trang www/employee-self-update-info — tách nguyên văn từ <script> của index.html (27/10/2026),
// giữ cả thụt lề cũ (chuỗi template nhiều dòng phụ thuộc khoảng trắng).
// index.html đặt window.csrf_token / window.COMPANY trước khi nạp file này.
// Test: customize_erpnext/tests_js/self_update_info (node run.js).

    const M = {
      config: "customize_erpnext.api.self_update_info.self_update_info_api.get_field_config",
      employees: "customize_erpnext.api.self_update_info.self_update_info_api.get_eligible_employees",
      verify: "customize_erpnext.api.self_update_info.self_update_info_api.verify_employee",
      access: "customize_erpnext.api.self_update_info.self_update_info_api.get_access_info",
      unlock: "customize_erpnext.api.self_update_info.self_update_info_api.unlock_access",
      formData: "customize_erpnext.api.self_update_info.self_update_info_api.get_form_data",
      save: "customize_erpnext.api.self_update_info.self_update_info_api.save_form_data",
      pdf: "customize_erpnext.api.self_update_info.self_update_info_api.download_submission_pdf",
      image: "customize_erpnext.api.self_update_info.self_update_info_api.download_submission_image",
      provinces: "customize_erpnext.api.vn_address_search.vn_address_search_api.get_province_options",
      wards: "customize_erpnext.api.vn_address_search.vn_address_search_api.get_ward_options",
    };

    // Company name in the header (injected via Jinja, set after load).
    document.addEventListener("DOMContentLoaded", function () {
      // Tên công ty trên header (inject qua Jinja).
      const cn = document.getElementById("company_name");
      if (cn) cn.textContent = window.COMPANY || "";
      // Tự lưu nháp khi gõ/chọn (nếu Setting bật localStorage).
      const fa = document.getElementById("form_area");
      if (fa) { fa.addEventListener("input", saveDraft); fa.addEventListener("change", saveDraft); }

      // Chặn Zalo webview: quyết định sau khi có config (init()).
    });

    // Màn hình hướng dẫn mở bằng trình duyệt ngoài (chỉ hiện trong Zalo).
    function showBrowserGuide() {
      document.body.style.overflow = "hidden";
      const ov = document.createElement("div");
      ov.id = "zalo_blocker_overlay";
      ov.innerHTML = `
        <style>
          #zalo_blocker_overlay{position:fixed;inset:0;z-index:999999;overflow:auto;
            background:linear-gradient(160deg,#17233F,#0C1424);color:#fff;
            font-family:'Be Vietnam Pro',-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
            display:flex;flex-direction:column;align-items:center;justify-content:center;
            padding:28px 22px;text-align:center;box-sizing:border-box}
          #zalo_blocker_overlay .zb-arrow{position:fixed;top:10px;right:14px;text-align:right;z-index:2;animation:zbBounce .85s ease-in-out infinite}
          #zalo_blocker_overlay .zb-arrow b{display:inline-block;font-size:15px;font-weight:800;color:#1B2733;
            background:#FBBF24;padding:6px 13px;border-radius:20px;box-shadow:0 5px 16px rgba(251,191,36,.55);animation:zbPulse .85s ease-in-out infinite}
          #zalo_blocker_overlay .zb-arrow i{display:block;font-style:normal;font-size:44px;line-height:1;margin-bottom:2px;filter:drop-shadow(0 3px 6px rgba(0,0,0,.45))}
          #zalo_blocker_overlay .zb-ico{font-size:54px;margin-bottom:14px}
          #zalo_blocker_overlay h2{font-size:22px;font-weight:700;margin:0 0 10px}
          #zalo_blocker_overlay .zb-sub{font-size:14px;color:#AEB8CC;line-height:1.6;margin:0 0 22px;max-width:340px}
          #zalo_blocker_overlay .zb-card{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);
            border-radius:14px;padding:16px 18px;width:100%;max-width:340px;text-align:left;margin-bottom:18px}
          #zalo_blocker_overlay .zb-t{font-weight:700;color:#7CC4FF;font-size:12px;letter-spacing:.06em;text-transform:uppercase;margin-bottom:12px}
          #zalo_blocker_overlay .zb-step{display:flex;align-items:flex-start;gap:11px;margin-bottom:11px;font-size:14.5px;color:#E5EAF3;line-height:1.5}
          #zalo_blocker_overlay .zb-step:last-child{margin-bottom:0}
          #zalo_blocker_overlay .zb-num{flex-shrink:0;width:23px;height:23px;border-radius:7px;background:#2A3D66;
            color:#fff;font-weight:700;font-size:12px;display:flex;align-items:center;justify-content:center}
          #zalo_blocker_overlay .zb-shot{width:100%;max-width:3000px;border-radius:12px;background:#fff;
            border:1px solid rgba(255,255,255,.2);box-shadow:0 10px 26px rgba(0,0,0,.4)}
          @keyframes zbBounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-11px)}}
          @keyframes zbPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.08)}}
        </style>
        <div class="zb-arrow"><i>↗️</i></div>
        <div class="zb-ico">🌐</div>
        <h2>Vui lòng mở bằng trình duyệt</h2>
        <p class="zb-sub">Trình duyệt web trong Zalo bị giới hạn tính năng: <b>không tải được file PDF</b> và dễ bị gián đoạn bởi tin nhắn / cuộc gọi.<br>Hãy mở trang này bằng <b>Chrome</b> hoặc <b>Safari</b> của thiết bị.</p>
        <div class="zb-card">
          <div class="zb-t">Cách mở</div>
          <div class="zb-step"><span class="zb-num">1</span><span>Bấm nút <b>⋮</b> ở góc trên bên phải màn hình.</span></div>
          <div class="zb-step"><span class="zb-num">2</span><span>Chọn dòng <b>“Mở bằng trình duyệt”</b> (như hình dưới).</span></div>
        </div>
        <img class="zb-shot" src="/employee-self-update-info/open_with_browser.png" alt="Chọn Mở bằng trình duyệt trong menu Zalo">
      `;
      document.body.appendChild(ov);
    }

    const S = { employee_id: null, employee_name: null, config: null, original: {}, values: {}, verifyCode: null, unlockCode: null, downloadToken: null, fieldByName: {}, tables: {} };

    // CCCD QR scan: only offered when this Employee field is configured.
    const CCCD_FIELD = "custom_id_card_no";              // số CCCD
    const CCCD_ISSUE_FIELD = "custom_id_card_date_of_issue";  // ngày cấp
    const CCCD_CMND_FIELD = "custom_id_card_cmnd_no";    // số CMND cũ
    const CCCD_EXPIRE_FIELD = "custom_id_card__date_of_expired";  // ngày hết hạn (tự tính theo luật)
    const DOB_FIELD = "date_of_birth";                   // ngày sinh (điền nếu field có trên form)
    const DEFAULT_PROVINCE = "Tỉnh Quảng Ngãi";          // mặc định điền khi tỉnh còn trống
    // Giá trị điền sẵn khi ô còn trống lúc mở form (NV vẫn sửa được). Không áp cho field
    // auto_fill = 0 / read_only. Tỉnh mặc định xử lý riêng trong initAddressWidgets.
    const FIELD_DEFAULTS = { custom_ethnicity: "Kinh" };
    let provincesCache = null;
    const wardsCache = {};

    async function api(method, args = {}) {
      const fd = new FormData();
      fd.append("csrf_token", window.csrf_token);
      for (const [k, v] of Object.entries(args))
        fd.append(k, v === null || v === undefined ? "" : (typeof v === "object" ? JSON.stringify(v) : String(v)));
      const res = await fetch(`/api/method/${method}`, { method: "POST", credentials: "same-origin", body: fd });
      if (res.status === 403) { location.reload(); throw new Error("Phiên đã hết hạn"); }
      const data = await res.json();
      if (data.exc) {
        let msg = "";
        try { msg = JSON.parse(JSON.parse(data._server_messages || "[]")[0]).message; } catch { }
        throw new Error(msg || data.exc_type || "Lỗi máy chủ");
      }
      return data.message;
    }

    function esc(s) {
      return String(s == null ? "" : s).replace(/[&<>"']/g, c => (
        { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }

    // Biến URL trong text thành link bấm được.
    // LƯU Ý: chỉ gọi trên chuỗi ĐÃ esc() — nên trong URL không thể còn " hay <.
    function linkify(escaped) {
      return escaped.replace(/(https?:\/\/[^\s<]+)/g, (m) => {
        const trail = m.match(/[.,;:!?)]+$/);          // đừng nuốt dấu câu cuối
        const url = trail ? m.slice(0, -trail[0].length) : m;
        const tail = trail ? trail[0] : "";
        return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>${tail}`;
      });
    }

    // ---------- lưu nháp cục bộ (chống mất dữ liệu khi reload/thoát) ----------
    // Lưu theo từng nhân viên trong localStorage; xoá sau khi gửi thành công.
    const DRAFT_TTL = 24 * 3600 * 1000;   // nháp quá 1 ngày coi như bỏ
    const draftKey = (id) => "esui_draft_" + (id || S.employee_id || "");
    let _draftTimer = null;

    // Bật/tắt lưu nháp cục bộ theo cấu hình Setting (allow_browser_local_storage).
    const draftAllowed = () => !!(S.config && S.config.allow_local_draft);

    function saveDraft() {
      if (!S.employee_id || !S.config || !draftAllowed()) return;
      clearTimeout(_draftTimer);
      _draftTimer = setTimeout(() => {
        try {
          const values = {};
          for (const sec of S.config.sections)
            for (const f of sec.fields)
              if (!f.read_only) values[f.fieldname] = currentValue(f);
          localStorage.setItem(draftKey(), JSON.stringify({ t: Date.now(), values, docs: checkedDocs() }));
        } catch (e) { /* localStorage bị chặn/đầy → bỏ qua, không chặn người dùng */ }
      }, 400);
    }

    function loadDraft(empId) {
      if (!draftAllowed()) return null;
      try {
        const raw = localStorage.getItem(draftKey(empId));
        if (!raw) return null;
        const d = JSON.parse(raw);
        if (!d || !d.t) return null;
        if (Date.now() - d.t > DRAFT_TTL) { clearDraft(empId); return null; }
        return d;
      } catch (e) { return null; }
    }

    function clearDraft(empId) {
      try { localStorage.removeItem(draftKey(empId)); } catch (e) { }
    }

    function toast(msg, ok = false) {
      const t = document.getElementById("toast");
      t.textContent = msg; t.style.background = ok ? "#166534" : "#111827";
      t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 2600);
    }

    // ---------- employee search combobox ----------
    let allEmps = [];          // [{employee_id, display_name, submitted, _hay}]
    let comboMatches = [];     // current filtered list
    let comboActive = -1;      // keyboard-highlighted index

    function deburr(s) {
      return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
        .replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
    }

    (async function init() {
      const inp = document.getElementById("emp_search");
      // Tải config sớm: nếu bật "Force Open Device's Browser" và đang trong Zalo → chặn.
      try { if (!S.config) S.config = await api(M.config); } catch (e) { }
      // Thật: chỉ trong Zalo webview. Test: thêm ?zalo=1 để xem trước overlay ở trình duyệt thường.
      const _testZalo = new URLSearchParams(location.search).get("zalo") === "1";
      const _inZalo = /Zalo/i.test(navigator.userAgent) || _testZalo;
      if (_inZalo && S.config && S.config.force_device_browser) {
        showBrowserGuide();
      }
      try {
        const emps = await api(M.employees);
        allEmps = emps.map(e => ({ ...e, _hay: deburr(e.display_name + " " + e.employee_id) }));
        inp.disabled = false;
        inp.placeholder = "Gõ mã nhân viên hoặc tên để tìm…";
        document.addEventListener("click", (ev) => {
          if (!ev.target.closest(".combo")) hideEmpResults();
        });
        const url = new URLSearchParams(location.search);
        const pre = url.get("emp");
        if (pre) {
          // Direct link (?emp=...) — mở thẳng vào nhân viên, ẩn ô tìm/chọn.
          // HR có thể mở bất kỳ NV (kể cả không có trong danh sách); server tự kiểm tra quyền.
          document.getElementById("picker_card").classList.add("hidden");
          onEmpSelected(pre);
        }
      } catch (e) { toast(e.message); inp.placeholder = "Không tải được danh sách"; }
    })();

    function onEmpSearch() {
      const q = deburr(document.getElementById("emp_search").value.trim());
      comboMatches = !q ? allEmps.slice(0, 50)
        : allEmps.filter(e => e._hay.includes(q)).slice(0, 50);
      comboActive = -1;
      renderEmpResults(q);
    }

    function renderEmpResults(q) {
      const box = document.getElementById("emp_results");
      if (!comboMatches.length) {
        box.innerHTML = `<div class="combo-empty">Không tìm thấy nhân viên phù hợp</div>`;
        box.classList.remove("hidden"); return;
      }
      box.innerHTML = comboMatches.map((e, i) =>
        `<div class="combo-item${i === comboActive ? ' active' : ''}" data-id="${esc(e.employee_id)}" onclick="pickEmpById('${esc(e.employee_id)}')">
        <span>${esc(e.display_name)}${e.submitted ? ' <span class="ok">✓</span>' : ''}</span>
        <span class="code">${esc(e.employee_id)}</span>
      </div>`).join("");
      box.classList.remove("hidden");
    }

    function hideEmpResults() { document.getElementById("emp_results").classList.add("hidden"); }

    function onEmpKey(ev) {
      const box = document.getElementById("emp_results");
      if (box.classList.contains("hidden")) return;
      if (ev.key === "ArrowDown") { ev.preventDefault(); comboActive = Math.min(comboActive + 1, comboMatches.length - 1); renderEmpResults(); scrollActive(); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); comboActive = Math.max(comboActive - 1, 0); renderEmpResults(); scrollActive(); }
      else if (ev.key === "Enter") { ev.preventDefault(); const i = comboActive >= 0 ? comboActive : 0; if (comboMatches[i]) pickEmp(comboMatches[i]); }
      else if (ev.key === "Escape") { hideEmpResults(); }
    }

    function scrollActive() {
      const el = document.querySelectorAll("#emp_results .combo-item")[comboActive];
      if (el) el.scrollIntoView({ block: "nearest" });
    }

    function pickEmpById(id) { const e = allEmps.find(x => x.employee_id === id); if (e) pickEmp(e); }

    function pickEmp(e) {
      document.getElementById("emp_search").value = `${e.display_name} (${e.employee_id})`;
      hideEmpResults();
      onEmpSelected(e.employee_id);
    }

    function resetForm() {
      document.getElementById("verify_card").classList.add("hidden");
      document.getElementById("lock_card").classList.add("hidden");
      document.getElementById("form_area").classList.add("hidden");
      document.getElementById("submitbar").classList.add("hidden");
      lockEmpSearch(false);   // mở lại ô chọn NV khi bắt đầu lượt chọn mới
    }

    // Khóa/mở ô "Mã nhân viên hoặc Họ tên". Dùng disabled để chặn cả focus
    // (tránh mở lại combo gợi ý sau khi đã xác thực).
    function lockEmpSearch(locked) {
      const inp = document.getElementById("emp_search");
      if (!inp) return;
      inp.disabled = locked;
      inp.classList.toggle("locked", locked);
      // Ẩn dòng hướng dẫn "Gõ mã nhân viên…" sau khi khóa (thừa).
      const hint = document.getElementById("emp_hint");
      if (hint) hint.classList.toggle("hidden", locked);
      if (locked) hideEmpResults();
    }

    // Decide between lock gate, verification gate, or loading the form directly.
    async function onEmpSelected(empId) {
      try {
        resetForm();
        S.employee_id = empId; S.verifyCode = null; S.unlockCode = null; S.downloadToken = null;
        if (!S.config) S.config = await api(M.config);

        // Nếu đã submit + Setting khoá → yêu cầu mở khoá (ngày sinh + mã HR).
        if (S.config.lock_after_submit) {
          const acc = await api(M.access, { employee_id: empId });
          if (acc && acc.locked) { showLockCard(acc); return; }
        }

        if (S.config.require_dob) {
          const vc = document.getElementById("verify_card");
          vc.classList.remove("hidden");
          const vi = document.getElementById("verify_input");
          vi.value = ""; vi.focus();
        } else {
          loadForm(empId, null);
        }
      } catch (e) { toast(e.message); }
    }

    function showLockCard(acc) {
      document.getElementById("lock_msg").innerHTML =
        `Bạn đã cập nhật thông tin lúc <b>${esc(acc.submitted_on || "")}</b>.<br>` +
        `Nếu có sai sót cần nhập lại, vui lòng <b>liên hệ HR</b> để được cấp mã mở khoá.`;
      document.getElementById("lock_dob").value = "";
      document.getElementById("lock_code").value = "";
      document.getElementById("lock_card").classList.remove("hidden");
      document.getElementById("lock_dob").focus();
    }

    let _unlocking = false;
    async function doUnlock() {
      if (_unlocking) return;
      const code = (document.getElementById("lock_dob").value || "").trim();
      const unlock = (document.getElementById("lock_code").value || "").trim();
      if (!code) { toast("Vui lòng nhập 2 số ngày sinh"); return; }
      if (!unlock) { toast("Vui lòng nhập mã mở khoá do HR cấp"); return; }
      _unlocking = true;
      try {
        const r = await api(M.unlock, { employee_id: S.employee_id, code, unlock_code: unlock });
        if (r && r.valid) {
          S.unlockCode = unlock;
          document.getElementById("lock_card").classList.add("hidden");
          loadForm(S.employee_id, code);
        } else {
          toast("Ngày sinh hoặc mã mở khoá không đúng. Vui lòng thử lại.");
          document.getElementById("lock_code").value = "";
          document.getElementById("lock_code").focus();
        }
      } catch (e) { toast(e.message); }
      finally { _unlocking = false; }
    }

    let _verifying = false;
    async function doVerify() {
      if (_verifying) return;                       // chống gọi trùng (auto + Enter)
      const code = (document.getElementById("verify_input").value || "").trim();
      if (!code) { toast("Vui lòng nhập mã xác thực"); return; }
      _verifying = true;
      try {
        const r = await api(M.verify, { employee_id: S.employee_id, code });
        if (r && r.valid) {
          document.getElementById("verify_card").classList.add("hidden");
          loadForm(S.employee_id, code);           // đúng → vào thẳng form, không cần bấm nút
        } else {
          toast("Mã xác thực không đúng. Vui lòng thử lại.");
          const vi = document.getElementById("verify_input");
          vi.value = ""; vi.focus();               // sai → xoá để gõ lại
        }
      } catch (e) { toast(e.message); }
      finally { _verifying = false; }
    }

    async function loadForm(empId, code) {
      try {
        S.verifyCode = code || null;
        document.getElementById("submit_btn").disabled = true;
        if (!S.config) S.config = await api(M.config);
        const fd = await api(M.formData, { employee_id: empId, code: code || "", unlock_code: S.unlockCode || "" });
        S.employee_id = empId; S.employee_name = fd.employee_name;
        S.original = fd.original || {}; S.values = fd.values || {};

        // Khôi phục nháp cục bộ (nếu có) — đè lên giá trị server TRƯỚC khi render
        // để cascade địa chỉ & mọi widget cùng dựng theo dữ liệu đang nhập dở.
        const draft = loadDraft(empId);
        if (draft && draft.values) S.values = { ...S.values, ...draft.values };

        // Field auto_fill=0: luôn để trống mỗi lần truy cập — không nhận cả
        // giá trị server (đã null) lẫn nháp cục bộ. NV phải tự nhập lại.
        (S.config.sections || []).forEach(sec => (sec.fields || []).forEach(f => {
          if (f.auto_fill === false) delete S.values[f.fieldname];
        }));
        (S.config.sections || []).forEach(sec => (sec.fields || []).forEach(f => {
          const def = FIELD_DEFAULTS[f.fieldname];
          if (def === undefined || f.auto_fill === false || f.read_only) return;
          if (norm(S.values[f.fieldname]).trim() === "") S.values[f.fieldname] = def;
        }));

        renderForm();
        renderDocs(draft && Array.isArray(draft.docs) ? draft.docs : (fd.documents || []));
        resetSignCard(!!fd.is_hr);
        if (draft) toast("Đã khôi phục thông tin bạn nhập dở trước đó", true);
        document.getElementById("emp_label").textContent = `${fd.employee_name || empId}`;
        const sw = document.getElementById("status_wrap");
        sw.innerHTML = fd.status ?
          `<span id="status_pill" class="${fd.status === 'Submitted' ? 'pill-sub' : 'pill-draft'}">${fd.status === 'Submitted' ? 'Đã gửi' : 'Bản nháp'}</span>` : "";
        document.getElementById("form_area").classList.remove("hidden");
        document.getElementById("submitbar").classList.remove("hidden");
        document.getElementById("success_area").classList.add("hidden");
        document.getElementById("submit_btn").disabled = false;
        // Khóa ô chọn NV sau khi xác thực/tải form thành công — không cho đổi NV.
        lockEmpSearch(true);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch (e) {
        toast(e.message);
        document.getElementById("picker_card").classList.remove("hidden");  // tránh dead-end
      }
    }

    // ---------- render ----------
    function renderForm() {
      const root = document.getElementById("sections");
      if (!S.config.sections.length) {
        root.innerHTML =
          `<div class="card"><div class="empty">Chưa có trường nào được cấu hình.<br>Liên hệ bộ phận nhân sự.</div></div>`; return;
      }

      root.innerHTML = S.config.sections.map(sec => {
        let provFieldInSection = null;
        const fieldsHtml = sec.fields.map(f => {
          if (f.widget === "Address Province") provFieldInSection = f.fieldname;
          return renderField(f, provFieldInSection);
        }).join("");
        return `<div class="card"><h2><span class="dot"></span>${esc(sec.label)}</h2>${fieldsHtml}</div>`;
      }).join("");

      // wire up + index fields by name
      S.fieldByName = {};
      S.config.sections.forEach(sec => sec.fields.forEach(f => {
        S.fieldByName[f.fieldname] = f;
        const el = document.getElementById("f_" + f.fieldname);
        if (!el) return;
        const ev = (f.fieldtype === "Check") ? "change" : "input";
        el.addEventListener(ev, () => markChanged(f));
        if (NORMALIZE_TYPES.has(f.fieldtype) && (f.widget || "Auto") === "Auto" && !f.read_only) {
          // Rời ô → ghi lại bản đã chuẩn hoá để NV thấy (không cảnh báo, không hỏi).
          el.addEventListener("change", () => {
            const nv = normalizeText(f, el.value);
            if (nv !== el.value) { el.value = nv; markChanged(f); }
          });
        }
        if (f.fieldtype === "Table") tblWire(f);
        if (f.fieldname === CCCD_ISSUE_FIELD || f.fieldname === DOB_FIELD) {
          el.addEventListener("input", () => recalcCccdExpiry(true));
          el.addEventListener("change", () => recalcCccdExpiry(true));
        }
        // KHÔNG đánh dấu lúc load: chỉ tô "đã đổi" khi NV thực sự thao tác
        // (tránh báo nhầm với field auto_fill / prefill từ lần gửi trước).
      }));
      // Field "chỉ hiện khi…" (f.depends_on, _FIELD_DEPENDS ở server): đổi field điều kiện → ẩn/hiện lại.
      S.config.sections.forEach(sec => sec.fields.forEach(f => {
        if (!f.depends_on) return;
        const pel = document.getElementById("f_" + f.depends_on.field);
        if (pel) pel.addEventListener("change", applyDepends);
      }));
      applyDepends();
      recalcCccdExpiry(false);
      initAddressWidgets();
    }

    // Đang hiện? — giá trị field điều kiện nằm trong danh sách. Cùng luật _apply_depends ở server.
    function depVisible(f) {
      if (!f.depends_on) return true;
      const pf = S.fieldByName[f.depends_on.field];
      const pv = pf ? currentValue(pf) : (S.values[f.depends_on.field] || "");
      return f.depends_on.values.includes(pv || "");
    }
    // Ẩn ô không thoả điều kiện và xoá trắng giá trị (server cũng xoá khi lưu).
    function applyDepends() {
      S.config.sections.forEach(sec => sec.fields.forEach(f => {
        if (!f.depends_on) return;
        const show = depVisible(f);
        const box = document.getElementById("fg_" + f.fieldname);
        if (box) box.classList.toggle("hidden", !show);
        const el = document.getElementById("f_" + f.fieldname);
        if (!show && el && el.value) { el.value = ""; markChanged(f); }
      }));
    }

    function renderField(f, provField) {
      const id = "f_" + f.fieldname;
      const ro = f.read_only ? " ro" : "";
      const roAttr = f.read_only ? " disabled" : "";
      // depends_on: khi hiện thì luôn bắt buộc.
      const req = (f.required || f.depends_on) ? `<span class="req">*</span>` : "";
      const val = S.values[f.fieldname];
      // Gợi ý mờ trong ô trống (cột "Placeholder" trong Setting).
      // Không gắn cho Date (trình duyệt luôn hiện định dạng ngày) / Select / Check.
      const ph = f.placeholder ? ` placeholder="${esc(f.placeholder)}"` : "";
      let input = "";

      if (f.widget === "Address Province" || f.widget === "Address Ward") {
        // Ô gõ để tìm (xem "address combobox" bên dưới); giá trị đã chọn nằm ở dataset.value.
        const kind = f.widget === "Address Province" ? "province" : "ward";
        input = `<div class="combo addr-combo" data-kind="${kind}" data-fieldname="${f.fieldname}"` +
          ` data-prov-field="${kind === "ward" ? (provField || "") : ""}" data-ro="${f.read_only ? 1 : 0}">` +
          `<input type="text" id="${id}" autocomplete="off" disabled data-value="" data-code=""` +
          ` placeholder="${kind === "province" ? "Gõ để tìm tỉnh/thành…" : "Chọn tỉnh/thành trước"}">` +
          `<button type="button" class="addr-clear hidden" tabindex="-1" aria-label="Xoá">✕</button>` +
          `<div class="combo-list hidden"></div></div>`;
      } else if (f.fieldtype === "Table") {
        input = tblShell(f, val);
      } else if (f.fieldtype === "Check") {
        const ck = (val === 1 || val === "1" || val === true) ? " checked" : "";
        input = `<div class="chk"><input type="checkbox" id="${id}"${ck}${roAttr}><span class="muted">Có</span></div>`;
      } else if (f.fieldtype === "Select") {
        // Nhãn tiếng Việt (option_labels), giá trị gửi đi giữ nguyên: <option value="Married">Đã kết hôn</option>.
        const lbl = f.option_labels || {};
        const opts = (f.options || []).map(o => `<option value="${esc(o)}"${String(val || "") === String(o) ? " selected" : ""}>${esc(lbl[o] || o || "— Chọn —")}</option>`).join("");
        input = `<select id="${id}"${roAttr}>${opts}</select>`;
      } else if (["Small Text", "Text", "Long Text"].includes(f.fieldtype)) {
        input = `<textarea id="${id}"${ph}${roAttr}>${esc(val || "")}</textarea>`;
      } else if (["Int", "Float", "Currency"].includes(f.fieldtype)) {
        input = `<input type="number" id="${id}" value="${esc(val == null ? "" : val)}"${ph}${roAttr}>`;
      } else if (f.fieldname === CCCD_EXPIRE_FIELD) {
        // Ngày hết hạn CCCD: KHÔNG cho nhập — tự tính từ ngày sinh + ngày cấp (recalcCccdExpiry);
        // server tính lại khi gửi (self_update_info_api._apply_cccd_expiry).
        input = `<input type="date" id="${id}" value="${esc(val || "")}" readonly tabindex="-1" class="auto-calc">` +
          `<div class="hint">Tự tính theo ngày sinh và ngày cấp.</div>`;
      } else if (f.fieldtype === "Date") {
        let dattr = "";
        if (f.validation === "Past") dattr = ` max="${todayISO()}"`;
        else if (f.validation === "Future") dattr = ` min="${todayISO()}"`;
        input = `<input type="date" id="${id}" value="${esc(val || "")}"${dattr}${roAttr}>`;
      } else {
        input = `<input type="text" id="${id}" value="${esc(val || "")}"${ph}${valAttrs(f)}${roAttr}>`;
      }
      // CCCD — chỉ 2 lựa chọn: quét QR trực tiếp, hoặc nhập tay ở ô bên dưới.
      // (Đã tạm ẩn tuỳ chọn "Chụp / chọn ảnh CCCD" — xem khối comment bên dưới
      //  và hàm onCccdPhoto/_decodeImageForQR nếu cần bật lại.)
      const scanUi = (f.fieldname === CCCD_FIELD && !f.read_only)
        ? `<button type="button" class="qr-scan-btn" onclick="openQRScanner()">📷 Quét mã QR trên CCCD</button>
         <!-- TẠM ẨN — upload ảnh CCCD:
         <button type="button" class="qr-scan-btn alt" onclick="document.getElementById('cccd_photo_input').click()">🖼️ Chụp / chọn ảnh CCCD (nếu quét khó)</button>
         <input type="file" id="cccd_photo_input" accept="image/*" capture="environment" style="display:none" onchange="onCccdPhoto(event)">
         -->
         <div class="hint"><div><ul>
<li>Nếu thông tin CCCD đã chính xác ➡️ Bỏ qua.</li>
<li>Nếu cần cập nhật, thay đổi:
<ul>
<li>Bấm nút trên để quét mã QR trên CCCD — hệ thống tự điền số CCCD, ngày cấp, ngày hết hạn và số CMND cũ.</li>
<li>Hoặc <span style="color: #ff0000;">nhập tay vào ô bên dưới nếu <strong>KHÔNG </strong>quét được mã QR</span>.</li>
</ul>
</li>
</ul></div>`
        : "";
      // Giải thích thêm cho field (cột "Detail" trong Setting) — hiện dưới nhãn.
      const detailUi = f.detail
        ? `<div class="field-detail">${linkify(esc(f.detail))}</div>`
        : "";
      return `<div class="field${ro}" id="fg_${f.fieldname}">
      <label class="fl" for="${id}">${esc(f.label)} ${req}</label>
      ${detailUi}${scanUi}${input}</div>`;
    }

    // ---------- bảng con của Employee (Học vấn, Quá trình làm việc) ----------
    // Mỗi mục 1 thẻ (hợp điện thoại), ô theo f.columns; "+ Thêm" tới f.max_rows.
    // `name` = ID dòng con trên Employee, giữ ẩn để Sync sửa đúng dòng. Dòng mà mọi ô trống bị bỏ khi gửi.
    // Server làm sạch + kiểm lại (self_update_info_api._clean_table_value).
    function tblRows(f) { return S.tables[f.fieldname] || (S.tables[f.fieldname] = []); }

    function tblShell(f, val) {
      const rows = (Array.isArray(val) ? val : []).map(r => ({ ...r }));
      // Giá trị Select ngoài danh sách (dữ liệu cũ) → coi như chưa chọn: ô hiện trống thì giá trị gửi đi cũng trống.
      rows.forEach(r => f.columns.forEach(c => {
        if (c.fieldtype === "Select" && r[c.fieldname] && !(c.options || []).includes(r[c.fieldname])) r[c.fieldname] = "";
      }));
      if (!rows.length && !f.read_only) rows.push({});   // sẵn 1 thẻ trống để NV thấy ô nhập
      S.tables[f.fieldname] = rows;
      return `<div class="tbl" id="f_${esc(f.fieldname)}">${tblInner(f)}</div>`;
    }

    function tblCell(f, c, i, v) {
      const a = ` data-i="${i}" data-col="${esc(c.fieldname)}"${f.read_only ? " disabled" : ""}`;
      const ph = c.placeholder ? ` placeholder="${esc(c.placeholder)}"` : "";
      if (c.fieldtype === "Select") {
        const lbl = c.option_labels || {};
        const opts = (c.options || []).map(o =>
          `<option value="${esc(o)}"${String(v) === String(o) ? " selected" : ""}>${esc(lbl[o] || o || "— Chọn —")}</option>`).join("");
        return `<select${a}>${opts}</select>`;
      }
      if (c.fieldtype === "Int" || c.fieldtype === "Float")
        return `<input type="number" inputmode="numeric" value="${esc(v)}"${ph}${a}>`;
      if (c.fieldtype === "Date") return `<input type="date" value="${esc(v)}"${a}>`;
      return `<input type="text" value="${esc(v)}"${ph}${a}>`;
    }

    function tblInner(f) {
      const rows = tblRows(f);
      const cards = rows.map((r, i) =>
        `<div class="tbl-row"><div class="tbl-head"><span>${i + 1}.</span>` +
        (f.read_only ? "" : `<button type="button" class="tbl-del" data-i="${i}">✕ Xoá</button>`) + `</div>` +
        f.columns.filter(c => !tblColHidden(f, c, r)).map(c =>
          `<label class="tbl-lbl">${esc(c.label)}${tblColRequired(f, c, r) ? ' <span class="req">*</span>' : ""}</label>` +
          tblCell(f, c, i, r[c.fieldname] == null ? "" : r[c.fieldname])).join("") +
        `</div>`).join("");
      const add = (!f.read_only && rows.length < f.max_rows)
        ? `<button type="button" class="tbl-add">+ Thêm</button>`
        : (!f.read_only ? `<div class="hint">Tối đa ${f.max_rows}.</div>` : "");
      return (cards || `<div class="hint">—</div>`) + add;
    }

    function tblWire(f) {
      const box = document.getElementById("f_" + f.fieldname);
      if (!box || f.read_only) return;
      const rerender = () => { box.innerHTML = tblInner(f); markChanged(f); saveDraft(); };
      const store = (t) => {
        if (t.dataset.col === undefined || t.dataset.i === undefined) return false;
        const row = tblRows(f)[+t.dataset.i];
        if (row) row[t.dataset.col] = t.value;
        return true;
      };
      box.addEventListener("input", (e) => { if (store(e.target)) markChanged(f); });
      box.addEventListener("change", (e) => {
        const t = e.target;
        const c = f.columns.find(x => x.fieldname === t.dataset.col);
        if (!c) return;
        const nv = normalizeText(c, t.value);   // rời ô → hiện bản đã chuẩn hoá như field thường
        if (nv !== t.value) t.value = nv;
        store(t); markChanged(f);
        // Đổi cột điều kiện (vd Trình độ) → vẽ lại: ẩn/hiện + dấu * của các cột phụ thuộc theo giá trị mới.
        if (f.required_if && c.fieldname === f.required_if.column) box.innerHTML = tblInner(f);
      });
      box.addEventListener("click", (e) => {
        const del = e.target.closest(".tbl-del"), add = e.target.closest(".tbl-add");
        if (del) { tblRows(f).splice(+del.dataset.i, 1); rerender(); }
        else if (add && tblRows(f).length < f.max_rows) { tblRows(f).push({}); rerender(); }
      });
    }

    // Giá trị gửi lên: list dòng đã chuẩn hoá, bỏ dòng trống; giữ `name` của dòng có sẵn trên Employee.
    function tblValue(f) {
      return tblRows(f).map(r => {
        const out = {};
        f.columns.forEach(c => {
          // Cột đang ẩn (vd THCS/THPT) → gửi trống, không mang giá trị nhập trước khi đổi trình độ.
          out[c.fieldname] = tblColHidden(f, c, r) ? "" : normalizeText(c, String(r[c.fieldname] == null ? "" : r[c.fieldname]).trim());
        });
        return { row: out, name: r.name };
      }).filter(x => Object.values(x.row).some(v => v !== ""))
        .map(x => (x.name ? { name: x.name, ...x.row } : x.row));
    }

    // Khoá so sánh "đã đổi": chỉ giá trị các cột (bỏ `name`), theo thứ tự dòng.
    function tblKey(f, rows) {
      return JSON.stringify((Array.isArray(rows) ? rows : []).map(r =>
        f.columns.map(c => String(r[c.fieldname] == null ? "" : r[c.fieldname]).trim())));
    }

    // Cột bắt buộc ở dòng này: cố định (c.required) hoặc theo f.required_if — cùng luật _column_required ở server.
    function tblColRequired(f, c, row) {
      if (c.required) return true;
      const rule = f.required_if;
      return !!rule && (rule.required || []).includes(c.fieldname) && rule.values.includes((row || {})[rule.column]);
    }

    // Cột ẩn ở dòng này: thuộc required_if và cột điều kiện ĐÃ chọn giá trị ngoài danh sách — như _column_hidden.
    function tblColHidden(f, c, row) {
      const rule = f.required_if;
      const v = rule ? (row || {})[rule.column] : "";
      return !!rule && rule.columns.includes(c.fieldname) && !!v && !rule.values.includes(v);
    }

    function tblValidate(f, rows) {
      if (rows.length > f.max_rows) return `${f.label}: tối đa ${f.max_rows}`;
      for (let i = 0; i < rows.length; i++) {
        for (const c of f.columns) {
          const v = rows[i][c.fieldname];
          if (tblColRequired(f, c, rows[i]) && !v) return `${f.label} (${i + 1}): chưa nhập ${c.label}`;
          if (v && c.fieldtype === "Int" && !/^\d{1,9}$/.test(v)) return `${f.label} – ${c.label}: phải là số`;
        }
      }
      return "";
    }

    // ---------- changed tracking ----------
    function currentValue(f) {
      const el = document.getElementById("f_" + f.fieldname);
      if (!el) return "";
      if (f.fieldtype === "Check") return el.checked ? 1 : 0;
      if (f.fieldtype === "Table") return tblValue(f);
      if (f.widget === "Address Province" || f.widget === "Address Ward") {
        return el.dataset.value || "";   // chữ đang gõ để lọc KHÔNG phải giá trị
      }
      return normalizeText(f, el.value);
    }

    // Tự chuẩn hoá chữ NV nhập — cùng quy tắc _normalize_text() ở server (server làm lại khi lưu;
    // sửa một nơi thì sửa cả hai). Field chữ widget Auto, trừ Email:
    //  NFC · gộp khoảng trắng · "Xóm1" → "Xóm 1" (phần chữ ≥ 2 ký tự có chữ thường; giữ "B2", "TDP1")
    //  · viết hoa ký tự đầu · Capitalize Each Word: hoa ký tự đầu mỗi từ, giữ nguyên phần còn lại
    //  · Sentence Case: hoa ký tự đầu mỗi câu (sau . ! ? …, đầu dòng). Không cảnh báo, không hỏi.
    const NORMALIZE_TYPES = new Set(["Data", "Small Text", "Text", "Long Text"]);
    function normalizeText(f, v) {
      if (typeof v !== "string") return v;
      if (!NORMALIZE_TYPES.has(f.fieldtype) || (f.widget || "Auto") !== "Auto") return v;
      // Email (Validation, hoặc giá trị trông như email dù chưa gán Validation): chỉ bỏ khoảng trắng.
      if ((f.validation || "") === "Email" || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.trim())) return v.trim();
      v = v.normalize("NFC");
      const multiline = f.fieldtype !== "Data";
      const lines = (multiline ? v.split("\n") : [v]).map(l => l.replace(/[ \t\u00a0]+/g, " ").trim());
      v = (multiline ? lines.join("\n") : lines[0]).trim();
      v = v.replace(/(?<![\p{L}])(\p{L}{2,})(?=\d)/gu, (m) => (/\p{Ll}/u.test(m) ? m + " " : m));
      if (f.validation === "Capitalize Each Word") {
        return v.split("\n").map(l => l.split(" ").map(x => x.charAt(0).toUpperCase() + x.slice(1)).join(" ")).join("\n");
      }
      if (f.validation === "Sentence Case") {
        // cùng regex _SENTENCE_START ở server
        return v.replace(/(^|[.!?…]\s+|\n)(["'“‘(\[]*)(\p{L})/gu, (m, a, b, c) => a + b + c.toUpperCase());
      }
      return v.charAt(0).toUpperCase() + v.slice(1);
    }

    function norm(v) { return (v === null || v === undefined) ? "" : String(v); }

    function markChanged(f) {
      const fg = document.getElementById("fg_" + f.fieldname);
      if (!fg) return;
      const changed = f.fieldtype === "Table"
        ? tblKey(f, currentValue(f)) !== tblKey(f, S.original[f.fieldname])
        : norm(currentValue(f)) !== norm(S.original[f.fieldname]);
      fg.classList.toggle("changed", changed);
    }

    // ---------- address combobox (Tỉnh → Phường/Xã) ----------
    // Gõ để tìm (bỏ dấu: "ba to" ra Ba Tơ + Ba Tô), CHỈ nhận giá trị trong danh sách.
    // Dữ liệu: api/vn_address_search — dùng chung API với form Employee; JS độc lập vì trang www
    // không có object frappe. Server chặn lại cặp sai ở save_form_data (_portal_address_errors).
    // Giá trị lưu = tên đầy đủ ("Tỉnh Quảng Ngãi", "Xã Ba Tơ") như Employee.
    const toCodeName = (rows) => (rows || []).map(r => ({ code: r.code, name: r.label }));
    async function loadProvinces() {
      if (!provincesCache) provincesCache = toCodeName(await api(M.provinces));
      return provincesCache;
    }
    async function loadWards(code) {
      if (!code) return [];
      if (!wardsCache[code]) wardsCache[code] = toCodeName(await api(M.wards, { province: code }));
      return wardsCache[code];
    }

    const addrState = {};   // fieldname → { items:[{code,name,_hay}], matches:[], active }
    const addrBox = (fn) => document.querySelector(`.addr-combo[data-fieldname="${fn}"]`);
    const addrInput = (fn) => document.getElementById("f_" + fn);
    const addrWards = (provFn) => [...document.querySelectorAll(`.addr-combo[data-kind="ward"][data-prov-field="${provFn}"]`)];

    function addrSetItems(fn, items) {
      addrState[fn] = { items: (items || []).map(it => ({ ...it, _hay: deburr(it.name) })), matches: [], active: -1 };
    }

    // Bật/tắt ô: read_only luôn tắt; ô xã tắt khi chưa có tỉnh (chưa có list).
    function addrEnable(fn, on) {
      const box = addrBox(fn), inp = addrInput(fn);
      inp.disabled = !on || box.dataset.ro === "1";
      if (box.dataset.kind === "ward") inp.placeholder = on ? "Gõ để tìm phường/xã…" : "Chọn tỉnh/thành trước";
      addrToggleClear(fn);
    }
    function addrToggleClear(fn) {
      const inp = addrInput(fn);
      addrBox(fn).querySelector(".addr-clear").classList.toggle("hidden", inp.disabled || !inp.dataset.value);
    }

    // Chốt giá trị. notify=true khi là thao tác của NV → bắn "input" để markChanged + lưu nháp.
    function addrCommit(fn, item, notify) {
      const inp = addrInput(fn);
      const prev = inp.dataset.value || "";
      inp.dataset.value = item ? item.name : "";
      inp.dataset.code = item ? item.code : "";
      inp.value = inp.dataset.value;
      addrHide(fn);
      addrToggleClear(fn);
      const changed = inp.dataset.value !== prev;
      if (notify && changed) inp.dispatchEvent(new Event("input", { bubbles: true }));
      if (changed && addrBox(fn).dataset.kind === "province") fillWards(fn, !notify);
    }

    function addrOpen(fn, q) {
      const st = addrState[fn];
      if (!st) return;
      const needle = deburr((q || "").trim());
      st.matches = needle ? st.items.filter(it => it._hay.includes(needle)) : st.items.slice();
      const cur = addrInput(fn).dataset.value;
      st.active = needle ? (st.matches.length ? 0 : -1) : st.matches.findIndex(it => it.name === cur);
      addrRender(fn);
    }

    function addrRender(fn) {
      const st = addrState[fn], list = addrBox(fn).querySelector(".combo-list");
      list.innerHTML = st.matches.length
        ? st.matches.map((it, i) => `<div class="combo-item${i === st.active ? " active" : ""}" data-i="${i}">${esc(it.name)}</div>`).join("")
        : `<div class="combo-empty">Không tìm thấy — gõ ít chữ hơn hoặc bỏ dấu</div>`;
      list.classList.remove("hidden");
      const el = list.querySelector(".combo-item.active");
      if (el) el.scrollIntoView({ block: "nearest" });
    }

    function addrHide(fn) { const b = addrBox(fn); if (b) b.querySelector(".combo-list").classList.add("hidden"); }

    // Rời ô: chữ đang gõ không phải giá trị đã chọn → khớp ĐÚNG 1 tên (có dấu) thì nhận, ô trống thì
    // xoá, còn lại trả về giá trị cũ. Không tự đoán theo bản bỏ dấu (Ba Tơ ≠ Ba Tô).
    function addrSettle(fn) {
      const inp = addrInput(fn), st = addrState[fn];
      addrHide(fn);
      const typed = inp.value.trim();
      if (typed === (inp.dataset.value || "")) return;
      if (!typed) { addrCommit(fn, null, true); return; }
      const hit = st && st.items.find(it => it.name === typed);
      if (hit) { addrCommit(fn, hit, true); return; }
      inp.value = inp.dataset.value || "";
      toast("Vui lòng chọn trong danh sách gợi ý");
    }

    function addrWire(box) {
      const fn = box.dataset.fieldname, inp = addrInput(fn), list = box.querySelector(".combo-list");
      inp.addEventListener("focus", () => {
        inp.select();
        addrOpen(fn, "");
        // Điện thoại: đẩy ô lên để bàn phím không che danh sách.
        setTimeout(() => inp.scrollIntoView({ block: "start", behavior: "smooth" }), 250);
      });
      inp.addEventListener("input", (ev) => { if (ev.isTrusted) addrOpen(fn, inp.value); });
      inp.addEventListener("keydown", (ev) => {
        const st = addrState[fn];
        if (!st) return;
        if (list.classList.contains("hidden") && ev.key === "ArrowDown") { addrOpen(fn, ""); ev.preventDefault(); return; }
        if (ev.key === "ArrowDown") { ev.preventDefault(); st.active = Math.min(st.active + 1, st.matches.length - 1); addrRender(fn); }
        else if (ev.key === "ArrowUp") { ev.preventDefault(); st.active = Math.max(st.active - 1, 0); addrRender(fn); }
        else if (ev.key === "Enter") {
          ev.preventDefault();
          const it = st.matches[st.active >= 0 ? st.active : 0];
          if (it) addrCommit(fn, it, true);
        } else if (ev.key === "Escape") { inp.value = inp.dataset.value || ""; addrHide(fn); }
      });
      inp.addEventListener("blur", () => setTimeout(() => addrSettle(fn), 120));
      // mousedown/pointerdown + preventDefault: chọn trước khi ô mất focus (blur).
      list.addEventListener("pointerdown", (ev) => {
        const el = ev.target.closest(".combo-item");
        if (!el) return;
        ev.preventDefault();
        addrCommit(fn, addrState[fn].matches[+el.dataset.i], true);
      });
      box.querySelector(".addr-clear").addEventListener("pointerdown", (ev) => {
        ev.preventDefault();
        addrCommit(fn, null, true);
      });
    }

    async function initAddressWidgets() {
      const boxes = [...document.querySelectorAll(".addr-combo")];
      if (!boxes.length) return;
      boxes.forEach(addrWire);
      let provinces;
      try { provinces = await loadProvinces(); }
      catch (e) { toast("Không tải được danh sách tỉnh/thành: " + e.message); return; }

      for (const box of boxes.filter(b => b.dataset.kind === "province")) {
        const fn = box.dataset.fieldname;
        addrSetItems(fn, provinces);
        addrEnable(fn, true);
        // Prefill theo tên đã lưu; tỉnh trống → mặc định Quảng Ngãi khi field cho phép auto-fill.
        // Tên không có trong danh mục (dữ liệu cũ) → để trống, không báo (user quyết 15/10/2026).
        const saved = norm(S.values[fn]);
        let item = saved ? provinces.find(p => p.name === saved) : null;
        if (!saved) {
          const fmeta = S.fieldByName[fn];
          if (!fmeta || fmeta.auto_fill !== false) item = provinces.find(p => p.name === DEFAULT_PROVINCE);
        }
        // Không markChanged lúc load — chỉ tô khi NV thao tác.
        if (item) addrCommit(fn, item, false);   // → fillWards(fn, prefill=true)
        else await fillWards(fn, true);
      }
      // Ô xã không có tỉnh cùng section: không có list → giữ khoá.
      boxes.filter(b => b.dataset.kind === "ward" && !b.dataset.provField).forEach(b => addrEnable(b.dataset.fieldname, false));
    }

    // Nạp list xã theo tỉnh đang chọn. prefill=true: lúc mở form (chọn lại xã đã lưu);
    // false: NV vừa đổi tỉnh → xoá xã + tô "đã đổi".
    async function fillWards(provFn, prefill) {
      const code = addrInput(provFn).dataset.code;
      const wards = await loadWards(code);
      if (addrInput(provFn).dataset.code !== code) return;   // NV đã đổi tỉnh khác trong lúc chờ
      for (const box of addrWards(provFn)) {
        const wf = box.dataset.fieldname;
        addrSetItems(wf, wards);
        addrEnable(wf, !!code);
        if (prefill) {
          const saved = norm(S.values[wf]);
          const item = saved ? wards.find(w => w.name === saved) : null;
          addrCommit(wf, item, false);
        } else {
          addrCommit(wf, null, true);
          markChanged({ fieldname: wf, widget: "Address Ward" });
        }
      }
    }

    // ---------- validation (mirrors server) ----------
    const VAL_PATTERNS = {
      Digits: [/^\d+$/, "chỉ gồm chữ số"],
      Phone: [/^0\d{9}$/, "số điện thoại VN 10 số, bắt đầu bằng 0"],
      Email: [/^[^@\s]+@[^@\s]+\.[^@\s]+$/, "email hợp lệ"],
      CCCD: [/^\d{12}$/, "đúng 12 chữ số"],
      CMND: [/^\d{9}$/, "đúng 9 chữ số"],
    };

    function validateField(f, value) {
      const val = (value == null ? "" : String(value)).trim();
      if (val === "") return "";
      const label = f.label || f.fieldname;
      if (f.min_length && val.length < f.min_length) return `${label}: tối thiểu ${f.min_length} ký tự`;
      if (f.max_length && val.length > f.max_length) return `${label}: tối đa ${f.max_length} ký tự`;
      const v = f.validation || "";
      if (!v) return "";
      if (v === "Past" || v === "Future") {
        const dv = new Date(val);
        if (isNaN(dv.getTime())) return "";
        const t = new Date(); t.setHours(0, 0, 0, 0); dv.setHours(0, 0, 0, 0);
        if (v === "Past" && dv > t) return `${label}: không được ở tương lai`;
        if (v === "Future" && dv < t) return `${label}: không được ở quá khứ`;
        return "";
      }
      if (v === "Regex") {
        if (!f.regex) return "";
        try { return new RegExp(f.regex).test(val) ? "" : `${label}: không đúng định dạng`; } catch { return ""; }
      }
      const spec = VAL_PATTERNS[v];
      if (!spec) return "";
      return spec[0].test(val) ? "" : `${label}: phải là ${spec[1]}`;
    }

    function todayISO() {
      const d = new Date();
      const p = n => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    }

    // Input attributes (maxlength / inputmode / digit-strip) from validation config.
    function valAttrs(f) {
      const v = f.validation || "";
      let maxlen = f.max_length || 0;
      if (v === "CCCD") maxlen = 12;
      else if (v === "CMND") maxlen = 9;
      else if (v === "Phone") maxlen = 10;
      let attrs = maxlen ? ` maxlength="${maxlen}"` : "";
      if (["Digits", "CCCD", "CMND", "Phone"].includes(v)) {
        attrs += ` inputmode="numeric" oninput="this.value=this.value.replace(/[^0-9]/g,'')"`;
      } else if (v === "Email") {
        attrs += ` inputmode="email"`;
      }
      return attrs;
    }

    // ---------- cam kết + chữ ký ----------
    // Ô ký tự viết (pointer events: chuột, bút, cảm ứng — chạy trong Zalo webview), không thư viện.
    // Xuất PNG nền trắng, thu về rộng tối đa 600px để file nhỏ (server giới hạn kích thước).
    const SignPad = (() => {
      let canvas, ctx, drawing = false, hasInk = false, last = null;
      function size() {
        const r = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.round(r.width * dpr);
        canvas.height = Math.round(r.height * dpr);
        ctx = canvas.getContext("2d");
        ctx.scale(dpr, dpr);
        ctx.lineWidth = 2.2; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#111827";
      }
      function pos(e) {
        const r = canvas.getBoundingClientRect();
        return { x: e.clientX - r.left, y: e.clientY - r.top };
      }
      function setInk(v) {
        hasInk = v;
        document.getElementById("sign_placeholder").style.display = v ? "none" : "";
      }
      function init() {
        canvas = document.getElementById("sign_pad");
        size();
        canvas.addEventListener("pointerdown", (e) => {
          drawing = true; last = pos(e); canvas.setPointerCapture(e.pointerId);
          ctx.beginPath(); ctx.arc(last.x, last.y, 1.1, 0, Math.PI * 2); ctx.fillStyle = "#111827"; ctx.fill();
          setInk(true); e.preventDefault();
        });
        canvas.addEventListener("pointermove", (e) => {
          if (!drawing) return;
          const p = pos(e);
          ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke();
          last = p; e.preventDefault();
        });
        const end = () => { drawing = false; };
        canvas.addEventListener("pointerup", end);
        canvas.addEventListener("pointercancel", end);
        // Xoay màn hình / đổi cỡ → vẽ lại khung trống (nét cũ bị co giãn nên xoá cho chắc).
        let w = window.innerWidth;
        window.addEventListener("resize", () => { if (window.innerWidth !== w) { w = window.innerWidth; clear(); } });
      }
      function clear() {
        if (!canvas) return;
        size(); setInk(false);
      }
      function toDataURL() {
        const maxW = 600;
        const scale = Math.min(1, maxW / canvas.width);
        const out = document.createElement("canvas");
        out.width = Math.round(canvas.width * scale);
        out.height = Math.round(canvas.height * scale);
        const o = out.getContext("2d");
        o.fillStyle = "#fff"; o.fillRect(0, 0, out.width, out.height);
        o.drawImage(canvas, 0, 0, out.width, out.height);
        return out.toDataURL("image/png");
      }
      return { init, clear, toDataURL, isEmpty: () => !hasInk };
    })();

    // ---------- Hồ sơ nộp kèm ----------
    // `checked` = tên hồ sơ đã tick (lần gửi trước / nháp). Tên đổi trong Setting → coi như chưa tick.
    function renderDocs(checked) {
      const docs = (S.config && S.config.documents) || [];
      const card = document.getElementById("doc_card");
      card.classList.toggle("hidden", !docs.length);
      const on = new Set(checked || []);
      document.getElementById("doc_list").innerHTML = docs.map((d, i) =>
        `<label class="commit-row" for="doc_${i}"><input type="checkbox" id="doc_${i}" data-doc="${esc(d.document)}"` +
        `${on.has(d.document) ? " checked" : ""}><span>${esc(d.document)}${d.required ? ' <span class="req">*</span>' : ""}</span></label>`
      ).join("");
    }
    function checkedDocs() {
      return [...document.querySelectorAll("#doc_list input:checked")].map(el => el.dataset.doc);
    }
    document.addEventListener("change", e => { if (e.target.closest && e.target.closest("#doc_list")) saveDraft(); });

    // Mỗi lần mở form: bỏ tick + xoá chữ ký (chữ ký đi theo đúng lần gửi này).
    // HR mở qua ?emp= → không bắt buộc; không ký thì server giữ chữ ký cũ của NV.
    let _signInit = false;
    function resetSignCard(isHR) {
      S.isHR = isHR;
      if (S.config && S.config.commitment_html) document.getElementById("commit_text").innerHTML = S.config.commitment_html;
      document.getElementById("f__commit").checked = false;
      document.getElementById("sign_req").style.display = isHR ? "none" : "";
      document.getElementById("sign_hint").textContent = ": Dùng ngón tay hoặc chuột ký vào khung dưới";
      // canvas phải đang hiển thị mới đo được kích thước → khởi tạo sau khi form hiện.
      requestAnimationFrame(() => {
        if (!_signInit) { SignPad.init(); _signInit = true; }
        SignPad.clear();
      });
    }

    function flashCard(id) {
      const el = document.getElementById(id);
      if (!el) return;
      el.classList.remove("card-error"); void el.offsetWidth; el.classList.add("card-error");
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => el.classList.remove("card-error"), 2500);
    }

    // ---------- submit ----------
    // Nhấp nháy viền đỏ TẤT CẢ field lỗi (tự tắt sau 2.5s hoặc khi NV nhập vào field đó).
    function flashFields(fieldnames) {
      (fieldnames || []).forEach(fn => {
        const fg = document.getElementById("fg_" + fn);
        if (!fg) return;
        fg.classList.remove("field-error");
        void fg.offsetWidth;                 // reflow → animation chạy lại mỗi lần bấm Gửi
        fg.classList.add("field-error");
        const el = document.getElementById("f_" + fn);
        const clear = () => fg.classList.remove("field-error");
        if (el) { el.addEventListener("input", clear, { once: true }); el.addEventListener("change", clear, { once: true }); }
        setTimeout(clear, 5500);
      });
    }

    async function submitForm() {
      const data = {};
      const missing = [];
      const missingFields = [];   // fieldname của field required chưa nhập — để nhấp nháy
      const invalid = [];
      const invalidFields = [];
      for (const sec of S.config.sections) {
        for (const f of sec.fields) {
          if (f.read_only) continue;
          if (!depVisible(f)) { data[f.fieldname] = ""; continue; }   // ô đang ẩn → gửi trống
          const v = currentValue(f);
          data[f.fieldname] = v;
          if (f.fieldname === CCCD_EXPIRE_FIELD) continue;   // tự tính, không bắt buộc / không kiểm "Future"
          if (f.fieldtype === "Table") {
            if (f.required && !v.length) { missing.push(f.label); missingFields.push(f.fieldname); continue; }
            const terr = tblValidate(f, v);
            if (terr) { invalid.push(terr); invalidFields.push(f.fieldname); }
            continue;
          }
          if ((f.required || f.depends_on) && (v === null || v === undefined || String(v).trim() === "")) {
            missing.push(f.label); missingFields.push(f.fieldname); continue;
          }
          const err = validateField(f, v);
          if (err) { invalid.push(err); invalidFields.push(f.fieldname); }
        }
      }
      if (missing.length) { toast("Vui lòng nhập: " + missing.join(", ")); flashFields(missingFields); return; }
      if (invalid.length) { toast(invalid.join(" · ")); flashFields(invalidFields); return; }
      const committed = document.getElementById("f__commit").checked;
      const signature = SignPad.isEmpty() ? "" : SignPad.toDataURL();
      if (!S.isHR) {
        if (!committed) { toast("Vui lòng tick ô cam kết thông tin khai đúng sự thật."); flashCard("sign_card"); return; }
        if (!signature) { toast("Vui lòng ký tên vào ô chữ ký."); flashCard("sign_card"); return; }
      }

      const btn = document.getElementById("submit_btn");
      btn.disabled = true; btn.textContent = "Đang gửi…";
      try {
        const r = await api(M.save, {
          employee_id: S.employee_id, data, code: S.verifyCode || "", unlock_code: S.unlockCode || "",
          commitment: committed ? 1 : 0, signature, documents: JSON.stringify(checkedDocs())
        });
        S.downloadToken = (r && r.download_token) || null;   // token tải phiếu ngay sau gửi (khi bị khoá)
        clearDraft(S.employee_id);   // gửi xong → bỏ nháp cục bộ
        document.getElementById("form_area").classList.add("hidden");
        document.getElementById("submitbar").classList.add("hidden");
        document.getElementById("picker_card").classList.add("hidden");
        document.getElementById("success_area").classList.remove("hidden");
        applySaveFileType();
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch (e) { toast(e.message); btn.disabled = false; btn.textContent = "Gửi thông tin"; }
    }

    // ---------- Lưu file thông tin đã gửi (PDF hoặc PNG theo Setting) ----------
    function saveFileType() { return (S.config && S.config.save_file_type) || "PDF"; }
    function isZalo() {
      return /Zalo/i.test(navigator.userAgent)
        || new URLSearchParams(location.search).get("zalo") === "1";  // test ngoài Zalo
    }

    // Đổi nhãn nút + gợi ý theo môi trường & loại file cấu hình.
    function applySaveFileType() {
      const btn = document.getElementById("save_btn");
      const hint = document.getElementById("save_hint");
      if (!btn) return;
      if (isZalo()) {
        // Zalo webview chặn tải/lưu file → hiện ảnh để user tự chụp màn hình.
        btn.textContent = "🖼 Xem ảnh để chụp màn hình";
        if (hint) hint.textContent = "Zalo không tải được file — nhấn nút để hiện ảnh, rồi chụp màn hình (screenshot) để lưu.";
      } else if (saveFileType() === "PNG") {
        btn.textContent = "🖼 Tải ảnh thông tin đã gửi";
        if (hint) hint.textContent = "Ảnh (PNG) được lưu tại thư mục Tải về / Downloads của thiết bị.";
      } else {
        btn.textContent = "📄 Tải PDF thông tin đã gửi";
        if (hint) hint.textContent = "File PDF được lưu tại thư mục Tải về / Downloads của thiết bị.";
      }
    }

    function downloadFile() {
      if (isZalo()) return showImageForSave();   // Zalo: luôn render ảnh để tự lưu
      return saveFileType() === "PNG" ? downloadImage() : downloadPdf();
    }

    // Zalo: tải bytes PNG rồi hiển thị <img> để user tự chụp màn hình lưu lại.
    async function showImageForSave() {
      const btn = document.getElementById("save_btn");
      const old = btn ? btn.textContent : "";
      if (btn) { btn.disabled = true; btn.textContent = "Đang tạo ảnh…"; }
      try {
        const res = await fetch(`/api/method/${M.image}?${receiptQuery()}`, { credentials: "same-origin" });
        if (!res.ok) throw new Error("Không tạo được ảnh");
        const blob = await res.blob();
        renderImageOverlay(URL.createObjectURL(blob));
      } catch (e) { toast(e.message || "Lỗi tạo ảnh"); }
      finally { if (btn) { btn.disabled = false; btn.textContent = old; } }
    }

    function renderImageOverlay(url) {
      const old = document.getElementById("img_save_overlay");
      if (old) old.remove();
      const ov = document.createElement("div");
      ov.id = "img_save_overlay";
      ov.innerHTML = `
        <style>
          #img_save_overlay{position:fixed;inset:0;z-index:1000000;background:#0C1424;
            display:flex;flex-direction:column;
            font-family:'Be Vietnam Pro',-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
          #img_save_overlay .is-bar{flex-shrink:0;display:flex;align-items:center;gap:10px;
            padding:12px 14px;background:#17233F;color:#fff;box-shadow:0 2px 10px rgba(0,0,0,.4)}
          #img_save_overlay .is-bar span{flex:1;font-size:13px;line-height:1.4}
          #img_save_overlay .is-bar b{color:#FBBF24}
          #img_save_overlay .is-close{flex-shrink:0;border:none;background:#2A3D66;color:#fff;
            font-size:14px;font-weight:700;padding:8px 14px;border-radius:9px}
          #img_save_overlay .is-scroll{flex:1;overflow:auto;-webkit-overflow-scrolling:touch;
            padding:14px;text-align:center}
          #img_save_overlay img{max-width:100%;height:auto;border-radius:8px;
            box-shadow:0 10px 30px rgba(0,0,0,.5);-webkit-touch-callout:default;user-select:none}
        </style>
        <div class="is-bar">
          <span>📸 <b>Chụp màn hình</b> (screenshot) để lưu lại thông tin.<br>Nếu ảnh dài, <b>kéo xuống</b> và chụp thêm cho đủ.</span>
          <button class="is-close" onclick="document.getElementById('img_save_overlay').remove()">✕ Đóng</button>
        </div>
        <div class="is-scroll"><img src="${url}" alt="Phiếu thông tin nhân viên"></div>`;
      document.body.appendChild(ov);
    }

    // PNG: tải thẳng ảnh về thiết bị (attachment).
    async function downloadImage() {
      const btn = document.getElementById("save_btn");
      const old = btn ? btn.textContent : "";
      if (btn) { btn.disabled = true; btn.textContent = "Đang tạo ảnh…"; }
      try {
        const res = await fetch(`/api/method/${M.image}?${receiptQuery()}`, { credentials: "same-origin" });
        if (!res.ok) throw new Error("Không tạo được ảnh");
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `${saveBaseName()}.png`;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      } catch (e) { toast(e.message || "Lỗi tạo ảnh"); }
      finally { if (btn) { btn.disabled = false; btn.textContent = old; } }
    }

    // Query string cho endpoint tải phiếu (kèm mã mở khoá + token phiên vừa gửi).
    function receiptQuery() {
      return new URLSearchParams({
        employee_id: S.employee_id,
        code: S.verifyCode || "",
        unlock_code: S.unlockCode || "",
        token: S.downloadToken || "",
      }).toString();
    }

    // Tên file tải về: "<mã NV> <họ tên> <yyyyMMdd_HHmm>".
    function saveBaseName() {
      const d = new Date();
      const p = n => String(n).padStart(2, "0");
      const stamp = `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`;
      return `${S.employee_id} ${(S.employee_name || "").trim()} ${stamp}`.replace(/\s+/g, " ").trim();
    }

    // ---------- PDF download (after submit) ----------
    async function downloadPdf() {
      const btn = document.getElementById("save_btn");
      const old = btn.textContent;
      btn.disabled = true; btn.textContent = "Đang tạo PDF…";
      try {
        const fd = new FormData();
        fd.append("csrf_token", window.csrf_token);
        fd.append("employee_id", S.employee_id);
        fd.append("code", S.verifyCode || "");
        fd.append("unlock_code", S.unlockCode || "");
        fd.append("token", S.downloadToken || "");
        const res = await fetch(`/api/method/${M.pdf}`, { method: "POST", credentials: "same-origin", body: fd });
        if (!res.ok) throw new Error("Không tạo được PDF");
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const d = new Date();
        const p = n => String(n).padStart(2, "0");
        const stamp = `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`;
        const fname = `${S.employee_id} ${(S.employee_name || "").trim()} ${stamp}.pdf`.replace(/\s+/g, " ").trim();
        const a = document.createElement("a");
        a.href = url; a.download = fname;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      } catch (e) { toast(e.message || "Lỗi tạo PDF"); }
      finally { btn.disabled = false; btn.textContent = old; }
    }

    // ---------- CCCD QR scanner (copied from employee-self-update) ----------
    let _qrStream = null, _qrRaf = null, _qrVideo = null, _qrCanvas = null, _qrCtx = null, _torchOn = false, _qrDetected = false;

    function _loadJsQr(cb) {
      if (window.jsQR) return cb();
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js";
      s.onload = cb;
      s.onerror = () => { document.getElementById("qr_status").textContent = "Không thể tải thư viện quét QR."; };
      document.head.appendChild(s);
    }

    function openQRScanner() {
      document.getElementById("qr_overlay").style.display = "flex";
      document.getElementById("qr_status").textContent = "Đang khởi động camera...";
      document.getElementById("qr_viewport").classList.remove("detected");
      _torchOn = false; _qrDetected = false;
      const torchBtn = document.getElementById("btn_torch");
      if (torchBtn) { torchBtn.textContent = "🔦 Bật đèn"; torchBtn.classList.remove("on"); torchBtn.style.display = "none"; }

      _loadJsQr(() => {
        navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }
        }).then(stream => {
          _qrStream = stream;
          _qrVideo = document.createElement("video");
          _qrVideo.srcObject = stream;
          _qrVideo.setAttribute("playsinline", "");
          _qrVideo.muted = true;
          document.getElementById("qr_viewport").appendChild(_qrVideo);
          _qrCanvas = document.createElement("canvas");
          _qrCanvas.style.display = "none";
          document.body.appendChild(_qrCanvas);
          _qrCtx = _qrCanvas.getContext("2d", { willReadFrequently: true });
          _qrVideo.play().then(() => {
            document.getElementById("qr_status").textContent = "Sẵn sàng quét...";
            const track = stream.getVideoTracks()[0];
            if (track) { try { const caps = track.getCapabilities(); if (caps && caps.torch && torchBtn) { torchBtn.style.display = ""; torchBtn._track = track; } } catch (e) { } }
            _qrScanLoop();
          });
        }).catch(err => {
          document.getElementById("qr_status").textContent = "Không thể mở camera: " + (err.message || err);
        });
      });
    }

    function _qrScanLoop() {
      if (_qrDetected || !_qrVideo || !_qrStream) return;
      const vw = _qrVideo.videoWidth, vh = _qrVideo.videoHeight;
      if (vw && vh) {
        const crops = [
          [0, 0, vw, vh],
          [vw * 0.2, vh * 0.2, vw * 0.6, vh * 0.6],
          [vw * 0.325, vh * 0.25, vw * 0.35, vh * 0.5],
        ];
        for (const [cx, cy, cw, ch] of crops) {
          const out = 900;
          _qrCanvas.width = out; _qrCanvas.height = Math.round(out * ch / cw);
          _qrCtx.drawImage(_qrVideo, cx, cy, cw, ch, 0, 0, _qrCanvas.width, _qrCanvas.height);
          const idd = _qrCtx.getImageData(0, 0, _qrCanvas.width, _qrCanvas.height);
          _boostContrast(idd);
          _qrCtx.putImageData(idd, 0, 0);
          const id2 = _qrCtx.getImageData(0, 0, _qrCanvas.width, _qrCanvas.height);
          const code = jsQR(id2.data, id2.width, id2.height, { inversionAttempts: "attemptBoth" });
          if (code) {
            const parsed = _parseVnCCCDQR(code.data);
            if (parsed) { _qrDetected = true; _onQRDetected(parsed); return; }
          }
        }
      }
      _qrRaf = requestAnimationFrame(_qrScanLoop);
    }

    function _boostContrast(imageData) {
      const d = imageData.data;
      let mn = 255, mx = 0;
      for (let i = 0; i < d.length; i += 4) { const g = (d[i] * 77 + d[i + 1] * 150 + d[i + 2] * 29) >> 8; if (g < mn) mn = g; if (g > mx) mx = g; }
      const range = mx - mn || 1;
      for (let i = 0; i < d.length; i += 4) { const g = Math.round((((d[i] * 77 + d[i + 1] * 150 + d[i + 2] * 29) >> 8) - mn) * 255 / range); d[i] = d[i + 1] = d[i + 2] = g; }
    }

    function toggleTorch() {
      const btn = document.getElementById("btn_torch");
      if (!btn || !btn._track) return;
      _torchOn = !_torchOn;
      btn._track.applyConstraints({ advanced: [{ torch: _torchOn }] }).catch(() => { });
      btn.textContent = _torchOn ? "🔦 Tắt đèn" : "🔦 Bật đèn";
      btn.classList.toggle("on", _torchOn);
    }

    function closeQRScanner() {
      _qrDetected = false;
      if (_qrRaf) { cancelAnimationFrame(_qrRaf); _qrRaf = null; }
      if (_torchOn && _qrStream) { const t = _qrStream.getVideoTracks()[0]; if (t) t.applyConstraints({ advanced: [{ torch: false }] }).catch(() => { }); }
      if (_qrStream) { _qrStream.getTracks().forEach(t => t.stop()); _qrStream = null; }
      if (_qrVideo) { _qrVideo.remove(); _qrVideo = null; }
      if (_qrCanvas) { _qrCanvas.remove(); _qrCanvas = null; }
      _qrCtx = null; _torchOn = false;
      document.getElementById("qr_overlay").style.display = "none";
    }

    function _onQRDetected(parsed) {
      document.getElementById("qr_viewport").classList.add("detected");
      document.getElementById("qr_status").textContent = "✅ Đọc mã QR thành công!";
      setTimeout(() => { closeQRScanner(); _fillFromCCCD(parsed); }, 500);
    }

    function _parseVnCCCDQR(text) {
      const parts = text.split("|");
      if (parts.length < 7) return null;
      const cccd = parts[0].trim();
      if (!/^\d{9,12}$/.test(cccd)) return null;
      function toISO(s) { s = s.trim(); if (s.length !== 8) return ""; return `${s.slice(4, 8)}-${s.slice(2, 4)}-${s.slice(0, 2)}`; }
      // QR format (pipe): [0]CCCD [1]CMND [2]tên [3]ngày sinh(ddmmyyyy) [4]giới tính [5]địa chỉ [6]ngày cấp(ddmmyyyy)
      return { cccd, cmnd: parts[1].trim(), dob: toISO(parts[3].trim()), issueDate: toISO(parts[6].trim()) };
    }

    // Tính ngày hết hạn CCCD theo Luật Căn cước 2023, dựa trên tuổi tại thời điểm cấp.
    // Mốc gia hạn: 14 / 25 / 40 / 60. Cấp trong vòng 2 năm trước 1 mốc → tính sang mốc kế tiếp.
    // Cấp từ 58 tuổi trở lên → không thời hạn (trả về "").
    function _cccdExpiryISO(dobISO, issueISO) {
      const dp = /^(\d{4})-(\d{2})-(\d{2})/.exec(dobISO || "");
      const ip = /^(\d{4})-(\d{2})-(\d{2})/.exec(issueISO || "");
      if (!dp || !ip) return "";
      const dob = { y: +dp[1], mo: +dp[2], d: +dp[3] };
      const iss = { y: +ip[1], mo: +ip[2], d: +ip[3] };
      let age = iss.y - dob.y;
      if (iss.mo < dob.mo || (iss.mo === dob.mo && iss.d < dob.d)) age--;
      const ms = [14, 25, 40, 60];
      let expAge = null;
      for (let i = 0; i < ms.length; i++) {
        if (age < ms[i]) {
          expAge = (age >= ms[i] - 2) ? (i + 1 < ms.length ? ms[i + 1] : null) : ms[i];
          break;
        }
      }
      if (expAge === null) return "";  // ≥ 60 hoặc cấp trong 2 năm trước 60 → không thời hạn
      const p = n => String(n).padStart(2, "0");
      const y = dob.y + expAge;
      const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
      const day = (dob.mo === 2 && dob.d === 29 && !leap) ? 28 : dob.d;   // 29/02 → 28/02 năm không nhuận
      return `${y}-${p(dob.mo)}-${p(day)}`;
    }

    // Tính lại ô ngày hết hạn CCCD từ ngày sinh + ngày cấp đang có trên form.
    // Thuật toán trùng api/employee/cccd_expiry.py và employee.js (sửa một nơi thì sửa cả ba).
    // Ngày sinh không có trên form → giữ nguyên ô; server tự tính khi gửi.
    function recalcCccdExpiry(byUser) {
      const exp = document.getElementById("f_" + CCCD_EXPIRE_FIELD);
      const iss = document.getElementById("f_" + CCCD_ISSUE_FIELD);
      const dob = document.getElementById("f_" + DOB_FIELD);
      if (!exp || !iss || !dob) return;
      const v = _cccdExpiryISO(dob.value, iss.value);
      if (exp.value === v) return;
      exp.value = v;
      if (byUser && S.fieldByName[CCCD_EXPIRE_FIELD]) markChanged(S.fieldByName[CCCD_EXPIRE_FIELD]);
    }

    // Set a configured field's value (if present) and flag it as changed.
    function _setCccdField(fieldname, value) {
      const f = S.fieldByName[fieldname];
      if (!f || f.read_only) return;
      const el = document.getElementById("f_" + fieldname);
      if (!el) return;
      el.value = value;
      markChanged(f);
    }

    // Fill: số CCCD, ngày cấp, số CMND cũ + ngày hết hạn (tự tính theo luật từ DOB + ngày cấp).
    function _fillFromCCCD(data) {
      if (data.cccd) _setCccdField(CCCD_FIELD, data.cccd);
      if (data.issueDate) _setCccdField(CCCD_ISSUE_FIELD, data.issueDate);
      if (data.cmnd && /^\d{9}$/.test(data.cmnd)) _setCccdField(CCCD_CMND_FIELD, data.cmnd);
      if (data.dob) _setCccdField(DOB_FIELD, data.dob);  // chỉ điền nếu field date_of_birth có trên form
      // "" = không thời hạn (cấp từ 58 tuổi) → vẫn ghi để xoá ngày cũ.
      _setCccdField(CCCD_EXPIRE_FIELD, _cccdExpiryISO(data.dob, data.issueDate));
      toast("Đã điền thông tin từ QR CCCD", true);
    }

    // ---------- P5: decode QR from a captured/selected photo (high-res still) ----------
    // TẠM KHÔNG DÙNG: nút "Chụp / chọn ảnh CCCD" đã được comment trong renderField.
    // Giữ nguyên các hàm dưới đây để bật lại nhanh khi cần (bỏ comment khối HTML đó).
    function _loadImage(file) {
      return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
        img.onerror = (e) => { URL.revokeObjectURL(url); reject(e); };
        img.src = url;
      });
    }

    // Try many crop rects × scales × (raw / contrast-boosted) on a still image.
    function _decodeImageForQR(img) {
      const W = img.naturalWidth, H = img.naturalHeight;
      if (!W || !H) return null;
      const cv = document.createElement("canvas");
      const cx = cv.getContext("2d", { willReadFrequently: true });

      const rects = [[0, 0, 1, 1], [0.2, 0.2, 0.6, 0.6], [0.3, 0.3, 0.4, 0.4], [0.375, 0.375, 0.25, 0.25]];
      // 3×3 overlapping grid of 40% tiles (QR may not be centered in the photo)
      for (let gy = 0; gy < 3; gy++) for (let gx = 0; gx < 3; gx++) rects.push([gx * 0.3, gy * 0.3, 0.4, 0.4]);

      for (const [fx, fy, fw, fh] of rects) {
        const sx = Math.floor(fx * W), sy = Math.floor(fy * H);
        const sw = Math.floor(fw * W), sh = Math.floor(fh * H);
        if (sw < 40 || sh < 40) continue;
        // upscale the crop so its shorter side ≈ 1200px (bounded)
        const scale = Math.min(3, Math.max(1, 1200 / Math.min(sw, sh)));
        const cw = Math.min(1800, Math.round(sw * scale)), ch = Math.min(1800, Math.round(sh * scale));
        cv.width = cw; cv.height = ch;
        cx.drawImage(img, sx, sy, sw, sh, 0, 0, cw, ch);
        let idata = cx.getImageData(0, 0, cw, ch);
        let code = jsQR(idata.data, cw, ch, { inversionAttempts: "attemptBoth" });
        if (!code) {
          _boostContrast(idata); cx.putImageData(idata, 0, 0);
          const id2 = cx.getImageData(0, 0, cw, ch);
          code = jsQR(id2.data, cw, ch, { inversionAttempts: "attemptBoth" });
        }
        if (code) { const p = _parseVnCCCDQR(code.data); if (p) return p; }
      }
      return null;
    }

    async function onCccdPhoto(ev) {
      const file = ev.target && ev.target.files && ev.target.files[0];
      ev.target.value = "";  // allow re-selecting the same file
      if (!file) return;
      toast("Đang đọc ảnh CCCD…");
      _loadJsQr(async () => {
        try {
          const img = await _loadImage(file);
          const parsed = _decodeImageForQR(img);
          if (parsed) _fillFromCCCD(parsed);
          else toast("Không đọc được QR từ ảnh. Chụp lại gần hơn, đủ sáng, lấy nét vào ô QR.");
        } catch (e) {
          toast("Không mở được ảnh. Thử lại.");
        }
      });
    }

// QR Login session helper (desk-wide, app_include_js).
// Only active for sessions opened by scanning a QR card (/qr-login sets the
// `qr_session` cookie = page to return to). Normal logins are untouched: the
// on_login hook deletes the cookie.
//   - 5 idle minutes -> sign out and go back to the scan screen
//   - warning overlay during the last 30 s, tap anywhere to stay
//   - one-tap "Log out" button (no confirm) + logout / session expiry -> scan screen
// See customize_erpnext/api/qr_login.py
(function () {
    const COOKIE = "qr_session";
    const IDLE_MS = 5 * 60 * 1000;
    const WARN_MS = 30 * 1000;

    function read_cookie() {
        const m = document.cookie.match(new RegExp("(?:^|;\\s*)" + COOKIE + "=([^;]*)"));
        if (!m) return null;
        try {
            let v = decodeURIComponent(m[1]);
            if (v.indexOf("%2F") === 0) v = decodeURIComponent(v); // tolerate double encoding
            return v;
        } catch (e) {
            return null;
        }
    }

    const next = read_cookie();
    if (!next) return;

    const login_url = "/qr-login?next=" + encodeURIComponent(next);
    // Shared by every tab of this browser: working in one tab keeps the others alive
    // (each tab runs its own timer; without this an idle tab logs out the busy one)
    const LS_KEY = "qr_login_last_active";
    let last_active = Date.now();
    let last_saved = 0;
    let logging_out = false;
    let $overlay = null;

    function shared_last_active() {
        let stored = 0;
        try {
            stored = parseInt(localStorage.getItem(LS_KEY), 10) || 0;
        } catch (e) { }
        return Math.max(last_active, stored);
    }

    function idle_ms() {
        return Date.now() - shared_last_active();
    }

    function go_to_scan() {
        window.location.replace(login_url);
    }

    function logout() {
        if (logging_out) return;
        logging_out = true;
        const headers = { "Accept": "application/json" };
        if (window.frappe && frappe.csrf_token) headers["X-Frappe-CSRF-Token"] = frappe.csrf_token;
        fetch("/api/method/logout", { method: "POST", credentials: "same-origin", headers: headers })
            .catch(function () { })
            .finally(go_to_scan);
    }

    function mark_active() {
        last_active = Date.now();
        if (last_active - last_saved > 5000) {
            last_saved = last_active;
            try {
                localStorage.setItem(LS_KEY, String(last_active));
            } catch (e) { }
        }
        if ($overlay) hide_overlay();
    }

    // Capture-phase handler for input events. If the idle limit has already passed
    // (tablet screen was off, timers paused), the first tap of the NEXT person must
    // not revive the previous session or click anything: swallow it and sign out.
    function on_input(e) {
        if (logging_out || idle_ms() >= IDLE_MS) {
            if (e.cancelable) e.preventDefault();
            e.stopImmediatePropagation();
            logout();
            return;
        }
        mark_active();
    }

    function show_overlay(seconds_left) {
        if (!$overlay) {
            $overlay = document.createElement("div");
            $overlay.className = "qr-idle-overlay";
            $overlay.setAttribute("role", "alertdialog");
            $overlay.innerHTML =
                '<div class="qr-idle-box">' +
                '<div class="qr-idle-title"></div>' +
                '<div class="qr-idle-count"></div>' +
                '<div class="qr-idle-hint"></div>' +
                "</div>";
            $overlay.querySelector(".qr-idle-title").textContent = __("Still there?");
            $overlay.querySelector(".qr-idle-hint").textContent = __("Tap anywhere to continue");
            document.body.appendChild($overlay);
        }
        $overlay.querySelector(".qr-idle-count").textContent =
            __("You will be signed out in {0} s", [seconds_left]);
    }

    function hide_overlay() {
        if ($overlay) {
            $overlay.remove();
            $overlay = null;
        }
    }

    function tick() {
        if (logging_out) return;
        const idle = idle_ms();
        if (idle >= IDLE_MS) {
            logout();
        } else if (idle >= IDLE_MS - WARN_MS) {
            show_overlay(Math.ceil((IDLE_MS - idle) / 1000));
        } else if ($overlay) {
            hide_overlay(); // activity in another tab
        }
    }

    function add_pill() {
        if (document.querySelector(".qr-session-pill")) return;
        const pill = document.createElement("div");
        pill.className = "qr-session-pill";
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = __("Log out");
        btn.addEventListener("click", logout);
        pill.appendChild(btn);
        document.body.appendChild(pill);
    }

    function add_style() {
        const css = `
.qr-idle-overlay { position: fixed; inset: 0; z-index: 2000; background: rgba(17, 24, 39, .82);
    display: flex; align-items: center; justify-content: center; padding: 16px; }
.qr-idle-box { background: #fff; color: #1f2937; border-radius: 16px; padding: 32px 40px;
    text-align: center; max-width: 520px; }
.qr-idle-title { font-size: 32px; font-weight: 700; margin-bottom: 12px; }
.qr-idle-count { font-size: 22px; margin-bottom: 8px; }
.qr-idle-hint { font-size: 18px; color: #4b5563; }
.qr-session-pill { position: fixed; left: 12px; bottom: 64px; z-index: 1040; } /* above the sidebar user avatar */
.qr-session-pill button { min-height: 48px; padding: 0 22px; font-size: 16px; font-weight: 700;
    border: 0; border-radius: 999px; background: #1f2937; color: #fff; cursor: pointer;
    box-shadow: 0 2px 10px rgba(0,0,0,.25); }
@media print { .qr-session-pill, .qr-idle-overlay { display: none !important; } }`;
        const style = document.createElement("style");
        style.textContent = css;
        document.head.appendChild(style);
    }

    function patch_app() {
        if (!window.frappe || !frappe.app) return;
        // logout / session-expired dialog -> scan screen instead of /login
        frappe.app.redirect_to_login = go_to_scan;
        // shared device: no "Are you sure?" step
        frappe.app.logout = logout;
    }

    function init() {
        if (!window.frappe || !frappe.session || frappe.session.user === "Guest") return;
        add_style();
        add_pill();
        patch_app();
        // not passive: on_input may need to cancel a tap that arrives after expiry
        ["pointerdown", "touchstart", "mousedown", "click", "keydown"].forEach(function (ev) {
            window.addEventListener(ev, on_input, { capture: true, passive: false });
        });
        ["wheel", "scroll"].forEach(function (ev) {
            window.addEventListener(ev, function () {
                if (!logging_out && idle_ms() < IDLE_MS) mark_active();
            }, { capture: true, passive: true });
        });
        // screen back on / tab shown again: check right away, not on the next tick
        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState === "visible") tick();
        });
        mark_active();
        setInterval(tick, 1000);
    }

    if (window.frappe && frappe.app) {
        init();
    } else {
        $(document).on("app_ready", init);
    }
})();

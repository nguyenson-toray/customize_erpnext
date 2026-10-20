/* Employee quiz page — /quiz?f=<slug>   (preview for HR: &preview=1)
 *
 * Guest page, mobile first. Flow:
 *   intro + pick yourself -> 2-digit code -> start/continue -> answer -> submit -> result
 * Talks to customize_erpnext.api.employee_quiz.quiz_api. No `frappe` object here:
 * calls go through FormData + csrf_token (Frappe checks CSRF from the form body).
 * UI is Vietnamese only, hard-coded on purpose (user decision 20/10/2026: workers'
 * page, no translation layer) — an exception to the app's English-first rule.
 */
(function () {
	"use strict";

	const API = "customize_erpnext.api.employee_quiz.quiz_api.";
	const params = new URLSearchParams(location.search);
	const SLUG = params.get("f") || "";
	const PREVIEW = params.get("preview") === "1";
	const SAVE_DELAY_MS = 2500;
	const WARN_SECONDS = 60; // timer turns red + one "1 minute left" warning
	const MAX_RESULTS = 30;

	const S = {
		quiz: null,
		employees: null,
		employee: null, // {id, name, group}
		code: "",
		verify: null, // verify() result
		attempt: null, // start() payload
		answers: {},
		result: null,
		deadlineAt: null, // performance.now() ms
		timer: null,
		warned1m: false, // the 1-minute warning was shown for this attempt
		saveTimer: null,
		saveState: "", // "", "saving", "saved", "error"
		submitting: false,
	};

	const app = document.getElementById("app");

	// ------------------------------------------------------------ utilities

	function fmt(text, args) {
		let out = text;
		(args || []).forEach((a, i) => (out = out.split("{" + i + "}").join(a)));
		return out;
	}

	function esc(v) {
		return String(v == null ? "" : v).replace(/[&<>"']/g, (c) =>
			({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
		);
	}

	function fold(s) {
		return String(s || "")
			.replace(/đ/g, "d")
			.replace(/Đ/g, "D")
			.normalize("NFD")
			.replace(/[̀-ͯ]/g, "")
			.toLowerCase();
	}

	function num(v) {
		const n = Number(v || 0);
		return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, "");
	}

	function store(key, value) {
		try {
			if (value === undefined) localStorage.removeItem(key);
			else localStorage.setItem(key, JSON.stringify(value));
		} catch (e) {
			/* private mode / storage blocked: the server copy still exists */
		}
	}

	function load(key) {
		try {
			return JSON.parse(localStorage.getItem(key) || "null");
		} catch (e) {
			return null;
		}
	}

	async function call(method, args, opts) {
		const fd = new FormData();
		fd.append("csrf_token", window.csrf_token || "");
		fd.append("_lang", "vi");
		Object.entries(args || {}).forEach(([k, v]) =>
			fd.append(k, v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v))
		);
		let res;
		try {
			res = await fetch("/api/method/" + API + method, {
				method: "POST",
				credentials: "same-origin",
				body: fd,
				keepalive: !!(opts && opts.keepalive),
			});
		} catch (e) {
			const err = new Error(fmt("Mất kết nối. Kiểm tra mạng rồi thử lại."));
			err.network = true;
			throw err;
		}
		let data = {};
		try {
			data = await res.json();
		} catch (e) {
			/* non-JSON error page */
		}
		if (!res.ok || data.exc || data.exc_type) {
			let msg = "";
			try {
				msg = JSON.parse(JSON.parse(data._server_messages || "[]")[0]).message;
			} catch (e) {
				/* no server message */
			}
			throw new Error(msg || fmt("Có lỗi xảy ra. Vui lòng thử lại."));
		}
		return data.message;
	}

	let toastTimer = null;
	function toast(msg, kind) {
		const el = document.getElementById("toast");
		el.textContent = msg;
		el.className = "toast show " + (kind || "");
		clearTimeout(toastTimer);
		toastTimer = setTimeout(() => (el.className = "toast"), 3500);
	}

	function modal(html, actions) {
		const el = document.getElementById("modal");
		el.innerHTML = `<div class="modal-card">${html}<div class="modal-actions"></div></div>`;
		const bar = el.querySelector(".modal-actions");
		actions.forEach((a) => {
			const b = document.createElement("button");
			b.className = a.primary ? "btn btn-primary" : "btn btn-ghost";
			b.textContent = a.label;
			b.onclick = () => {
				closeModal();
				a.onClick && a.onClick();
			};
			bar.appendChild(b);
		});
		el.classList.remove("hidden");
	}

	function closeModal() {
		document.getElementById("modal").classList.add("hidden");
	}

	function header(sub) {
		return `<header class="top">
			<img class="logo" src="/assets/customize_erpnext/images/logo_white.png" alt="">
			<div class="company">${esc(window.COMPANY)}</div>
			<h1>${esc(S.quiz ? S.quiz.title : fmt("Bài kiểm tra"))}</h1>
			${sub ? `<div class="sub">${sub}</div>` : ""}
		</header>`;
	}

	function render(html) {
		app.innerHTML = html;
		window.scrollTo(0, 0);
	}

	function fatal(msg) {
		render(`${header()}<div class="card center"><div class="big-icon">⚠️</div><p>${esc(msg)}</p></div>`);
	}

	// ----------------------------------------------------------- 1. intro

	function facts() {
		const q = S.quiz;
		const items = [fmt("{0} câu hỏi", [q.question_count])];
		items.push(q.time_limit_minutes ? fmt("{0} phút", [q.time_limit_minutes]) : fmt("Không giới hạn thời gian"));
		if (q.max_attempts) items.push(q.max_attempts === 1 ? fmt("Làm 1 lần") : fmt("Làm tối đa {0} lần", [q.max_attempts]));
		items.push(fmt("Đạt từ {0}%", [num(q.pass_percentage)]));
		return `<div class="facts">${items.map((t) => `<span>${esc(t)}</span>`).join("")}</div>`;
	}

	async function boot() {
		if (!SLUG) return fatal(fmt("Link bài kiểm tra không đúng."));
		try {
			S.quiz = await call("get_quiz", { slug: SLUG });
		} catch (e) {
			return fatal(e.message);
		}
		document.title = S.quiz.title;
		if (PREVIEW && S.quiz.can_preview) return startPreview();
		if (!S.quiz.is_open) {
			return render(`${header()}
				<div class="card">${S.quiz.description ? `<div class="desc">${S.quiz.description}</div>` : ""}${facts()}</div>
				<div class="card center"><div class="big-icon">🔒</div><p class="lead">${esc(S.quiz.message)}</p></div>`);
		}
		try {
			S.employees = await call("get_employees", { slug: SLUG });
		} catch (e) {
			return fatal(e.message);
		}
		S.employees.forEach((e) => (e._q = fold(e.id + " " + e.name)));
		showIdentify();
	}

	// ------------------------------------------------- 2. pick yourself

	function showIdentify() {
		resetAttempt();
		S.employee = null;
		S.code = "";
		S.verify = null;
		render(`${header()}
			<div class="card">${S.quiz.description ? `<div class="desc">${S.quiz.description}</div>` : ""}${facts()}</div>
			<div class="card" id="who">
				<h2><span class="step">1</span>${fmt("Bạn là ai?")}</h2>
				<label class="fl" for="search">${fmt("Gõ mã nhân viên hoặc họ tên")}</label>
				<input id="search" class="input" type="search" autocomplete="off" autocapitalize="off"
					spellcheck="false" enterkeyhint="search" placeholder="${esc(fmt("VD: 0148 hoặc Nguyễn Văn A"))}">
				<div id="results" class="results"></div>
			</div>`);
		const input = document.getElementById("search");
		input.addEventListener("input", () => renderResults(input.value));
		renderResults("");
	}

	function matches(q) {
		const tokens = fold(q).split(/\s+/).filter(Boolean);
		if (!tokens.length) return [];
		return S.employees.filter((e) => tokens.every((t) => e._q.includes(t)));
	}

	function renderResults(q) {
		const box = document.getElementById("results");
		if (!q.trim()) {
			box.innerHTML = `<div class="hint">${fmt("Có {0} người được làm bài này.", [S.employees.length])}</div>`;
			return;
		}
		const list = matches(q);
		if (!list.length) {
			box.innerHTML = `<div class="hint warn">${fmt("Không tìm thấy. Có thể bạn không có trong danh sách làm bài này — hãy hỏi HR.")}</div>`;
			return;
		}
		box.innerHTML =
			list
				.slice(0, MAX_RESULTS)
				.map(
					(e, i) => `<button type="button" class="person" data-i="${i}">
						<span class="pid">${esc(e.id)}</span>
						<span class="pname">${esc(e.name)}</span>
						<span class="pdept">${esc(e.group)}</span>
					</button>`
				)
				.join("") +
			(list.length > MAX_RESULTS
				? `<div class="hint">${fmt("Đang hiện {0}/{1} người. Gõ thêm để lọc.", [MAX_RESULTS, list.length])}</div>`
				: "");
		box.querySelectorAll(".person").forEach((b) => (b.onclick = () => pick(list[Number(b.dataset.i)])));
	}

	function pick(emp) {
		S.employee = emp;
		const who = document.getElementById("who");
		who.innerHTML = `
			<h2><span class="step">1</span>${fmt("Bạn là ai?")}</h2>
			<div class="picked">
				<div><div class="pname">${esc(emp.name)}</div><div class="pmeta">${esc(emp.id)}${emp.group ? " · " + esc(emp.group) : ""}</div></div>
			</div>`; // no "change" button: to pick someone else, reload the page
		if (S.quiz.require_code === false) {
			// Quiz without verification: picking your name is enough.
			// (=== false: a server without this flag still asks for the code.)
			who.insertAdjacentHTML(
				"afterend",
				`<div class="card" id="verify">
					<h2><span class="step">2</span>${fmt("Xác nhận bạn là ai")}</h2>
					<div id="verify-msg"></div>
				</div>`
			);
			doVerify("");
			return;
		}
		who.insertAdjacentHTML(
			"afterend",
			`<div class="card" id="verify">
				<h2><span class="step">2</span>${fmt("Xác nhận bạn là ai")}</h2>
				<label class="fl" for="code">${fmt("Nhập 2 số ngày sinh của bạn")}</label>
				<input id="code" class="input code" type="text" inputmode="numeric" pattern="[0-9]*"
					maxlength="2" autocomplete="off" placeholder="••">
				<div class="hint">${fmt("Sinh ngày 05/09 → nhập 05. Nếu không được, nhập mã do HR cung cấp.")}</div>
				<div id="verify-msg"></div>
			</div>`
		);
		const code = document.getElementById("code");
		code.addEventListener("input", () => {
			code.value = code.value.replace(/\D/g, "").slice(0, 2);
			document.getElementById("verify-msg").innerHTML = "";
			if (code.value.length === 2) doVerify(code.value);
		});
		code.focus();
	}

	async function doVerify(code) {
		const msg = document.getElementById("verify-msg");
		const input = document.getElementById("code");
		msg.innerHTML = `<div class="hint"><span class="spinner sm"></span> ${fmt("Đang kiểm tra…")}</div>`;
		try {
			const r = await call("verify", { slug: SLUG, employee: S.employee.id, code });
			if (!r.valid) {
				msg.innerHTML = `<div class="hint error">${fmt("Sai mã. Thử lại hoặc hỏi HR mã để nhập.")}</div>`;
				input.value = "";
				input.classList.add("shake");
				setTimeout(() => input.classList.remove("shake"), 500);
				input.focus();
				return;
			}
			S.code = code;
			S.verify = r;
			if (input) input.blur();
			showReady();
		} catch (e) {
			msg.innerHTML = `<div class="hint error">${esc(e.message)}</div>`;
		}
	}

	function showReady() {
		const v = S.verify;
		const noneLeft = v.attempts_left === 0 && !v.in_progress;
		const card = document.getElementById("verify");
		let body;
		if (noneLeft) {
			body = `<p class="lead">${fmt("Bạn đã làm bài này rồi, không còn lượt làm.")}</p>`;
		} else {
			const lines = [];
			if (v.attempts_used) lines.push(fmt("Bạn đã làm bài này {0} lần.", [v.attempts_used]));
			if (v.attempts_left !== null && v.attempts_left !== undefined && !v.in_progress)
				lines.push(fmt("Số lần còn được làm: {0}", [v.attempts_left]));
			if (S.quiz.time_limit_minutes && !v.in_progress)
				lines.push(fmt("Đồng hồ bắt đầu chạy khi bạn bấm Bắt đầu và không dừng lại."));
			body = `<p class="lead ok">✓ ${esc(v.employee_name)}</p>${lines.map((l) => `<p class="muted">${esc(l)}</p>`).join("")}`;
		}
		card.innerHTML = `<h2><span class="step">2</span>${fmt("Xác nhận bạn là ai")}</h2>${body}`;
		app.insertAdjacentHTML(
			"beforeend",
			noneLeft
				? ""
				: `<div class="bottom-bar"><button class="btn btn-primary" id="go">${
						v.in_progress ? fmt("Làm tiếp bài") : fmt("Bắt đầu làm bài")
					}</button></div>`
		);
		const go = document.getElementById("go");
		if (go) go.onclick = () => startAttempt(go);
	}

	// --------------------------------------------------------- 3. attempt

	async function startAttempt(btn) {
		btn.disabled = true;
		btn.innerHTML = `<span class="spinner sm light"></span>`;
		try {
			const a = await call("start", { slug: SLUG, employee: S.employee.id, code: S.code });
			const local = load("tiqn_quiz_" + a.response) || {};
			S.answers = Object.assign({}, a.answers || {}, local);
			openAttempt(a);
		} catch (e) {
			btn.disabled = false;
			btn.textContent = S.verify.in_progress ? fmt("Làm tiếp bài") : fmt("Bắt đầu làm bài");
			toast(e.message, "error");
		}
	}

	async function startPreview() {
		try {
			const a = await call("preview_start", { slug: SLUG });
			S.answers = {};
			openAttempt(a);
		} catch (e) {
			fatal(e.message);
		}
	}

	function openAttempt(a) {
		S.attempt = a;
		S.deadlineAt = a.seconds_left === null || a.seconds_left === undefined ? null : performance.now() + a.seconds_left * 1000;
		// Opened with ≤ 1 minute left (resume, very short quiz): the red timer is enough.
		S.warned1m = S.deadlineAt !== null && a.seconds_left <= WARN_SECONDS;
		renderQuiz();
		if (S.deadlineAt !== null) {
			tick();
			S.timer = setInterval(tick, 500);
		}
		window.addEventListener("beforeunload", onLeave);
		document.addEventListener("visibilitychange", onHidden);
	}

	function resetAttempt() {
		clearInterval(S.timer);
		clearTimeout(S.saveTimer);
		S.timer = S.saveTimer = null;
		S.attempt = null;
		S.answers = {};
		S.result = null;
		S.saveState = "";
		S.submitting = false;
		window.removeEventListener("beforeunload", onLeave);
		document.removeEventListener("visibilitychange", onHidden);
		closeModal();
	}

	function onLeave(e) {
		e.preventDefault();
		e.returnValue = "";
	}

	function onHidden() {
		if (document.visibilityState === "hidden" && S.saveTimer) {
			clearTimeout(S.saveTimer);
			saveNow(true);
		}
	}

	function answered(q) {
		const v = S.answers[q.key];
		return v !== undefined && String(v).trim() !== "";
	}

	function renderQuiz() {
		const a = S.attempt;
		const qs = a.questions;
		const cards = qs
			.map((q, i) => {
				const multi = q.type === "Multiple choice";
				const val = S.answers[q.key] || "";
				const chosen = val.split(",");
				const body = q.options
					.map(
						(o) => `<label class="opt">
							<input type="${multi ? "checkbox" : "radio"}" name="q_${esc(q.key)}" value="${esc(o.key)}"
								data-key="${esc(q.key)}" ${chosen.includes(o.key) ? "checked" : ""}>
							<span class="mark"></span><span class="otext">${esc(o.text)}</span>
						</label>`
					)
					.join("");
				return `<section class="card q" id="q_${esc(q.key)}" data-key="${esc(q.key)}">
					<div class="qhead">
						<span class="qno">${fmt("Câu {0}", [i + 1])}${q.required ? ' <span class="req">*</span>' : ""}</span>
						${q.points ? `<span class="qpts">${fmt("{0} điểm", [num(q.points)])}</span>` : ""}
					</div>
					<div class="qtext rich">${q.question}</div>
					${q.image ? `<img class="qimg" src="${esc(q.image)}" alt="" loading="lazy">` : ""}
					${multi ? `<div class="qhint">${fmt("Chọn tất cả đáp án đúng")}</div>` : ""}
					<div class="answers">${body}</div>
					<div class="qerr">${fmt("Vui lòng trả lời câu này")}</div>
				</section>`;
			})
			.join("");

		render(`
			<div class="quizbar">
				<div class="qb-row">
					<div class="qb-who">${esc(a.employee_name)}</div>
					<div class="qb-save" id="save-state"></div>
					${S.deadlineAt !== null ? `<div class="timer" id="timer">--:--</div>` : ""}
				</div>
				<div class="progress"><div id="progress-fill"></div></div>
				<div class="qb-count" id="progress-text"></div>
			</div>
			${PREVIEW ? `<div class="preview-banner">${fmt("Xem thử — bài làm không được lưu")}</div>` : ""}
			<div class="qtitle">${esc(S.quiz.title)}</div>
			${cards}
			${a.signature ? signCardHtml(a.signature) : ""}
			<div class="bottom-bar"><button class="btn btn-primary" id="submit">${fmt("Nộp bài")}</button></div>`);

		app.querySelectorAll("input[data-key]").forEach((el) => el.addEventListener("change", onPick));
		document.getElementById("submit").onclick = () => trySubmit(false);
		if (a.signature) {
			// The canvas must be on screen to measure it.
			requestAnimationFrame(() => SignPad.init(document.getElementById("sign_pad")));
			document.getElementById("sign_clear").onclick = () => SignPad.clear();
			const commit = document.getElementById("sign_commit");
			if (commit) commit.addEventListener("change", () => document.getElementById("sign_card").classList.remove("missing"));
		}
		updateProgress();
		renderSaveState();
	}

	function onPick(e) {
		const key = e.target.dataset.key;
		const card = document.getElementById("q_" + key);
		const picked = Array.from(card.querySelectorAll("input:checked")).map((i) => i.value);
		S.answers[key] = picked.join(",");
		card.classList.remove("missing");
		changed();
	}

	function changed() {
		updateProgress();
		if (PREVIEW) return;
		store("tiqn_quiz_" + S.attempt.response, S.answers);
		clearTimeout(S.saveTimer);
		S.saveTimer = setTimeout(() => saveNow(false), SAVE_DELAY_MS);
	}

	async function saveNow(keepalive) {
		S.saveTimer = null;
		if (!S.attempt || PREVIEW || S.submitting) return;
		S.saveState = "saving";
		renderSaveState();
		try {
			const r = await call("save_progress", { response: S.attempt.response, answers: S.answers }, { keepalive });
			S.saveState = r.saved ? "saved" : "";
			if (r.seconds_left !== null && r.seconds_left !== undefined && S.deadlineAt !== null) {
				S.deadlineAt = performance.now() + r.seconds_left * 1000; // re-sync with the server clock
			}
		} catch (e) {
			S.saveState = "error";
		}
		renderSaveState();
	}

	function renderSaveState() {
		const el = document.getElementById("save-state");
		if (!el) return;
		const labels = { saving: fmt("Đang lưu…"), saved: fmt("Đã lưu"), error: fmt("Chưa lưu — kiểm tra mạng") };
		el.textContent = labels[S.saveState] || "";
		el.className = "qb-save " + S.saveState;
	}

	function updateProgress() {
		const qs = S.attempt.questions;
		const done = qs.filter(answered).length;
		document.getElementById("progress-fill").style.width = (qs.length ? (done / qs.length) * 100 : 0) + "%";
		document.getElementById("progress-text").textContent = fmt("Đã trả lời {0}/{1} câu", [done, qs.length]);
	}

	function tick() {
		const el = document.getElementById("timer");
		if (S.deadlineAt === null || !el) return;
		const left = Math.max(0, Math.round((S.deadlineAt - performance.now()) / 1000));
		el.textContent = String(Math.floor(left / 60)).padStart(2, "0") + ":" + String(left % 60).padStart(2, "0");
		el.classList.toggle("danger", left <= WARN_SECONDS);
		if (left > 0 && left <= WARN_SECONDS && !S.warned1m && !S.submitting) {
			S.warned1m = true;
			warnOneMinute();
		}
		if (left === 0 && !S.submitting) {
			clearInterval(S.timer);
			S.timer = null;
			modal(`<div class="big-icon">⏰</div><p class="lead">${fmt("Hết giờ. Đang nộp bài…")}</p>`, []);
			submit(true);
		}
	}

	function warnOneMinute() {
		if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
		const msg = "Còn 1 phút! Hãy kiểm tra lại và bấm Nộp bài. Hết giờ hệ thống sẽ tự nộp.";
		// Do not cover a dialog already open (e.g. "Nộp bài?") — a toast is enough then.
		if (!document.getElementById("modal").classList.contains("hidden")) return toast(msg, "error");
		modal(`<div class="big-icon">⏰</div><p class="lead">${fmt(msg)}</p>`, [
			{ label: "Tiếp tục làm bài", primary: true },
		]);
	}

	function trySubmit() {
		const qs = S.attempt.questions;
		const missing = qs.filter((q) => q.required && !answered(q));
		app.querySelectorAll(".q.missing").forEach((c) => c.classList.remove("missing"));
		if (missing.length) {
			missing.forEach((q) => document.getElementById("q_" + q.key).classList.add("missing"));
			document.getElementById("q_" + missing[0].key).scrollIntoView({ block: "center", behavior: "smooth" });
			toast(fmt("Còn {0} câu bắt buộc chưa trả lời", [missing.length]), "error");
			return;
		}
		const sign = S.attempt.signature;
		if (sign) {
			const commit = document.getElementById("sign_commit");
			const msg = commit && !commit.checked ? fmt("Vui lòng tick ô cam kết.")
				: SignPad.isEmpty() ? fmt("Vui lòng ký tên vào ô chữ ký.") : "";
			if (msg) {
				const card = document.getElementById("sign_card");
				card.classList.add("missing");
				card.scrollIntoView({ block: "center", behavior: "smooth" });
				toast(msg, "error");
				return;
			}
		}
		const done = qs.filter(answered).length;
		modal(
			`<p class="lead">${fmt("Nộp bài?")}</p>
			 <p class="muted">${fmt("Bạn đã trả lời {0}/{1} câu. Sau khi nộp sẽ không sửa được nữa.", [done, qs.length])}</p>`,
			[
				{ label: fmt("Làm tiếp") },
				{ label: fmt("Nộp bài"), primary: true, onClick: () => submit(false) },
			]
		);
	}

	async function submit(auto) {
		if (S.submitting) return;
		S.submitting = true;
		clearTimeout(S.saveTimer);
		const btn = document.getElementById("submit");
		if (btn) {
			btn.disabled = true;
			btn.innerHTML = `<span class="spinner sm light"></span>`;
		}
		try {
			const r = PREVIEW
				? await call("preview_submit", { slug: SLUG, answers: S.answers })
				: await call("submit", {
						response: S.attempt.response,
						answers: S.answers,
						// Time-up auto-submit sends whatever was signed; the server does not insist.
						signature: S.attempt.signature && !SignPad.isEmpty() ? SignPad.toDataURL() : "",
						commitment: document.getElementById("sign_commit")?.checked ? 1 : 0,
					});
			if (!PREVIEW) store("tiqn_quiz_" + S.attempt.response, undefined);
			clearInterval(S.timer);
			closeModal();
			window.removeEventListener("beforeunload", onLeave);
			document.removeEventListener("visibilitychange", onHidden);
			showResult(r);
		} catch (e) {
			S.submitting = false;
			if (btn) {
				btn.disabled = false;
				btn.textContent = fmt("Nộp bài");
			}
			modal(`<div class="big-icon">📶</div><p class="lead">${fmt("Chưa nộp được bài")}</p><p class="muted">${esc(e.message)}</p>
				<p class="muted">${fmt("Bài làm vẫn được giữ trên điện thoại. Kiểm tra mạng rồi thử lại.")}</p>`, [
				{ label: fmt("Thử lại"), primary: true, onClick: () => submit(auto) },
			]);
		}
	}

	// ------------------------------------------------------------ signature
	// Same pad as /employee-self-update-info: pointer events (mouse, pen, touch — works in
	// the Zalo webview), no library; PNG on white, at most 600px wide (server size limit).

	function signCardHtml(sign) {
		return `<section class="card sign" id="sign_card">
			<div class="qhead"><span class="qno">${fmt("Cam kết & chữ ký")} <span class="req">*</span></span></div>
			${sign.commitment ? `<label class="commit-row"><input type="checkbox" id="sign_commit">
				<span>${esc(sign.commitment)}</span></label>` : ""}
			<div class="sign-wrap">
				<canvas id="sign_pad"></canvas>
				<div class="sign-placeholder" id="sign_placeholder">${fmt("Ký tên tại đây")}</div>
			</div>
			<button type="button" class="link" id="sign_clear">${fmt("↺ Xoá, ký lại")}</button>
			<div class="qerr">${fmt("Vui lòng tick cam kết và ký tên")}</div>
		</section>`;
	}

	const SignPad = (() => {
		let canvas, ctx, drawing = false, hasInk = false, last = null;
		function size() {
			const r = canvas.getBoundingClientRect();
			const dpr = window.devicePixelRatio || 1;
			canvas.width = Math.round(r.width * dpr);
			canvas.height = Math.round(r.height * dpr);
			ctx = canvas.getContext("2d");
			ctx.scale(dpr, dpr);
			ctx.lineWidth = 2.2;
			ctx.lineCap = "round";
			ctx.lineJoin = "round";
			ctx.strokeStyle = "#111827";
		}
		function pos(e) {
			const r = canvas.getBoundingClientRect();
			return { x: e.clientX - r.left, y: e.clientY - r.top };
		}
		function setInk(v) {
			hasInk = v;
			const ph = document.getElementById("sign_placeholder");
			if (ph) ph.style.display = v ? "none" : "";
			if (v) document.getElementById("sign_card")?.classList.remove("missing");
		}
		function init(el) {
			canvas = el;
			if (!canvas) return;
			size();
			setInk(false);
			canvas.addEventListener("pointerdown", (e) => {
				drawing = true;
				last = pos(e);
				canvas.setPointerCapture(e.pointerId);
				ctx.beginPath();
				ctx.arc(last.x, last.y, 1.1, 0, Math.PI * 2);
				ctx.fillStyle = "#111827";
				ctx.fill();
				setInk(true);
				e.preventDefault();
			});
			canvas.addEventListener("pointermove", (e) => {
				if (!drawing) return;
				const p = pos(e);
				ctx.beginPath();
				ctx.moveTo(last.x, last.y);
				ctx.lineTo(p.x, p.y);
				ctx.stroke();
				last = p;
				e.preventDefault();
			});
			const end = () => (drawing = false);
			canvas.addEventListener("pointerup", end);
			canvas.addEventListener("pointercancel", end);
		}
		function clear() {
			if (!canvas) return;
			size();
			setInk(false);
		}
		function toDataURL() {
			const scale = Math.min(1, 600 / canvas.width);
			const out = document.createElement("canvas");
			out.width = Math.round(canvas.width * scale);
			out.height = Math.round(canvas.height * scale);
			const o = out.getContext("2d");
			o.fillStyle = "#fff";
			o.fillRect(0, 0, out.width, out.height);
			o.drawImage(canvas, 0, 0, out.width, out.height);
			return out.toDataURL("image/png");
		}
		return { init, clear, toDataURL, isEmpty: () => !canvas || !hasInk };
	})();

	// Rotating the phone resizes the pad: start a fresh signature (strokes would be distorted).
	let lastWidth = window.innerWidth;
	window.addEventListener("resize", () => {
		if (window.innerWidth !== lastWidth) {
			lastWidth = window.innerWidth;
			SignPad.clear();
		}
	});

	// ----------------------------------------------------------- 4. result

	function showResult(r) {
		S.result = r;
		let main;
		if (r.show_result === "Nothing") {
			main = `<div class="card center"><div class="big-icon">✅</div>
				<p class="lead">${fmt("Đã nộp bài.")}</p>
				<p class="muted">${fmt("Cảm ơn bạn! HR sẽ thông báo kết quả sau.")}</p></div>`;
		} else {
			const pct = Math.round(r.percentage);
			main = `<div class="card center result ${r.passed ? "pass" : "fail"}">
				<div class="ring" style="--p:${pct}"><div class="ring-in"><b>${pct}%</b><small>${num(r.score)}/${num(r.max_score)}</small></div></div>
				<div class="verdict">${r.passed ? fmt("Đạt") : fmt("Chưa đạt")}</div>
				<p class="muted">${fmt("Điểm đạt: {0}%", [num(r.pass_percentage)])}</p>
				${r.status === "Expired" ? `<p class="muted">${fmt("Hết giờ — hệ thống đã chấm các câu bạn trả lời trước đó.")}</p>` : ""}
			</div>`;
		}
		const details = (r.details || [])
			.map(
				(d, i) => `<div class="card review ${d.is_correct ? "right" : "wrong"}">
					<div class="qhead"><span class="qno">${fmt("Câu {0}", [i + 1])}</span>
						<span class="qpts">${num(d.points_awarded)}/${num(d.points_max)}</span></div>
					<div class="qtext rich">${d.question}</div>
					<div class="ans"><span class="lbl">${fmt("Bạn chọn")}</span>${esc(d.answer_text) || `<i class="muted">${fmt("(chưa trả lời)")}</i>`}</div>
					${!d.is_correct ? `<div class="ans good"><span class="lbl">${fmt("Đáp án đúng")}</span>${esc(d.correct_text)}</div>` : ""}
					${d.explanation ? `<div class="expl">${esc(d.explanation)}</div>` : ""}
				</div>`
			)
			.join("");

		// Everyone takes the quiz on their own phone: no "next person" button.
		const again = !PREVIEW && (r.attempts_left === null || r.attempts_left > 0);
		const bar = PREVIEW
			? `<button class="btn btn-primary" id="preview-again">${fmt("Xem thử lại")}</button>`
			: again
				? `<button class="btn btn-primary" id="again">${fmt("Làm lại")}</button>`
				: "";
		render(`${header(S.attempt ? esc(S.attempt.employee_name) : "")}${main}${details}
			${bar ? `<div class="bottom-bar">${bar}</div>` : ""}`);
		const btnPreview = document.getElementById("preview-again");
		if (btnPreview) btnPreview.onclick = () => location.reload();
		const btnAgain = document.getElementById("again");
		if (btnAgain)
			btnAgain.onclick = async () => {
				btnAgain.disabled = true;
				resetAttempt();
				try {
					const a = await call("start", { slug: SLUG, employee: S.employee.id, code: S.code });
					S.answers = a.answers || {};
					openAttempt(a);
				} catch (e) {
					btnAgain.disabled = false;
					toast(e.message, "error");
				}
			};
	}

	boot();
})();

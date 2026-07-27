// Copyright (c) 2026, IT Team - TIQN and contributors
// Đọc cân điện tử (Jadever JIK/JWI) trực tiếp trong trình duyệt qua Web Serial API.
// Chỉ Chrome/Edge + HTTPS. Dùng chung qua window.plScale; OCR giữ làm dự phòng.

window.plScale = (function () {
	const LS_KEY = "pl_scale_cfg";
	const DEFAULT_CFG = {
		baudRate: 9600,
		dataBits: 8,
		parity: "none",
		stopBits: 1,
		// Regex mặc định Jadever: ST/US , GS/NT , <số> <đơn vị>
		// [.,] cho phần thập phân: có đầu cân dùng DẤU PHẨY. Chỉ nhận "." thì
		// "0,50" khớp thành "0" -> ghi 0 kg thay vì 0.5 mà không báo gì.
		regex: "(ST|US)\\s*,\\s*(GS|NT)\\s*,?\\s*([+-]?\\s*\\d+(?:[.,]\\d+)?)\\s*(kg|g|lb)?",
	};
	// Regex mặc định cũ (chỉ chấp nhận dấu chấm) — nâng cấp cho máy đã lưu bản cũ.
	const LEGACY_REGEX = "(ST|US)\\s*,\\s*(GS|NT)\\s*,?\\s*([+-]?\\s*\\d+(?:\\.\\d+)?)\\s*(kg|g|lb)?";

	let cfg = load_cfg();
	let port = null;
	let reader = null;
	let keepReading = false;
	let textBuf = "";
	const listeners = new Set(); // cb(parsed, rawLine)
	const statusListeners = new Set(); // cb(state)
	const recent = []; // vài dòng raw gần nhất (debug)

	function load_cfg() {
		try {
			const c = Object.assign({}, DEFAULT_CFG, JSON.parse(localStorage.getItem(LS_KEY) || "{}"));
			// Máy đã lưu regex mặc định CŨ -> nâng lên bản mới (chỉ khi user chưa tự sửa).
			if (c.regex === LEGACY_REGEX) c.regex = DEFAULT_CFG.regex;
			return c;
		} catch (e) {
			return Object.assign({}, DEFAULT_CFG);
		}
	}
	function getConfig() {
		return Object.assign({}, cfg);
	}
	function saveConfig(c) {
		cfg = Object.assign({}, cfg, c || {});
		localStorage.setItem(LS_KEY, JSON.stringify(cfg));
	}

	function supported() {
		return !!(navigator && navigator.serial);
	}
	function isConnected() {
		return !!port;
	}

	function setStatus(state) {
		statusListeners.forEach((cb) => {
			try {
				cb(state);
			} catch (e) {}
		});
	}
	function onStatus(cb) {
		statusListeners.add(cb);
		cb(port ? "connected" : "disconnected");
		return () => statusListeners.delete(cb);
	}
	function onReading(cb) {
		listeners.add(cb);
		return () => listeners.delete(cb);
	}

	function get_regex() {
		try {
			return new RegExp(cfg.regex, "i");
		} catch (e) {
			return new RegExp(DEFAULT_CFG.regex, "i");
		}
	}

	// Các kiểu fallback khi regex cấu hình không khớp — thử lần lượt.
	//  1) số + đơn vị chuẩn (Jadever rời cờ, cân generic).
	//  2) DIGI DI-28SS: "=   1.88B" — cờ "=" đứng trước, KHÔNG có token kg/g/lb.
	//     Bắt buộc có ký tự cờ ở đầu để khỏi vớ số linh tinh trong dòng.
	const FALLBACKS = [
		// [full, flag, mode, số, đơn vị]
		{ re: /([+-]?\s*\d+(?:[.,]\d+)?)[\s,]*(kg|g|lb)\b/i, map: (m) => ["", "", "", m[1], m[2]] },
		{ re: /^\s*([=~!S?])\s*([+-]?\d+(?:[.,]\d+)?)\s*([A-Za-z]{0,2})\s*$/, map: (m) => [m[0], m[1], "", m[2], ""] },
	];

	// Cờ rõ ràng cho biết ổn định (ST) hay chưa (US); ký tự khác -> để "loose".
	function stable_from_flag(flag) {
		flag = String(flag || "").toUpperCase();
		if (flag === "ST") return true;
		if (flag === "US") return false;
		return null; // không xác định -> caller dùng chế độ loose
	}

	// Parse 1 dòng -> {stable, mode, weight(kg), unit, raw, loose} hoặc null.
	function parseLine(line) {
		let m = get_regex().exec(line || "");
		let loose = false;
		if (!m) {
			for (const f of FALLBACKS) {
				const mm = f.re.exec(line || "");
				if (mm) {
					m = f.map(mm);
					break;
				}
			}
			if (!m) return null;
			loose = true;
		}
		let w = parseFloat(String(m[3] || "").replace(/\s+/g, "").replace(",", "."));
		if (isNaN(w)) return null;
		let unit = String(m[4] || "").toLowerCase();
		if (unit === "g") {
			w = w / 1000; // g -> kg
			unit = "kg";
		}
		// Cờ ST/US mới quyết định; cờ lạ (=, S...) hoặc regex generic không có cờ ->
		// loose = coi như ổn định, để luật "N lần liên tiếp cùng giá trị" của
		// readStableWeight lo phần chống số đang nhảy.
		let st = stable_from_flag(m[1]);
		if (st === null) {
			loose = true;
			st = true;
		}
		return {
			stable: st,
			mode: String(m[2] || "").toUpperCase(),
			weight: w,
			unit: unit || "kg",
			raw: line,
			loose: loose,
		};
	}

	function handle_line(line) {
		if (!line) return;
		recent.push(line);
		if (recent.length > 6) recent.shift();
		const parsed = parseLine(line);
		listeners.forEach((cb) => {
			try {
				cb(parsed, line);
			} catch (e) {}
		});
	}

	async function open_port(p) {
		port = p;
		await port.open({
			baudRate: Number(cfg.baudRate) || 9600,
			dataBits: Number(cfg.dataBits) || 8,
			parity: cfg.parity || "none",
			stopBits: Number(cfg.stopBits) || 1,
		});
		setStatus("connected");
		start_reading();
	}

	// Kết nối lần đầu — CẦN user gesture (click).
	async function connect() {
		if (!supported())
			throw new Error("Trình duyệt không hỗ trợ Web Serial (chỉ Chrome/Edge, cần HTTPS).");
		if (port) return true;
		const p = await navigator.serial.requestPort();
		await open_port(p);
		return true;
	}

	// Tự nối lại cổng đã được cấp quyền — KHÔNG cần gesture.
	async function tryReconnect() {
		if (!supported() || port) return isConnected();
		try {
			const ports = await navigator.serial.getPorts();
			if (ports && ports.length) {
				await open_port(ports[0]);
				return true;
			}
		} catch (e) {}
		return false;
	}

	async function start_reading() {
		keepReading = true;
		textBuf = "";
		const decoder = new TextDecoder();
		try {
			reader = port.readable.getReader();
		} catch (e) {
			return;
		}
		(async () => {
			try {
				while (keepReading) {
					const { value, done } = await reader.read();
					if (done) break;
					if (value) {
						textBuf += decoder.decode(value, { stream: true });
						// CR-only (\r) là kiểu kết dòng phổ biến của đầu cân (DIGI...).
						// Trước chỉ tách \r\n|\n -> loại cân đó không bao giờ ra 1 dòng nào,
						// buffer phình mãi và UI đứng ở "Đang chờ cân…" vĩnh viễn.
						let m;
						while ((m = /\r\n|\r|\n/.exec(textBuf))) {
							const line = textBuf.slice(0, m.index).trim();
							textBuf = textBuf.slice(m.index + m[0].length);
							if (line) handle_line(line);
						}
						// Không có ký tự kết dòng nào -> vẫn phải nhả ra để còn chẩn đoán,
						// nếu không thì "có data" và "không có data" trông giống hệt nhau.
						if (textBuf.length > 120) {
							handle_line(textBuf.trim());
							textBuf = "";
						}
					}
				}
			} catch (e) {
				// đọc lỗi (thường do rút cáp)
			} finally {
				try {
					reader.releaseLock();
				} catch (e) {}
			}
		})();
	}

	async function close() {
		keepReading = false;
		try {
			if (reader) await reader.cancel();
		} catch (e) {}
		try {
			if (reader) reader.releaseLock();
		} catch (e) {}
		reader = null;
		try {
			if (port) await port.close();
		} catch (e) {}
		port = null;
		setStatus("disconnected");
	}

	// Đọc số ổn định: đủ N dòng ST liên tiếp cùng giá trị.
	function readStableWeight(opts) {
		opts = opts || {};
		const timeoutMs = opts.timeoutMs || 8000;
		const needConsecutive = opts.needConsecutive || 3;
		return new Promise((resolve, reject) => {
			if (!port) {
				reject(new Error("Chưa kết nối cân."));
				return;
			}
			setStatus("reading");
			let count = 0,
				lastVal = null,
				gotAny = false;
			const off = onReading((parsed) => {
				if (!parsed) return;
				gotAny = true;
				if (parsed.stable) {
					if (lastVal !== null && Math.abs(parsed.weight - lastVal) < 1e-6) count++;
					else {
						count = 1;
						lastVal = parsed.weight;
					}
					if (count >= needConsecutive) {
						cleanup();
						resolve(parsed.weight);
					}
				} else {
					count = 0;
				}
			});
			const timer = setTimeout(() => {
				cleanup();
				// Ba tình huống rất khác nhau, đừng gộp làm một:
				//   không byte nào  -> cáp/COM/baud, hoặc đầu cân chưa bật in liên tục
				//   có byte, 0 parse -> sai regex (mỗi hãng một định dạng)
				//   parse được       -> số đang nhảy, chưa đứng yên
				let msg;
				if (!recent.length)
					msg =
						"Không nhận được dữ liệu từ cân. Kiểm tra: cáp RS232, đúng cổng COM, baud rate, " +
						"và đầu cân đã bật chế độ in liên tục (continuous/stream) chưa.";
				else if (!gotAny)
					msg =
						"Có nhận dữ liệu nhưng KHÔNG đọc được số — nhiều khả năng sai regex hoặc sai baud " +
						"(baud sai sẽ ra ký tự rác). Mở ⚙️ Scale Settings → Test để xem dữ liệu thô.\n" +
						recent.join("\n");
				else msg = "Cân chưa đứng yên (số còn nhảy). Raw gần nhất:\n" + recent.join("\n");
				reject(new Error(msg));
			}, timeoutMs);
			function cleanup() {
				clearTimeout(timer);
				off();
				setStatus(port ? "connected" : "disconnected");
			}
		});
	}

	// Xử lý rút cáp giữa chừng.
	if (supported()) {
		navigator.serial.addEventListener("disconnect", (e) => {
			if (port && e.target === port) {
				keepReading = false;
				reader = null;
				port = null;
				setStatus("disconnected");
			}
		});
	}
	// Đóng cổng sạch khi rời trang (F5/đóng tab) -> tránh lock COM.
	window.addEventListener("beforeunload", () => {
		try {
			if (reader) reader.cancel();
		} catch (e) {}
		try {
			if (port) port.close();
		} catch (e) {}
	});

	// Dialog cấu hình cổng + Test raw/parse.
	function settingsDialog() {
		const d = new frappe.ui.Dialog({
			title: __("⚖️ Cấu hình cân (Web Serial)"),
			fields: [
				{ fieldtype: "HTML", fieldname: "status" },
				{
					fieldtype: "Select",
					fieldname: "baudRate",
					label: __("Baud rate"),
					options: "1200\n2400\n4800\n9600\n19200\n38400\n57600\n115200",
					default: String(cfg.baudRate),
				},
				{ fieldtype: "Column Break" },
				{ fieldtype: "Select", fieldname: "dataBits", label: __("Data bits"), options: "7\n8", default: String(cfg.dataBits) },
				{ fieldtype: "Select", fieldname: "parity", label: __("Parity"), options: "none\neven\nodd", default: cfg.parity },
				{ fieldtype: "Select", fieldname: "stopBits", label: __("Stop bits"), options: "1\n2", default: String(cfg.stopBits) },
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Small Text",
					fieldname: "regex",
					label: __("Regex parse dòng (có nhóm: cờ, mode, số, đơn vị)"),
					default: cfg.regex,
				},
				{ fieldtype: "HTML", fieldname: "test" },
			],
			primary_action_label: __("Lưu"),
			primary_action() {
				saveConfig({
					baudRate: Number(d.get_value("baudRate")),
					dataBits: Number(d.get_value("dataBits")),
					parity: d.get_value("parity"),
					stopBits: Number(d.get_value("stopBits")),
					regex: d.get_value("regex"),
				});
				frappe.show_alert({ message: __("Đã lưu cấu hình cân"), indicator: "green" }, 4);
				d.hide();
			},
		});

		const render_status = () => {
			const connected = isConnected();
			d.fields_dict.status.$wrapper.html(
				`<div style="margin-bottom:6px">${__("Trạng thái")}: <b style="color:${
					connected ? "#27ae60" : "#c0392b"
				}">${connected ? __("Đã kết nối") : __("Chưa kết nối")}</b>
				<button class="btn btn-xs btn-${connected ? "default" : "primary"} sc-conn" style="margin-left:8px">${
					connected ? __("Ngắt") : __("Kết nối cổng COM")
				}</button></div>`
			);
		};
		const off = onStatus(render_status);
		d.onhide = () => off();

		d.$wrapper.on("click", ".sc-conn", async () => {
			try {
				if (isConnected()) await close();
				else {
					saveConfig({
						baudRate: Number(d.get_value("baudRate")),
						dataBits: Number(d.get_value("dataBits")),
						parity: d.get_value("parity"),
						stopBits: Number(d.get_value("stopBits")),
					});
					await connect();
				}
			} catch (e) {
				frappe.msgprint(frappe.utils.escape_html(e.message || String(e)));
			}
		});

		// Khu Test: hiện raw + parse live.
		d.fields_dict.test.$wrapper.html(
			`<button class="btn btn-sm btn-default sc-test">▶ ${__("Test (đặt vật lên cân)")}</button>
			<pre class="sc-testout" style="margin-top:6px;max-height:160px;overflow:auto;font-size:12px;background:#f7f7f7;padding:6px"></pre>`
		);
		let testOff = null;
		d.$wrapper.on("click", ".sc-test", async () => {
			const $out = d.$wrapper.find(".sc-testout");
			if (testOff) {
				testOff();
				testOff = null;
				$out.append("--- dừng test ---\n");
				return;
			}
			// đổi regex đang gõ để test ngay
			saveConfig({ regex: d.get_value("regex") });
			try {
				if (!isConnected()) await connect();
			} catch (e) {
				frappe.msgprint(frappe.utils.escape_html(e.message || String(e)));
				return;
			}
			$out.text("");
			testOff = onReading((parsed, raw) => {
				const line = parsed
					? `${raw}   ⟶  ${parsed.stable ? "ST" : "US"} ${parsed.weight} ${parsed.unit}`
					: `${raw}   ⟶  (không parse được)`;
				$out.append(frappe.utils.escape_html(line) + "\n");
				$out.scrollTop($out[0].scrollHeight);
			});
			setTimeout(() => {
				if (testOff) {
					testOff();
					testOff = null;
					$out.append("--- tự dừng sau 15s ---\n");
				}
			}, 15000);
		});
		const prevHide = d.onhide;
		d.onhide = () => {
			if (testOff) testOff();
			prevHide && prevHide();
		};

		render_status();
		d.show();
	}

	return {
		supported,
		isConnected,
		getConfig,
		saveConfig,
		connect,
		tryReconnect,
		close,
		onReading,
		onStatus,
		parseLine,
		readStableWeight,
		settingsDialog,
	};
})();

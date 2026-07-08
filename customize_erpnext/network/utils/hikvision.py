"""
hikvision.py — HikvisionNVR class
Giao tiếp với NVR Hikvision qua ISAPI (HTTP REST + Digest Auth)
Dựa trên docs_sample/src/nvr.py đã test thực tế.

Quy ước thời gian (probe thực tế 2026-07-08 trên cả 2 NVR):
- Đồng hồ NVR chạy giờ địa phương Asia/Ho_Chi_Minh (NTP, timeZone CST-7:00).
- ISAPI search nhận và trả wall-clock giờ NVR, hậu tố "Z" KHÔNG có nghĩa UTC.
- Vì vậy mọi cửa sổ query build từ datetime.now() (server cùng tz với NVR),
  và timestamp trả về được giữ nguyên wall-clock, chỉ bỏ hậu tố tz.
- searchResultPosition bị firmware bỏ qua (luôn trả từ đầu) → paginate bằng
  cách dời startTime, không dùng pos.
- DailyDistribution trả 400 Invalid XML trên firmware hiện tại → cache flag
  _daily_dist_supported để không lặp lại request hỏng cho từng camera.
"""
import uuid
import requests
import xmltodict
from requests.auth import HTTPDigestAuth
from datetime import datetime, timedelta
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class HikvisionNVR:
    def __init__(self, nvr_doc):
        """Nhận frappe document NVR."""
        self.name      = nvr_doc.nvr_name
        self.base_url  = f"http://{nvr_doc.host}:{nvr_doc.port}"
        self.auth      = HTTPDigestAuth(nvr_doc.user, nvr_doc.get_password("password"))
        self.session   = requests.Session()
        self.session.verify = False
        self._track_map = None  # cache cho track discovery
        self._daily_dist_supported = None  # None = chưa thử, False = firmware không hỗ trợ

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass

    # ─── HTTP helpers ─────────────────────────────────────────

    def _get(self, path: str) -> dict:
        r = self.session.get(f"{self.base_url}{path}", auth=self.auth, timeout=10)
        r.raise_for_status()
        if "format=json" in path:
            return r.json()
        return xmltodict.parse(r.text)

    def _post(self, path: str, xml_body: str) -> dict:
        r = self.session.post(
            f"{self.base_url}{path}",
            auth=self.auth,
            data=xml_body.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            timeout=15,
        )
        r.raise_for_status()
        if "format=json" in path:
            return r.json()
        return xmltodict.parse(r.text)

    # ─── NVR Status ───────────────────────────────────────────

    def is_online(self) -> bool:
        try:
            r = self.session.get(
                f"{self.base_url}/ISAPI/System/deviceInfo",
                auth=self.auth,
                timeout=5,
            )
            return r.status_code == 200
        except Exception:
            return False

    def get_device_info(self) -> dict:
        """GET /ISAPI/System/deviceInfo"""
        try:
            d = self._get("/ISAPI/System/deviceInfo").get("DeviceInfo", {})
            return {
                "model":    d.get("model"),
                "firmware": d.get("firmwareVersion"),
                "serial":   d.get("serialNumber"),
            }
        except Exception:
            return {}

    def get_system_status(self) -> dict:
        """
        Uptime: GET /ISAPI/System/status → DeviceStatus.deviceUpTime (giây)
          → trả về datetime NVR bắt đầu chạy (now - uptime_seconds)
        CPU/RAM: DeviceStatus.cpuUsage/memoryUsage — trả None nếu không có hoặc = 0
        (firmware DS-9664NI-I8 V4.50.010 không expose CPU/RAM qua endpoint này)
        """
        result = {"uptime": None, "cpu": None, "ram": None}
        try:
            s = self._get("/ISAPI/System/status").get("DeviceStatus", {})
            up = s.get("deviceUpTime")
            if up:
                secs = int(up)
                online_since = datetime.now() - __import__("datetime").timedelta(seconds=secs)
                result["uptime"] = online_since.strftime("%Y-%m-%d %H:%M:%S")
            # Dùng or None để bắt cả 0 (firmware trả 0 thay vì null)
            cpu = s.get("cpuUsage") or s.get("CPUUsage") or None
            mem = s.get("memoryUsage") or s.get("MemoryUsage") or None
            result["cpu"] = cpu
            result["ram"] = mem
        except Exception:
            pass
        return result

    def get_hdd_status(self) -> list:
        """GET /ISAPI/ContentMgmt/Storage"""
        try:
            hdds = (
                self._get("/ISAPI/ContentMgmt/Storage")
                    .get("storage", {})
                    .get("hddList", {})
                    .get("hdd", [])
            )
            if isinstance(hdds, dict):
                hdds = [hdds]
            result = []
            for h in hdds:
                cap  = int(h.get("capacity", 0))
                free = int(h.get("freeSpace", 0))
                used = cap - free
                pct  = round(used / cap * 100, 1) if cap > 0 else 0.0
                result.append({
                    "id":          h.get("id"),
                    "name":        h.get("hddName", f"hdd{h.get('id')}"),
                    "status":      h.get("status", "unknown"),
                    "capacity_gb": round(cap / 1024, 1),
                    "free_gb":     round(free / 1024, 1),
                    "used_pct":    pct,
                })
            return result
        except Exception:
            return []

    # ─── Camera Status ────────────────────────────────────────

    def get_camera_status(self) -> list:
        """
        Ưu tiên: GET /ISAPI/System/workingstatus/chanStatus?format=json
        Fallback: /ISAPI/System/Video/inputs/channels + channels/status
        """
        res_map = {}
        try:
            data = self._get("/ISAPI/System/workingstatus/chanStatus?format=json")
            # Response có thể là {"ChanStatus": {"JSON_ChanStatus": [...]}}
            # hoặc {"JSON_ChanStatus": [...]}
            cl = data.get("ChanStatus", {}).get("JSON_ChanStatus", [])
            if not cl:
                cl = data.get("JSON_ChanStatus", [])
            if isinstance(cl, dict):
                cl = [cl]
            for c in cl:
                cid = str(c.get("chanNo", ""))
                if cid:
                    res_map[cid] = {
                        "id":     cid,
                        "name":   c.get("name", f"Camera {cid}"),
                        "online": str(c.get("online", "0")) == "1",
                    }
        except Exception:
            pass

        if not res_map:
            # Fallback 1: lấy tên cameras
            for ep in [
                "/ISAPI/System/Video/inputs/channels",
                "/ISAPI/ContentMgmt/InputProxy/channels",
            ]:
                try:
                    d = self._get(ep)
                    rk = next((k for k in d if "List" in k), None)
                    items = d[rk].get(rk.replace("List", ""), []) if rk else []
                    if isinstance(items, dict):
                        items = [items]
                    for i in items:
                        cid = str(i.get("id", ""))
                        res_map[cid] = {
                            "id":     cid,
                            "name":   i.get("name", f"Camera {cid}"),
                            "online": False,
                        }
                except Exception:
                    continue

            # Fallback 2: lấy trạng thái online/offline
            for ep in [
                "/ISAPI/System/Video/inputs/channels/status",
                "/ISAPI/ContentMgmt/InputProxy/channels/status",
            ]:
                try:
                    d = self._get(ep)
                    rk = next((k for k in d if "StatusList" in k), None)
                    items = d[rk].get(rk.replace("List", ""), []) if rk else []
                    if isinstance(items, dict):
                        items = [items]
                    for i in items:
                        cid = str(i.get("id", ""))
                        if cid in res_map:
                            res_map[cid]["online"] = (
                                str(i.get("online", "false")).lower() in ("true", "1")
                            )
                except Exception:
                    continue

        ids = sorted(res_map.keys(), key=lambda x: int(x) if x.isdigit() else x)
        return [res_map[cid] for cid in ids]

    # ─── Track Discovery ──────────────────────────────────────

    def _get_track_id(self, cid: str) -> str:
        """Tìm TrackID thực tế từ NVR, fallback về {cid}01."""
        if self._track_map is None:
            self._track_map = {}
            try:
                ts = (
                    self._get("/ISAPI/ContentMgmt/record/tracks")
                        .get("TrackList", {})
                        .get("Track", [])
                )
                if isinstance(ts, dict):
                    ts = [ts]
                for t in ts:
                    tid = str(t.get("id", ""))
                    v_cid = t.get("videoInputChannelID") or t.get("inputChannelID")
                    if tid and v_cid and (tid.endswith("01") or len(tid) <= 2):
                        self._track_map[str(v_cid)] = tid
            except Exception:
                pass
        return self._track_map.get(str(cid)) or f"{cid}01"

    # ─── Recording History ────────────────────────────────────

    @staticmethod
    def _fmt_time(dt) -> str:
        """Datetime → chuỗi ISAPI. Hậu tố Z bắt buộc theo format nhưng NVR hiểu là giờ local."""
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _parse_naive(s):
        """Chuỗi ISAPI → naive datetime giữ nguyên wall-clock (bỏ Z/offset, không đổi giờ)."""
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(str(s).strip().replace("Z", ""))
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except Exception:
            return None

    def _collect_segments(self, tid: str, start: str, end: str) -> list:
        """Lấy toàn bộ segment trong cửa sổ [start, end].

        Firmware bỏ qua searchResultPosition nên paginate bằng cách dời
        startTime qua endTime lớn nhất đã thấy, dừng khi batch < 100.
        """
        segments = []
        cursor = start
        for _ in range(20):  # chặn trên 2000 segment / cửa sổ
            batch = self._search_api(tid, cursor, end, pos=0, max_results=100)
            if not batch:
                break
            segments.extend(batch)
            if len(batch) < 100:
                break
            ends = [b.get("timeSpan", {}).get("endTime") for b in batch]
            ends = [e for e in ends if e]
            new_cursor = max(ends) if ends else None
            if not new_cursor or new_cursor <= cursor:
                break
            cursor = new_cursor
        return segments

    def _search_api(self, tid: str, start: str, end: str, pos: int = 0, max_results: int = 1) -> list:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CMSearchDescription>
    <searchID>{uuid.uuid4()}</searchID>
    <trackList><trackID>{tid}</trackID></trackList>
    <timeSpanList><timeSpan>
        <startTime>{start}</startTime><endTime>{end}</endTime>
    </timeSpan></timeSpanList>
    <contentTypeList><contentType>video</contentType></contentTypeList>
    <maxResults>{max_results}</maxResults>
    <searchResultPosition>{pos}</searchResultPosition>
    <metaDataList><metaData>//recordType.meta.std-cgi.com</metaData></metaDataList>
</CMSearchDescription>"""
        try:
            d = self._post("/ISAPI/ContentMgmt/search", xml)
            root = d.get("CMSearchResult") or d.get("cmSearchResult") or {}
            match = root.get("matchList") or root.get("searchMatchItem") or {}
            items = match.get("searchMatchItem") if isinstance(match, dict) else []
            if not items and isinstance(match, list):
                items = match
            return [items] if isinstance(items, dict) else (items or [])
        except Exception:
            return []

    def _daily_distribution_days(self, tid: str, start: str, end: str) -> list:
        """Danh sách ngày có ghi hình (sorted). [] nếu firmware không hỗ trợ/không có."""
        if self._daily_dist_supported is False:
            return []
        try:
            xml = (
                f"<?xml version='1.0' encoding='UTF-8'?>"
                f"<DailyDistributionSearchDescription>"
                f"<timeSpan><startTime>{start}</startTime><endTime>{end}</endTime></timeSpan>"
                f"</DailyDistributionSearchDescription>"
            )
            d = self._post(
                f"/ISAPI/ContentMgmt/record/tracks/{tid}/dailyDistribution", xml
            )
            root = (
                d.get("DailyDistributionList")
                or d.get("dailyDistributionList")
                or d
            )
            days = root.get("DailyDistribution") or root.get("dailyDistribution") or []
            if isinstance(days, dict):
                days = [days]
            self._daily_dist_supported = True
            return sorted(
                day.get("day")
                for day in days
                if str(day.get("record") or day.get("recorded") or "").lower()
                in ("true", "1")
            )
        except Exception:
            # Firmware hiện tại trả 400 Invalid XML — không thử lại cho camera khác
            self._daily_dist_supported = False
            return []

    def _window_has_recording(self, tid: str, age_days: int, now=None) -> bool:
        """Cửa sổ 24h "age_days ngày trước" có ít nhất 1 segment không (1 call, ~0.1s)."""
        now = now or datetime.now()
        win_end   = now - timedelta(days=age_days)
        win_start = win_end - timedelta(hours=24)
        return bool(
            self._search_api(tid, self._fmt_time(win_start), self._fmt_time(win_end), 0, 1)
        )

    def _oldest_by_window_scan(self, tid: str, max_days: int = 150) -> str:
        """Tìm bản ghi cũ nhất bằng cửa sổ 24h — dùng khi search span dài bị
        firmware từ chối (NVR-Insite trả 500 cho span nhiều tháng).

        Nhị phân trên "tuổi" cửa sổ: retention xoá cuốn chiếu nên tính có/không
        dữ liệu gần như đơn điệu theo tuổi (~log2(max_days) call/camera).
        """
        now = datetime.now()

        # Neo: tìm một cửa sổ chắc chắn có dữ liệu
        if self._window_has_recording(tid, 0, now):
            anchor = 0
        else:
            anchor = next(
                (d for d in range(7, max_days, 7) if self._window_has_recording(tid, d, now)),
                None,
            )
            if anchor is None:
                return None

        # Nhị phân: lo luôn có dữ liệu, hi coi như không
        lo, hi = anchor, max_days
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self._window_has_recording(tid, mid, now):
                lo = mid
            else:
                hi = mid

        # Bản ghi cũ nhất nằm trong cửa sổ tuổi lo
        win_end   = now - timedelta(days=lo)
        win_start = win_end - timedelta(hours=24)
        segs = self._collect_segments(tid, self._fmt_time(win_start), self._fmt_time(win_end))
        starts = [s.get("timeSpan", {}).get("startTime") for s in segs]
        starts = [s for s in starts if s]
        return min(starts) if starts else None

    def get_oldest_recording(self, cid) -> str:
        """Bản ghi cũ nhất — DailyDistribution → search full-range → quét cửa sổ 24h."""
        tid = self._get_track_id(cid)
        start = "2020-01-01T00:00:00Z"
        end = self._fmt_time(datetime.now().replace(hour=23, minute=59, second=59))

        # Ưu tiên DailyDistribution (nhanh nhất) — nếu firmware hỗ trợ
        recorded_days = self._daily_distribution_days(tid, start, end)
        if recorded_days:
            return f"{recorded_days[0]}T00:00:00"

        # Search full-range, pos=0 = cũ nhất — chạy tốt trên NVR-Outsite
        res = self._search_api(tid, start, end, 0)
        if res:
            return res[0].get("timeSpan", {}).get("startTime") or None

        # Fallback: NVR-Insite trả 500 cho span dài → quét nhị phân cửa sổ 24h
        return self._oldest_by_window_scan(tid)

    def get_latest_recording(self, cid, max_lookback_days: int = 120) -> str:
        """Bản ghi mới nhất — ước tính thời điểm camera offline.

        Không dùng searchResultPosition (firmware bỏ qua → sẽ trả bản ghi CŨ nhất)
        và không search span dài (firmware Insite trả 500/timeout). Quét lùi từng
        cửa sổ 24h từ hiện tại, cửa sổ đầu tiên có segment → endTime lớn nhất.
        Camera offline thường mới ngừng gần đây nên thoát sớm sau vài call.
        """
        tid = self._get_track_id(cid)
        now = datetime.now()

        for d in range(max_lookback_days):
            win_end   = now - timedelta(days=d)
            win_start = win_end - timedelta(hours=24)
            segs = self._collect_segments(tid, self._fmt_time(win_start), self._fmt_time(win_end))
            ends = [s.get("timeSpan", {}).get("endTime") for s in segs]
            ends = [e for e in ends if e]
            if ends:
                return max(ends)
        return None

    def get_recording_gaps(self, cid, days: int = 7, min_gap_minutes: int = 10) -> str:
        """
        Phát hiện khoảng ngắt quãng trong ghi hình.
        Kiểm tra [days] ngày gần nhất, báo cáo các gap > [min_gap_minutes] phút.
        Trả về chuỗi mô tả hoặc rỗng nếu không có gap.
        Thời gian hiển thị theo giờ NVR (= giờ VN, xem docstring module).
        """
        tid = self._get_track_id(cid)
        now = datetime.now()

        # Quét từng cửa sổ 24h, mỗi cửa sổ paginate đầy đủ (không giới hạn 100)
        segments = []
        for d in range(days):
            win_end   = now - timedelta(days=d)
            win_start = win_end - timedelta(hours=24)
            segments.extend(
                self._collect_segments(tid, self._fmt_time(win_start), self._fmt_time(win_end))
            )

        if len(segments) < 2:
            return ""

        # Dedup + sort theo startTime
        seen = set()
        unique = []
        for seg in segments:
            ts = seg.get("timeSpan", {})
            key = (ts.get("startTime", ""), ts.get("endTime", ""))
            if key not in seen:
                seen.add(key)
                unique.append(seg)
        unique.sort(key=lambda x: x.get("timeSpan", {}).get("startTime", ""))

        if len(unique) < 2:
            return ""

        # Tìm gap
        gaps = []
        for i in range(len(unique) - 1):
            end_t   = self._parse_naive(unique[i].get("timeSpan", {}).get("endTime", ""))
            start_t = self._parse_naive(unique[i + 1].get("timeSpan", {}).get("startTime", ""))
            if end_t and start_t:
                diff_min = (start_t - end_t).total_seconds() / 60
                if diff_min > min_gap_minutes:
                    hours = int(diff_min // 60)
                    mins  = int(diff_min % 60)
                    dur = f"{hours}h{mins:02d}m" if hours else f"{mins}m"
                    gaps.append(
                        f"{end_t.strftime('%m-%d %H:%M')}→{start_t.strftime('%m-%d %H:%M')}({dur})"
                    )

        if not gaps:
            return ""
        return "; ".join(gaps)

"""
hikvision.py — HikvisionNVR class
Giao tiếp với NVR Hikvision qua ISAPI (HTTP REST + Digest Auth)
Dựa trên docs_sample/src/nvr.py đã test thực tế.
"""
import uuid
import requests
import xmltodict
from requests.auth import HTTPDigestAuth
from datetime import datetime, timezone
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

    def _search_api(self, tid: str, start: str, end: str, pos: int = 0) -> list:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CMSearchDescription>
    <searchID>{uuid.uuid4()}</searchID>
    <trackList><trackID>{tid}</trackID></trackList>
    <timeSpanList><timeSpan>
        <startTime>{start}</startTime><endTime>{end}</endTime>
    </timeSpan></timeSpanList>
    <contentTypeList><contentType>video</contentType></contentTypeList>
    <maxResults>1</maxResults>
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

    def get_oldest_recording(self, cid) -> str:
        """Bản ghi cũ nhất — dùng DailyDistribution, fallback sang Search API."""
        tid = self._get_track_id(cid)
        start = "2020-01-01T00:00:00Z"
        end = datetime.now().strftime("%Y-%m-%dT23:59:59Z")

        # Ưu tiên DailyDistribution (nhanh hơn)
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
            recorded_days = sorted(
                day.get("day")
                for day in days
                if str(day.get("record") or day.get("recorded") or "").lower()
                in ("true", "1")
            )
            if recorded_days:
                return f"{recorded_days[0]}T00:00:00Z"
        except Exception:
            pass

        # Fallback: Search API
        res = self._search_api(tid, start, end, 0)
        if res:
            return res[0].get("timeSpan", {}).get("startTime") or None
        return None

    def get_latest_recording(self, cid) -> str:
        """Bản ghi mới nhất — ước tính thời điểm camera offline."""
        tid = self._get_track_id(cid)
        end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            xml = (
                f"<?xml version='1.0' encoding='UTF-8'?>"
                f"<CMSearchDescription>"
                f"<searchID>{uuid.uuid4()}</searchID>"
                f"<trackList><trackID>{tid}</trackID></trackList>"
                f"<timeSpanList><timeSpan>"
                f"<startTime>2020-01-01T00:00:00Z</startTime><endTime>{end}</endTime>"
                f"</timeSpan></timeSpanList>"
                f"<maxResults>0</maxResults>"
                f"</CMSearchDescription>"
            )
            d = self._post("/ISAPI/ContentMgmt/search", xml)
            root = d.get("CMSearchResult") or d.get("cmSearchResult") or {}
            total = int(root.get("numOfMatches") or root.get("totalMatches") or 0)
            if total > 0:
                res = self._search_api(tid, "2020-01-01T00:00:00Z", end, total - 1)
                if res:
                    return res[0].get("timeSpan", {}).get("endTime") or None
        except Exception:
            pass
        return None

    def get_recording_gaps(self, cid, days: int = 7, min_gap_minutes: int = 10) -> str:
        """
        Phát hiện khoảng ngắt quãng trong ghi hình (record_gap.md).
        Kiểm tra [days] ngày gần nhất, báo cáo các gap > [min_gap_minutes] phút.
        Trả về chuỗi mô tả hoặc rỗng nếu không có gap.
        """
        from datetime import datetime as _dt, timedelta

        tid = self._get_track_id(cid)
        now_utc = _dt.now(timezone.utc)
        start_utc = now_utc - timedelta(days=days)
        start = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        end   = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Lấy tất cả segment trong khoảng thời gian (tối đa 200 kết quả)
        segments = []
        batch_size = 50
        pos = 0
        try:
            # Đếm tổng số kết quả
            xml_count = (
                f"<?xml version='1.0' encoding='UTF-8'?>"
                f"<CMSearchDescription>"
                f"<searchID>{uuid.uuid4()}</searchID>"
                f"<trackList><trackID>{tid}</trackID></trackList>"
                f"<timeSpanList><timeSpan><startTime>{start}</startTime><endTime>{end}</endTime></timeSpan></timeSpanList>"
                f"<contentTypeList><contentType>video</contentType></contentTypeList>"
                f"<maxResults>0</maxResults>"
                f"<searchResultPosition>0</searchResultPosition>"
                f"<metaDataList><metaData>//recordType.meta.std-cgi.com</metaData></metaDataList>"
                f"</CMSearchDescription>"
            )
            d = self._post("/ISAPI/ContentMgmt/search", xml_count)
            root = d.get("CMSearchResult") or d.get("cmSearchResult") or {}
            total = int(root.get("numOfMatches") or root.get("totalMatches") or 0)
            if total == 0:
                return ""

            # Lấy tối đa 200 segment để tránh timeout
            fetch_count = min(total, 200)
            while pos < fetch_count:
                batch = self._search_api(tid, start, end, pos)
                if not batch:
                    break
                segments.extend(batch)
                pos += len(batch)
                if len(batch) < batch_size:
                    break
        except Exception:
            return ""

        if len(segments) < 2:
            return ""

        # Sắp xếp theo startTime
        def _parse_iso(s):
            try:
                return _dt.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                return None

        segments.sort(key=lambda x: x.get("timeSpan", {}).get("startTime", ""))

        # Tìm gap
        gaps = []
        for i in range(len(segments) - 1):
            end_t   = _parse_iso(segments[i].get("timeSpan", {}).get("endTime", ""))
            start_t = _parse_iso(segments[i + 1].get("timeSpan", {}).get("startTime", ""))
            if end_t and start_t:
                diff_min = (start_t - end_t).total_seconds() / 60
                if diff_min > min_gap_minutes:
                    end_local   = end_t.astimezone().strftime("%m-%d %H:%M")
                    start_local = start_t.astimezone().strftime("%m-%d %H:%M")
                    hours = int(diff_min // 60)
                    mins  = int(diff_min % 60)
                    dur = f"{hours}h{mins:02d}m" if hours else f"{mins}m"
                    gaps.append(f"{end_local}→{start_local}({dur})")

        if not gaps:
            return ""
        return "; ".join(gaps)

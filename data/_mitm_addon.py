"""Auto-generated mitmproxy addon — captures WeChat live stream URLs.

Live page provides oid (stable room ID). FLV streams are mapped to oid
via orig_ number in FLV URL path (unique per live room).
"""
import sys, os, re, time, logging, json
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, r"D:\\liverec")
from config import Config
from mitmproxy import http

logger = logging.getLogger(__name__)

CAPTURED = {}
CACHE_TTL = 1800
CAPTURE_FILE = r"D:\\liverec\\data\\wechat_captured.txt"

STREAM_RE = re.compile(
    r"(?:\.m3u8|\.flv$|pull-flv|pull-hls|wxstream|wxvideostream"
    r"|liveplay\.myqcloud|finderlive|live\.video\.qq|wxlivecdn)",
    re.IGNORECASE,
)
EXCLUDE_RE = re.compile(r"stodownload|stothumb|skey=", re.IGNORECASE)
LIVE_PAGE_RE = re.compile(r"channels\.weixin\.qq\.com/web/pages/live", re.IGNORECASE)
ALLOWED_DOMAINS = set(d.lower() for d in Config.WECHAT_DOMAINS + ["wxlivecdn.com"])

# Track oids for logging
SEEN_OIDS = set()


class WeChatAddon:
    def request(self, flow: http.HTTPFlow):
        try:
            host = flow.request.host.lower().rstrip(".")
            if not any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS):
                return
            url = flow.request.pretty_url

            # Live page: extract oid
            if LIVE_PAGE_RE.search(url):
                self._on_live_page(url)
                return

            if EXCLUDE_RE.search(url):
                return
            if not STREAM_RE.search(url):
                return
            if self._is_dup(url):
                return
            self._capture(url, dict(flow.request.headers))
        except Exception as e:
            logger.error(f"Error: {e}")

    def response(self, flow: http.HTTPFlow):
        try:
            host = flow.request.host.lower().rstrip(".")
            if not any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS):
                return
            url = flow.request.pretty_url
            if EXCLUDE_RE.search(url):
                return
            if self._is_dup(url):
                return
            ct = flow.response.headers.get("content-type", "") if flow.response else ""
            if "mpegurl" not in ct and "flv" not in ct:
                return
            self._capture(url, dict(flow.request.headers))
        except Exception as e:
            logger.error(f"Error: {e}")

    def _on_live_page(self, url):
        try:
            params = parse_qs(urlparse(url).query)
            oid = params.get("oid", [""])[0]
            if oid and oid not in SEEN_OIDS:
                SEEN_OIDS.add(oid)
                logger.info(f"Live page: oid={oid}")
        except Exception:
            pass

    def _capture(self, url, headers):
        # Extract orig_ stream ID — unique per live room
        room_id = ""
        m = re.search(r"orig_(\d+)", url)
        if m:
            room_id = m.group(1)
        if not room_id:
            return
        self._emit(url, headers, room_id)

    def _emit(self, url, headers, room_id):
        info = {"room_id": room_id, "name": f"视频号_{room_id[:8]}"}
        safe = Config.redact_url(url)
        logger.info(f"[Stream] room={room_id} {safe[:100]}")
        print(f"CAPTURED: {safe[:100]}", flush=True)
        try:
            os.makedirs(os.path.dirname(CAPTURE_FILE), exist_ok=True)
            with open(CAPTURE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), "url": url, "h": headers, "info": info}) + "\n")
        except Exception:
            pass

    def _is_dup(self, url):
        now = time.time()
        for u in [u for u, t in list(CAPTURED.items()) if now - t >= CACHE_TTL]:
            del CAPTURED[u]
        ts = CAPTURED.get(url)
        if ts is not None and now - ts < CACHE_TTL:
            return True
        CAPTURED[url] = now
        return False


addons = [WeChatAddon()]

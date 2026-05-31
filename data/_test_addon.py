"""mitmproxy addon to capture WeChat live stream URLs."""
from mitmproxy import http
import re
import os
import time

STREAM_RE = re.compile(
    r"(?:m3u8|\.flv|pull-flv|pull-hls|wxstream|wxvideostream"
    r"|liveplay\.myqcloud|finderlive|live\.video\.qq)",
    re.IGNORECASE,
)

CAPTURED = set()
CAPTURE_FILE = r"D:\liverec\data\wechat_captured.txt"


def response(flow: http.HTTPFlow):
    url = flow.request.pretty_url
    if STREAM_RE.search(url) and url not in CAPTURED:
        CAPTURED.add(url)
        os.makedirs(os.path.dirname(CAPTURE_FILE), exist_ok=True)
        with open(CAPTURE_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.time()}\t{url}\n")
        print(f"CAPTURED: {url[:100]}")

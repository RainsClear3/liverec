from mitmproxy import http
import re, os, time
STREAM_RE = re.compile(
    r'(?:m3u8|\.flv|pull-flv|pull-hls|wxstream|wxvideostream|liveplay\.myqcloud|finderlive|live\.video\.qq)',
    re.IGNORECASE,
)
CAPTURE_FILE = r'D:\liverec\data\wechat_captured.txt'
CAPTURED = set()

def response(flow: http.HTTPFlow):
    url = flow.request.pretty_url
    if STREAM_RE.search(url) and url not in CAPTURED:
        CAPTURED.add(url)
        os.makedirs(os.path.dirname(CAPTURE_FILE), exist_ok=True)
        with open(CAPTURE_FILE, 'a', encoding='utf-8') as f:
            f.write(str(time.time()) + '\t' + url + '\n')
        print('CAPTURED: ' + url[:100])

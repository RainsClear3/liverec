"""WeChat Channels stream sniffer using mitmproxy proxy mode.

Uses mitmproxy as an HTTP/HTTPS proxy and configures the Windows system
proxy so all traffic (including WeChat) flows through it. Also launches
WeChat with --proxy-server and --disable-quic flags to ensure the
embedded Chromium browser uses the proxy.

The addon detects WeChat video stream URLs and passes them with
headers directly to the recording system via callback.
"""

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from typing import Optional, Callable

try:
    import winreg
except ImportError:
    winreg = None

from config import Config

logger = logging.getLogger("live_recorder")

WECHAT_EXE = r"D:\Program Files\Tencent\WeChat\Weixin.exe"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CAPTURE_FILE = os.path.join(DATA_DIR, "wechat_captured.txt")
ADDON_SCRIPT = os.path.join(DATA_DIR, "_mitm_addon.py")
PROXY_ADDR = "127.0.0.1:8080"
INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


class StreamSniffer:
    def __init__(self):
        self.is_running = False
        self._mitmprocess: Optional[subprocess.Popen] = None
        self._wechat_process: Optional[subprocess.Popen] = None
        self._watcher_running = False
        self._callbacks: list[Callable] = []
        self._original_proxy_enabled: Optional[int] = None
        self._original_proxy_server: Optional[str] = None
        self._original_auto_config_url: Optional[str] = None

    def start(self, callback: Callable[[str, dict, dict], None]) -> bool:
        """Start the sniffer: set proxy -> start mitmdump -> launch WeChat.

        Args:
            callback: Called with (url, headers, streamer_info) when captured.
        """
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            self._callbacks = [callback]

            # Step 1: Kill existing WeChat and mitmdump, restore system proxy
            self._kill_wechat()
            self._kill_mitmdump()
            self._restore_system_proxy()  # Clean up leftover proxy from previous run

            # Step 2: Install mitmproxy CA cert
            self._install_mitm_ca()

            # Step 3: Write addon script
            self._write_addon()

            # Step 4: Set PAC-based selective proxy (only WeChat domains)
            self._set_system_proxy()

            # Step 5: Start mitmdump as regular HTTP proxy
            mitmdump = self._find_mitmdump()
            if not mitmdump:
                logger.error("mitmdump not found")
                return False

            # Only MITM WeChat domains — all other traffic passes through unmodified
            cmd = [
                mitmdump,
                "--mode", "regular",
                "--listen-port", "8080",
                "-s", ADDON_SCRIPT,
                "--allow-hosts", ".*channels\\.weixin\\.qq\\.com",
                "--allow-hosts", ".*finder\\.video\\.qq\\.com",
                "--allow-hosts", ".*findermp\\.video\\.qq\\.com",
                "--allow-hosts", ".*finder\\.qq\\.com",
                "--allow-hosts", ".*wxsnsdythumb\\.video\\.qq\\.com",
                "--allow-hosts", ".*wxlivecdn\\.com",
            ]

            self._mitmprocess = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            # Wait for mitmdump to start
            time.sleep(3)
            if self._mitmprocess.poll() is not None:
                out = self._mitmprocess.stdout.read().decode(errors="replace")
                logger.error(f"mitmdump failed: {out[:500]}")
                self._restore_system_proxy()
                return False

            # Step 6: Launch WeChat with proxy + cert bypass + disable QUIC
            self._launch_wechat()

            self.is_running = True
            self._watcher_running = True
            threading.Thread(target=self._file_watcher, daemon=True).start()
            threading.Thread(target=self._mitm_output_reader, daemon=True).start()

            logger.info(
                f"Sniffer started - proxy on {PROXY_ADDR}\n"
                "System proxy configured, WeChat restarted.\n"
                "Please navigate to a video channel live page."
            )
            return True

        except Exception as e:
            logger.error(f"Sniffer failed: {e}", exc_info=True)
            self._restore_system_proxy()
            return False

    def stop(self):
        self.is_running = False
        self._watcher_running = False
        self._restore_system_proxy()

        if self._mitmprocess:
            try:
                self._mitmprocess.terminate()
                self._mitmprocess.wait(timeout=5)
            except Exception:
                try:
                    self._mitmprocess.kill()
                except Exception:
                    pass
            self._mitmprocess = None

        logger.info("Sniffer stopped")

    def _on_url_captured(self, url: str, headers: dict, info: dict = None):
        for cb in self._callbacks:
            try:
                cb(url, headers, info or {})
            except Exception as e:
                logger.error(f"Callback error: {e}")

    # --- WeChat management ---

    def _kill_wechat(self):
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "Weixin.exe", "/T"],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["taskkill", "/F", "/IM", "WeChatAppEx.exe", "/T"],
                capture_output=True, timeout=5,
            )
            time.sleep(2)
            logger.info("WeChat processes killed")
        except Exception:
            pass

    def _kill_mitmdump(self):
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "mitmdump.exe", "/T"],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["taskkill", "/F", "/IM", "mitmproxy.exe", "/T"],
                capture_output=True, timeout=5,
            )
            time.sleep(1)
        except Exception:
            pass

    def _launch_wechat(self):
        """Launch WeChat with cert bypass (proxy via PAC file, not command-line)."""
        if not os.path.isfile(WECHAT_EXE):
            logger.warning(f"WeChat not found at {WECHAT_EXE}")
            return
        try:
            self._wechat_process = subprocess.Popen(
                [WECHAT_EXE, "--ignore-certificate-errors"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            logger.info(f"WeChat launched (PID={self._wechat_process.pid})")
        except Exception as e:
            logger.error(f"Failed to launch WeChat: {e}")

    # --- System proxy management ---

    def _set_system_proxy(self):
        """Set system proxy to point to mitmproxy."""
        if not winreg or platform.system() != "Windows":
            return
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                INTERNET_SETTINGS,
                0,
                winreg.KEY_ALL_ACCESS,
            )
            try:
                self._original_proxy_enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            except FileNotFoundError:
                self._original_proxy_enabled = 0
            try:
                self._original_proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            except FileNotFoundError:
                self._original_proxy_server = ""
            # Clear PAC if set
            try:
                self._original_auto_config_url, _ = winreg.QueryValueEx(key, "AutoConfigURL")
                winreg.DeleteValue(key, "AutoConfigURL")
            except FileNotFoundError:
                self._original_auto_config_url = ""

            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, PROXY_ADDR)
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            logger.info(f"System proxy set to {PROXY_ADDR}")
        except Exception as e:
            logger.warning(f"Failed to set system proxy: {e}")

    def _restore_system_proxy(self):
        """Restore system proxy to original settings."""
        if not winreg or platform.system() != "Windows":
            return
        if self._original_proxy_enabled is None:
            return
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                INTERNET_SETTINGS,
                0,
                winreg.KEY_ALL_ACCESS,
            )
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, self._original_proxy_enabled)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, self._original_proxy_server or "")
            if self._original_auto_config_url:
                winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, self._original_auto_config_url)
            else:
                try:
                    winreg.DeleteValue(key, "AutoConfigURL")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            logger.info("System proxy restored")
        except Exception as e:
            logger.warning(f"Failed to restore system proxy: {e}")

    # --- mitmproxy helpers ---

    def _find_mitmdump(self) -> Optional[str]:
        path = shutil.which("mitmdump")
        if path:
            return path
        for p in [os.path.join(DATA_DIR, "mitmdump.exe")]:
            if os.path.isfile(p):
                return p
        return None

    def _install_mitm_ca(self):
        ca_cert = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
        if not os.path.exists(ca_cert):
            subprocess.run(["mitmdump", "--version"], capture_output=True, timeout=10)
        if os.path.exists(ca_cert):
            try:
                r = subprocess.run(
                    ["certutil", "-addstore", "-user", "Root", ca_cert],
                    capture_output=True, text=True, timeout=10,
                )
                if "command completed successfully" in r.stdout.lower():
                    logger.info("mitmproxy CA installed to trust store")
            except Exception:
                pass

    def _write_addon(self):
        """Write mitmproxy addon that intercepts WeChat stream traffic."""
        os.makedirs(DATA_DIR, exist_ok=True)
        cap_file = CAPTURE_FILE.replace("\\", "\\\\")
        config_path = os.path.dirname(DATA_DIR).replace("\\", "\\\\")

        script = f'''"""Auto-generated mitmproxy addon — captures WeChat live stream URLs.

Live page provides oid (stable room ID). FLV streams are mapped to oid
via orig_ number in FLV URL path (unique per live room).
"""
import sys, os, re, time, logging, json
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, r"{config_path}")
from config import Config
from mitmproxy import http

logger = logging.getLogger(__name__)

CAPTURED = {{}}
CACHE_TTL = {Config.STREAM_CACHE_TTL}
CAPTURE_FILE = r"{cap_file}"

STREAM_RE = re.compile(
    r"(?:\\.m3u8|\\.flv$|pull-flv|pull-hls|wxstream|wxvideostream"
    r"|liveplay\\.myqcloud|finderlive|live\\.video\\.qq|wxlivecdn)",
    re.IGNORECASE,
)
EXCLUDE_RE = re.compile(r"stodownload|stothumb|skey=", re.IGNORECASE)
LIVE_PAGE_RE = re.compile(r"channels\\.weixin\\.qq\\.com/web/pages/live", re.IGNORECASE)
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
            logger.error(f"Error: {{e}}")

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
            logger.error(f"Error: {{e}}")

    def _on_live_page(self, url):
        try:
            params = parse_qs(urlparse(url).query)
            oid = params.get("oid", [""])[0]
            if oid and oid not in SEEN_OIDS:
                SEEN_OIDS.add(oid)
                logger.info(f"Live page: oid={{oid}}")
        except Exception:
            pass

    def _capture(self, url, headers):
        # Extract orig_ stream ID — unique per live room
        room_id = ""
        m = re.search(r"orig_(\\d+)", url)
        if m:
            room_id = m.group(1)
        if not room_id:
            return
        self._emit(url, headers, room_id)

    def _emit(self, url, headers, room_id):
        info = {{"room_id": room_id, "name": f"视频号_{{room_id}}"}}
        safe = Config.redact_url(url)
        logger.info(f"[Stream] room={{room_id}} {{safe[:100]}}")
        print(f"CAPTURED: {{safe[:100]}}", flush=True)
        try:
            os.makedirs(os.path.dirname(CAPTURE_FILE), exist_ok=True)
            with open(CAPTURE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({{"t": time.time(), "url": url, "h": headers, "info": info}}) + "\\n")
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
'''
        with open(ADDON_SCRIPT, "w", encoding="utf-8") as f:
            f.write(script)

    # --- Monitoring ---

    def _file_watcher(self):
        """Poll capture file for new URLs and trigger callbacks."""
        last_size = 0
        while self._watcher_running:
            try:
                if os.path.exists(CAPTURE_FILE):
                    size = os.path.getsize(CAPTURE_FILE)
                    if size > last_size:
                        logger.info(f"File watcher: {size - last_size} new bytes in capture file")
                        with open(CAPTURE_FILE, "r", encoding="utf-8") as f:
                            f.seek(last_size)
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    data = json.loads(line)
                                    url = data.get("url", "")
                                    info = data.get("info", {})
                                    rid = info.get("room_id", "")
                                    logger.info(f"File watcher: parsed room={rid} url={url[:60]}")
                                    self._on_url_captured(url, data.get("h", {}), info)
                                except (json.JSONDecodeError, KeyError) as e:
                                    logger.warning(f"File watcher: parse error: {e}")
                        last_size = size
            except Exception as e:
                logger.warning(f"File watcher error: {e}")
            time.sleep(1)

    def _mitm_output_reader(self):
        """Read mitmdump stdout for log info."""
        try:
            while self._mitmprocess and self._mitmprocess.poll() is None:
                line = self._mitmprocess.stdout.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                if text:
                    if "CAPTURED" in text or "[REQUEST match]" in text:
                        logger.info(f"mitmproxy: {text[:200]}")
                    elif "stream" in text.lower():
                        logger.debug(f"mitmproxy: {text[:150]}")
                    elif "error" in text.lower() or "failed" in text.lower():
                        logger.debug(f"mitmproxy: {text[:150]}")
        except Exception:
            pass

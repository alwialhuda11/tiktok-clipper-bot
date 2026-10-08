"""Chrome headless + CDP helper — pola sama kayak Threads bot."""
import json, time, subprocess, os, signal
import requests, websocket

CHROME = "/opt/google/chrome/chrome"

def launch_chrome(port, profile_dir=None):
    """Launch Chrome headless dengan CDP port. Return PID atau None."""
    if profile_dir is None:
        profile_dir = f"/tmp/chrome-tiktok-{port}"
    os.makedirs(profile_dir, exist_ok=True)
    # Cek sudah jalan
    try:
        requests.get(f"http://localhost:{port}/json/version", timeout=3)
        return True
    except Exception:
        pass
    cmd = [
        CHROME, f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run", "--no-default-browser-check",
        "--remote-allow-origins=*", "--headless=new", "--noerrdialogs",
        "--ozone-platform=headless", "--disable-gpu", "--disable-dev-shm-usage",
        "--window-size=1280,900",
        "--renderer-process-limit=2", "--process-per-site",
        "--js-flags=--max-old-space-size=96",
        "--disable-features=BackForwardCache,MediaRouter,Translate,OptimizationHints",
        "--disk-cache-size=10485760", "--disable-background-networking",
        "--metrics-recording-only", "--no-pings", "--num-raster-threads=1",
        "--lang=en-US",
    ]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Tunggu CDP siap
    for _ in range(20):
        try:
            requests.get(f"http://localhost:{port}/json/version", timeout=3)
            return True
        except Exception:
            time.sleep(1)
    return False

def kill_chrome(port):
    """Kill Chrome di port tertentu."""
    subprocess.run(["bash", "-c",
        f"ps aux | grep '[c]hrome.*remote-debugging-port={port}' | awk '{{print $2}}' | xargs -r kill"],
        capture_output=True)

def _ws_url(port, want_threads=False):
    resp = requests.get(f"http://localhost:{port}/json", timeout=5).json()
    for t in resp:
        if not want_threads or "tiktok" in t.get("url", "").lower():
            return t.get("webSocketDebuggerUrl")
    return resp[0].get("webSocketDebuggerUrl") if resp else None

def cdp_eval(port, expr, timeout=20):
    ws_url = _ws_url(port)
    if not ws_url:
        return None
    ws = websocket.create_connection(ws_url, timeout=timeout)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
    msg = json.loads(ws.recv())
    ws.close()
    return msg.get("result", {}).get("result", {}).get("value")

def navigate(port, url, wait=6):
    ws_url = _ws_url(port)
    if not ws_url:
        return False
    ws = websocket.create_connection(ws_url, timeout=20)
    ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
    json.loads(ws.recv())
    ws.close()
    time.sleep(wait)
    return True

def click_at(port, x, y):
    ws_url = _ws_url(port)
    if not ws_url:
        return
    ws = websocket.create_connection(ws_url, timeout=20)
    for typ in ("mouseMoved", "mousePressed", "mouseReleased"):
        params = {"type": typ, "x": x, "y": y}
        if "Pressed" in typ or "Released" in typ:
            params.update({"button": "left", "clickCount": 1})
        ws.send(json.dumps({"id": 1, "method": "Input.dispatchMouseEvent", "params": params}))
        json.loads(ws.recv())
        time.sleep(0.1)
    ws.close()

def inject_cookies(port, cookies_file):
    """Inject cookies JSON (format EditThisCookie / list) ke Chrome. Untuk login TikTok."""
    with open(cookies_file) as f:
        cookies = json.load(f)
    if isinstance(cookies, dict):
        cookies = cookies.get("cookies", [cookies])
    ws_url = _ws_url(port)
    ws = websocket.create_connection(ws_url, timeout=15)
    ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": "https://www.tiktok.com/"}}))
    json.loads(ws.recv())
    time.sleep(4)
    ok = 0
    for i, c in enumerate(cookies):
        cdp_c = {
            "name": c.get("name"), "value": c.get("value"),
            "domain": c.get("domain", ".tiktok.com"), "path": c.get("path", "/"),
            "secure": c.get("secure", True), "httpOnly": c.get("httpOnly", False),
            "sameSite": c.get("sameSite", "None"),
        }
        cdp_c = {k: v for k, v in cdp_c.items() if v is not None}
        if "expirationDate" in c:
            cdp_c["expires"] = c["expirationDate"]
        ws.send(json.dumps({"id": i + 2, "method": "Network.setCookie", "params": cdp_c}))
        resp = json.loads(ws.recv())
        if resp.get("result", {}).get("success"):
            ok += 1
    ws.close()
    print(f"    Injected {ok}/{len(cookies)} cookies")
    # Refresh halaman biar login kebaca
    navigate(port, "https://www.tiktok.com/", wait=5)
    return ok > 0

def is_logged_in(port):
    """Cek apakah TikTok sudah login (lihat elemen upload/profile)."""
    v = cdp_eval(port, """
        (() => {
            const uploadBtn = document.querySelector('a[href*="/upload"], button[data-e2e="upload-button"]');
            const loginBtn = document.querySelector('[data-e2e="login-button"], button:has-text("Log in")');
            const avatar = document.querySelector('[data-e2e="profile-icon"], img[src*="profile"]');
            return JSON.stringify({upload: !!uploadBtn, avatar: !!avatar, bodyHas: document.body.innerText.substring(0,200)});
        })()
    """)
    return v

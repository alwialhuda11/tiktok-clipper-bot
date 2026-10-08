"""Auto-upload video ke TikTok via web (CDP) — gak butuh API approval.

Flow: tiktok.com/creator-center/upload -> set file -> set caption -> Post.
Butuh: Chrome logged in (inject cookies sekali via config/tiktok_cookies.json).

NOTE: Product basket (keranjang kuning) gak bisa di-attach via web — app only.
Caption tetap berisi promo link + hashtag. Kalau mau basket, post manual via app.
"""
import time, json, os
from .chrome_cdp import (launch_chrome, kill_chrome, cdp_eval, navigate,
                         click_at, inject_cookies, is_logged_in)

UPLOAD_PORT = 9231
ROOT = os.path.dirname(os.path.dirname(__file__))
COOKIES_FILE = os.path.join(ROOT, "config", "tiktok_cookies.json")

def _ensure_login(port):
    """Pastikan Chrome logged in; inject cookies kalau ada file."""
    info = is_logged_in(port)
    if info:
        d = json.loads(info)
        # Cek avatar/profile = logged in
        if d.get("avatar") or d.get("upload"):
            return True
    # Coba inject cookies
    if os.path.exists(COOKIES_FILE):
        print("    [UP] Inject TikTok cookies...")
        inject_cookies(port, COOKIES_FILE)
        info2 = is_logged_in(port)
        if info2:
            d2 = json.loads(info2)
            if d2.get("avatar") or d2.get("upload"):
                return True
    return False

def upload_video(video_path, caption, privacy="public", upload_port=UPLOAD_PORT):
    """Upload video ke TikTok via web creator center.
    
    Args:
        video_path: path file video (MP4)
        caption: caption/description (max 2200 chars)
        privacy: "public" atau "private" (buat test dulu)
    
    Returns: True kalau sukses
    """
    print(f"    [UP] Launch Chrome :{upload_port}...")
    if not launch_chrome(upload_port):
        print("    [UP] Gak bisa launch Chrome")
        return False

    try:
        # Cek login
        if not _ensure_login(upload_port):
            print("    [UP] Belum login TikTok! Drop cookies ke config/tiktok_cookies.json dulu.")
            print("    [UP] (Export dari browser: EditThisCookie -> Export -> save sebagai tiktok_cookies.json)")
            return False

        # Buka upload page
        print("    [UP] Buka creator center upload...")
        navigate(upload_port, "https://www.tiktok.com/creator-center/upload", wait=8)

        # Set file via CDP DOM.setFileInputFiles
        abs_path = os.path.abspath(video_path)
        file_set = cdp_eval(upload_port, f"""
            (() => {{
                const input = document.querySelector('input[type="file"]');
                if (!input) return JSON.stringify({{error: "file input not found"}});
                return JSON.stringify({{found: true}});
            }})()
        """)
        if not file_set or json.loads(file_set).get("error"):
            # Coba klik "Select video" dulu
            cdp_eval(upload_port, """
                (() => {
                    const btn = Array.from(document.querySelectorAll('button, div[role="button"]'))
                        .find(b => (b.innerText||'').includes('Select') || (b.innerText||'').includes('Upload'));
                    if (btn) { btn.click(); return true; }
                    return false;
                })()
            """)
            time.sleep(2)

        # Set file input via CDP (perlu DOM domain)
        ws_url = None
        import requests, websocket
        resp = requests.get(f"http://localhost:{upload_port}/json", timeout=5).json()
        for t in resp:
            if "upload" in t.get("url", "").lower() or "creator" in t.get("url", "").lower():
                ws_url = t.get("webSocketDebuggerUrl")
                break
        if not ws_url:
            ws_url = resp[0].get("webSocketDebuggerUrl")

        ws = websocket.create_connection(ws_url, timeout=30)
        # Get DOM document
        ws.send(json.dumps({"id": 1, "method": "DOM.enable"}))
        json.loads(ws.recv())
        ws.send(json.dumps({"id": 2, "method": "DOM.getDocument", "params": {"depth": -1}}))
        doc = json.loads(ws.recv())
        root_node = doc.get("result", {}).get("root", {}).get("nodeId", 0)

        # Find file input
        ws.send(json.dumps({"id": 3, "method": "DOM.querySelector",
                            "params": {"nodeId": root_node, "selector": "input[type='file']"}}))
        q = json.loads(ws.recv())
        input_node = q.get("result", {}).get("nodeId", 0)

        if input_node:
            ws.send(json.dumps({"id": 4, "method": "DOM.setFileInputFiles",
                                "params": {"nodeId": input_node, "files": [abs_path]}}))
            json.loads(ws.recv())
            print(f"    [UP] File set: {os.path.basename(abs_path)}")
        ws.close()

        # Tunggu upload processing
        print("    [UP] Tunggu upload processing...")
        time.sleep(15)

        # Set caption (description field)
        print("    [UP] Set caption...")
        caption_set = cdp_eval(upload_port, f"""
            (() => {{
                // TikTok creator center: contenteditable atau textarea untuk description
                const editors = document.querySelectorAll('[contenteditable="true"], textarea[name="caption"], div[data-placeholder]');
                let captionEl = null;
                for (const el of editors) {{
                    const ph = (el.getAttribute('data-placeholder') || el.getAttribute('placeholder') || '').toLowerCase();
                    if (ph.includes('caption') || ph.includes('description') || ph.includes('write')) {{
                        captionEl = el; break;
                    }}
                }}
                if (!captionEl && editors.length > 0) captionEl = editors[editors.length - 1];
                if (!captionEl) return JSON.stringify({{error: "caption field not found"}});
                captionEl.focus();
                captionEl.click();
                return JSON.stringify({{found: true, tag: captionEl.tagName}});
            }})()
        """)
        if caption_set and json.loads(caption_set).get("found"):
            # Type caption via Input.insertText
            ws2_url = None
            for t in requests.get(f"http://localhost:{upload_port}/json", timeout=5).json():
                if "upload" in t.get("url", "").lower() or "creator" in t.get("url", "").lower():
                    ws2_url = t.get("webSocketDebuggerUrl")
                    break
            if not ws2_url:
                ws2_url = requests.get(f"http://localhost:{upload_port}/json", timeout=5).json()[0].get("webSocketDebuggerUrl")
            ws2 = websocket.create_connection(ws2_url, timeout=30)
            ws2.send(json.dumps({"id": 1, "method": "Input.insertText", "params": {"text": caption[:2200]}}))
            json.loads(ws2.recv())
            ws2.close()
            print(f"    [UP] Caption set: {caption[:60]}...")
        else:
            print("    [UP] ⚠️ Caption field gak ketemu — caption mungkin perlu manual")

        time.sleep(2)

        # Set privacy (kalau ada toggle)
        if privacy == "private":
            cdp_eval(upload_port, """
                (() => {
                    const radios = Array.from(document.querySelectorAll('[role="radio"], input[type="radio"]'));
                    const priv = radios.find(r => (r.innerText||r.getAttribute('aria-label')||'').toLowerCase().includes('private'));
                    if (priv) { priv.click(); return true; }
                    return false;
                })()
            """)
            time.sleep(1)

        # Click Post/Publish button
        print("    [UP] Click Post...")
        post_clicked = cdp_eval(upload_port, """
            (() => {
                const btns = Array.from(document.querySelectorAll('button, div[role="button"]'));
                const post = btns.find(b => {
                    const t = (b.innerText||'').trim().toLowerCase();
                    return t === 'post' || t === 'publish' || t === 'upload';
                });
                if (post) {
                    const rect = post.getBoundingClientRect();
                    return JSON.stringify({x: rect.x + rect.width/2, y: rect.y + rect.height/2});
                }
                return null;
            })()
        """)

        if post_clicked:
            coords = json.loads(post_clicked)
            click_at(upload_port, int(coords["x"]), int(coords["y"]))
            print(f"    [UP] Post clicked at ({coords['x']:.0f}, {coords['y']:.0f})")
            time.sleep(10)
            # Cek success
            result = cdp_eval(upload_port, """
                (() => {
                    const body = document.body.innerText;
                    const success = body.includes('Your video has been') || body.includes('uploaded') || body.includes('Published');
                    const error = body.includes('error') || body.includes('failed');
                    return JSON.stringify({success, error, sample: body.substring(0, 200)});
                })()
            """)
            if result:
                d = json.loads(result)
                if d.get("success"):
                    print("    [UP] ✅ Video posted!")
                    return True
                elif d.get("error"):
                    print(f"    [UP] ❌ Error: {d.get('sample', '')[:150]}")
                    return False
            print("    [UP] ⚠️ Status gak jelas — cek TikTok manual")
            return True  # Assume posted
        else:
            print("    [UP] ❌ Post button gak ketemu")
            return False

    except Exception as e:
        print(f"    [UP] Error: {e}")
        return False
    finally:
        kill_chrome(upload_port)
        print(f"    [UP] Chrome :{upload_port} ditutup")

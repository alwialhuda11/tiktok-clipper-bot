"""Telegram approval flow: kirim preview clip + caption, user approve/reject.
Juga terima video forward dari Telegram -> simpan ke inbox/.
"""
import requests, json, os, time

API_BASE = "https://api.telegram.org"

def _send_message(token, chat_id, text, reply_markup=None):
    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    r = requests.post(url, json=payload, timeout=15)
    return r.json() if r.ok else {"ok": False, "error": r.text}

def _send_video(token, chat_id, video_path, caption, reply_markup=None):
    url = f"{API_BASE}/bot{token}/sendVideo"
    with open(video_path, "rb") as f:
        payload = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        r = requests.post(url, data=payload, files={"video": f}, timeout=60)
    return r.json() if r.ok else {"ok": False, "error": r.text}

def send_clip_preview(token, chat_id, clip_data, video_path):
    """Kirim preview clip ke Telegram untuk approval."""
    caption = f"""🎬 <b>Clip Siap Post</b>

<b>Produk:</b> {clip_data.get('product_name', 'N/A')}
<b>Duration:</b> {clip_data.get('duration', '?')}s
<b>Source:</b> {clip_data.get('source', 'N/A')[:50]}

<b>Caption:</b>
{clip_data.get('caption', '')[:300]}

<b>Promo link:</b> {clip_data.get('promo_link', 'N/A')[:60]}

Approve untuk post ke TikTok?"""

    markup = {"inline_keyboard": [
        [{"text": "✅ Approve & Post", "callback_data": "approve"},
         {"text": "⏭️ Skip", "callback_data": "skip"}]
    ]}

    if video_path and os.path.exists(video_path):
        result = _send_video(token, chat_id, video_path, caption, markup)
    else:
        result = _send_message(token, chat_id, caption, markup)

    if result.get("ok"):
        msg_id = result["result"]["message_id"]
        print(f"    [TG] Preview sent (msg_id={msg_id})")
        return msg_id
    else:
        print(f"    [TG] Error: {result.get('error', 'unknown')[:200]}")
        return None

def poll_approval(token, chat_id, timeout_sec=300):
    """Poll Telegram untuk approval. Return 'approve', 'skip', atau 'timeout'."""
    offset_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state", "tg_offset.txt")
    os.makedirs(os.path.dirname(offset_file), exist_ok=True)

    offset = 0
    if os.path.exists(offset_file):
        with open(offset_file) as f:
            offset = int(f.read().strip() or 0)

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            url = f"{API_BASE}/bot{token}/getUpdates?offset={offset + 1}&timeout=30"
            r = requests.get(url, timeout=35)
            data = r.json()

            for update in data.get("result", []):
                update_id = update.get("update_id", 0)
                offset = max(offset, update_id)

                cb = update.get("callback_query", {})
                if cb:
                    action = cb.get("data", "")
                    cb_id = cb.get("id", "")
                    requests.post(f"{API_BASE}/bot{token}/answerCallbackQuery",
                                  json={"callback_query_id": cb_id}, timeout=10)
                    chat = cb.get("message", {}).get("chat", {}).get("id", chat_id)
                    msg_id = cb.get("message", {}).get("message_id", 0)
                    if msg_id:
                        requests.post(f"{API_BASE}/bot{token}/editMessageReplyMarkup",
                                      json={"chat_id": chat, "message_id": msg_id,
                                            "reply_markup": {"inline_keyboard": []}}, timeout=10)
                    with open(offset_file, "w") as f:
                        f.write(str(offset))
                    if action == "approve":
                        return "approve"
                    elif action == "skip":
                        return "skip"

                msg = update.get("message", {})
                text = msg.get("text", "").lower().strip()
                if text in ("approve", "/approve", "ok", "ya"):
                    with open(offset_file, "w") as f:
                        f.write(str(offset))
                    return "approve"
                elif text in ("skip", "/skip", "no"):
                    with open(offset_file, "w") as f:
                        f.write(str(offset))
                    return "skip"

                # Video forward -> simpan ke inbox/
                video = msg.get("video") or msg.get("document", {})
                if video and (video.get("mime_type", "").startswith("video/") or
                              video.get("file_name", "").endswith((".mp4", ".mov", ".webm"))):
                    file_id = video.get("file_id", "")
                    file_name = video.get("file_name", f"tg_{file_id}.mp4")
                    if file_id:
                        _download_tg_video(token, file_id, file_name)
                        _send_message(token, chat_id, f"📥 Video '{file_name}' disimpan ke inbox/!")

            with open(offset_file, "w") as f:
                f.write(str(offset))

        except Exception as e:
            print(f"    [TG] Poll error: {e}")
            time.sleep(3)

    return "timeout"

def _download_tg_video(token, file_id, file_name):
    """Download video dari Telegram -> simpan ke inbox/."""
    inbox_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "inbox")
    os.makedirs(inbox_dir, exist_ok=True)

    # Get file path
    r = requests.get(f"{API_BASE}/bot{token}/getFile?file_id={file_id}", timeout=15)
    if not r.ok:
        return False
    file_path = r.json().get("result", {}).get("file_path", "")

    # Download
    url = f"{API_BASE}/bot{token}/file/{file_path}"
    out = os.path.join(inbox_dir, file_name)
    r2 = requests.get(url, timeout=60)
    if r2.ok:
        with open(out, "wb") as f:
            f.write(r2.content)
        print(f"    [TG] Video saved: {out} ({len(r2.content)} bytes)")
        return True
    return False

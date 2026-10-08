"""Pipeline utama: inbox/URL -> process clip -> caption -> approve -> post."""
import os, json, time, random, shutil

from . import state
from .clipper import (get_inbox_videos, download_video, process_clip,
                      probe_video, cleanup_old, CLIPS_DIR, INBOX_DIR)
from .captioner import generate_caption, get_product
from .tiktok_api import TikTokClient
from .telegram_flow import send_clip_preview, poll_approval

ROOT = os.path.dirname(os.path.dirname(__file__))

def load_config():
    with open(os.path.join(ROOT, "config", "credentials.json")) as f:
        return json.load(f)

def source_phase(config):
    """Phase 1: Kumpulkan clip dari inbox/ folder atau URL list."""
    print("\n=== PHASE 1: Source Clips ===")
    clips = []

    # Inbox videos (user drop / forward dari Telegram)
    inbox_videos = get_inbox_videos()
    for v in inbox_videos:
        clip_id = os.path.basename(v).rsplit(".", 1)[0]
        if not state.is_posted(clip_id):
            clips.append({"path": v, "clip_id": clip_id, "source": "inbox"})
    print(f"  Inbox videos: {len(inbox_videos)} ({len(clips)} baru)")

    # URL list (opsional — butuh yt-dlp)
    url_file = os.path.join(ROOT, "config", "urls.txt")
    if os.path.exists(url_file):
        with open(url_file) as f:
            urls = [u.strip() for u in f if u.strip() and not u.startswith("#")]
        for url in urls:
            clip_id = "url_" + str(abs(hash(url)))[:10]
            if not state.is_posted(clip_id):
                clips.append({"url": url, "clip_id": clip_id, "source": url[:60]})
        print(f"  URL list: {len(urls)} URLs")

    return clips

def process_phase(config, clips):
    """Phase 2: Process clips (trim + vertical)."""
    print("\n=== PHASE 2: Process Clips ===")
    clip_cfg = config.get("clipping", {})
    max_dur = clip_cfg.get("max_clip_duration_sec", 60)
    out_w = clip_cfg.get("target_width", 720)
    out_h = clip_cfg.get("target_height", 1280)

    processed = []
    for clip in clips[:5]:  # max 5 per batch
        src = clip.get("path")

        # Download kalau URL
        if not src and clip.get("url"):
            src = download_video(clip["url"], max_duration=max_dur)
            if not src:
                continue
            clip["path"] = src

        if not src or not os.path.exists(src):
            continue

        out_path = process_clip(src, max_duration=max_dur,
                                vertical=True, out_width=out_w, out_height=out_h)
        if out_path:
            info = probe_video(out_path)
            clip["processed_path"] = out_path
            clip["duration"] = round(info["duration"], 1)
            processed.append(clip)
            print(f"  ✓ {clip['clip_id']}: {info['duration']:.0f}s, {info['width']}x{info['height']}")

    return processed

def caption_phase(config, processed):
    """Phase 3: Generate caption + match produk."""
    print("\n=== PHASE 3: Generate Caption ===")
    captioned = []
    for clip in processed:
        product = get_product()
        if not product:
            print("  Gak ada produk di config — skip")
            continue
        cap = generate_caption(product, clip.get("source", ""))
        clip.update(cap)
        captioned.append(clip)
        print(f"  ✓ {clip['clip_id']}: {cap['caption'][:60]}...")
    return captioned

def approval_phase(config, captioned):
    """Phase 4: Kirim ke Telegram, tunggu approval."""
    print("\n=== PHASE 4: Telegram Approval ===")
    tg = config.get("telegram", {})
    token = tg.get("bot_token", "")
    chat_id = tg.get("chat_id", "")
    approve_required = config.get("posting", {}).get("approve_required", True)

    if not token or token.startswith("ISI") or not chat_id:
        print("  Telegram belum dikonfigurasi — auto-approve semua")
        return captioned
    if not approve_required:
        print("  approve_required=false — auto-approve")
        return captioned

    approved = []
    for clip in captioned:
        print(f"  Mengirim preview: {clip['clip_id']}")
        msg_id = send_clip_preview(token, chat_id, clip, clip.get("processed_path"))
        if not msg_id:
            continue
        result = poll_approval(token, chat_id, timeout_sec=300)
        if result == "approve":
            print("  ✅ Approved!")
            approved.append(clip)
        elif result == "skip":
            print("  ⏭️ Skipped")
        else:
            print("  ⏰ Timeout")
    return approved

def post_phase(config, approved):
    """Phase 5: Post ke TikTok."""
    print("\n=== PHASE 5: Post ke TikTok ===")
    tiktok = TikTokClient(config.get("tiktok", {}))
    post_mode = config.get("posting", {}).get("post_mode", "api")

    posted = []
    for clip in approved:
        video_path = clip.get("processed_path")
        if not video_path or not os.path.exists(video_path):
            print(f"  Video gak ada: {clip['clip_id']}, skip")
            continue

        caption = clip.get("caption", "")
        print(f"  Posting: {clip['clip_id']} ({clip.get('duration', '?')}s)")

        if post_mode == "api":
            result = tiktok.post_video(video_path, caption)
            if result:
                record = {
                    "clip_id": clip["clip_id"],
                    "publish_id": result.get("publish_id", ""),
                    "product_name": clip.get("product_name", ""),
                    "caption": caption[:200],
                    "duration": clip.get("duration", 0),
                    "source": clip.get("source", ""),
                    "posted_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "mock": result.get("mock", False),
                }
                state.save_posted(record)
                state.record_stat("posted", clip["clip_id"])
                posted.append(record)

                # Move video ke posted/
                posted_dir = os.path.join(ROOT, "posted")
                os.makedirs(posted_dir, exist_ok=True)
                try:
                    shutil.move(video_path, os.path.join(posted_dir, os.path.basename(video_path)))
                except:
                    pass
                print(f"  ✅ Posted! publish_id={result.get('publish_id', 'N/A')}")
            else:
                print(f"  ✗ Gagal post")
                state.record_stat("error", clip["clip_id"])
        else:
            # hybrid/manual: video tetap di clips/, user post manual
            print(f"  [MANUAL] Video di: {video_path}")
            print(f"  [MANUAL] Caption: {caption[:80]}...")
            print(f"  [MANUAL] Product: {clip.get('product_name', '')}")
            print(f"  [MANUAL] Promo link: {clip.get('promo_link', '')}")
            record = {
                "clip_id": clip["clip_id"],
                "publish_id": "",
                "product_name": clip.get("product_name", ""),
                "caption": caption[:200],
                "duration": clip.get("duration", 0),
                "source": clip.get("source", ""),
                "posted_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "mode": "manual",
            }
            state.save_posted(record)
            state.record_stat("manual_queue", clip["clip_id"])
            posted.append(record)
            print(f"  ✅ Queued untuk manual post")

    return posted

def run_pipeline(config_override=None):
    """Jalankan pipeline lengkap."""
    config = config_override or load_config()

    max_per_day = config.get("posting", {}).get("posts_per_day", 3)
    posted_today = state.posted_today()
    if posted_today >= max_per_day:
        print(f"Sudah {posted_today}/{max_per_day} post hari ini. Stop.")
        return []

    remaining = max_per_day - posted_today
    print(f"Pipeline mulai. Limit hari ini: {remaining} post lagi.")

    # Phase 1-5
    clips = source_phase(config)
    if not clips:
        print("Tidak ada clip baru. Stop.")
        return []

    processed = process_phase(config, clips)
    if not processed:
        print("Tidak ada clip yang berhasil diproses. Stop.")
        return []

    captioned = caption_phase(config, processed)
    if not captioned:
        print("Tidak ada caption yang di-generate. Stop.")
        return []

    approved = approval_phase(config, captioned)
    if not approved:
        print("Tidak ada yang di-approve. Stop.")
        return []

    posted = post_phase(config, approved)

    # Cleanup
    cleanup_old(days=7)

    print(f"\n=== SELESAI ===")
    print(f"Posted: {len(posted)} clip")
    return posted

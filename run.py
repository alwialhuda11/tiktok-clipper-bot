#!/usr/bin/env python3
"""TikTok Auto-Clipper Bot — entry point.

Commands:
  python3 run.py run          # Jalankan pipeline lengkap
  python3 run.py status       # Lihat status (posted hari ini, inbox, stats)
  python3 run.py inbox        # List video di inbox/
  python3 run.py cleanup      # Hapus clips lama
"""
import sys, os

sys.path.insert(0, os.path.dirname(__file__))

from bot import state
from bot.pipeline import run_pipeline, load_config
from bot.clipper import get_inbox_videos, CLIPS_DIR, INBOX_DIR

def cmd_run():
    print("=" * 60)
    print("  TIKTOK AUTO-CLIPPER BOT — pipeline run")
    print("=" * 60)
    config = load_config()
    mode = config.get("mode", "mock")
    print(f"Mode: {mode}")
    if mode == "mock":
        print("  (Mock mode: pakai fake data, gak post beneran ke TikTok)")
    print()
    posted = run_pipeline()
    print(f"\nSelesai. {len(posted)} clip dipost.")

def cmd_status():
    config = load_config()
    mode = config.get("mode", "mock")
    inbox_videos = get_inbox_videos()
    print(f"Mode: {mode}")
    print(f"Posted hari ini: {state.posted_today()}")
    print(f"Total posted: {len(state.get_posted())}")
    print(f"Queue: {len(state.get_queue())}")
    print(f"Inbox videos: {len(inbox_videos)}")
    for v in inbox_videos[:5]:
        print(f"  - {os.path.basename(v)}")
    print()
    stats = state.get_stats(days=7)
    if stats:
        print("Stats 7 hari terakhir:")
        for date, day_stats in sorted(stats.items(), reverse=True):
            posted_count = day_stats.get("posted", 0)
            manual = day_stats.get("manual_queue", 0)
            errors = day_stats.get("error", 0)
            print(f"  {date}: posted={posted_count} manual={manual} errors={errors}")

def cmd_inbox():
    inbox_videos = get_inbox_videos()
    print(f"Inbox videos ({len(inbox_videos)}):")
    for v in inbox_videos:
        size = os.path.getsize(v) / (1024 * 1024)
        print(f"  {os.path.basename(v)} ({size:.1f} MB)")
    if not inbox_videos:
        print("  (kosong — drop video ke folder inbox/ atau forward ke Telegram bot)")

def cmd_cleanup():
    from bot.clipper import cleanup_old
    cleanup_old(days=7)
    print("Old clips cleaned up (7+ hari).")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1].lower()
    if cmd == "run":
        cmd_run()
    elif cmd == "status":
        cmd_status()
    elif cmd == "inbox":
        cmd_inbox()
    elif cmd == "cleanup":
        cmd_cleanup()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)

if __name__ == "__main__":
    main()

"""State: dedup clip, daily limits, stats."""
import json, os, datetime

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state")
POSTED_FILE = os.path.join(STATE_DIR, "posted.json")
QUEUE_FILE = os.path.join(STATE_DIR, "queue.json")
STATS_FILE = os.path.join(STATE_DIR, "stats.json")

def _load(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    return default

def _save(path, data):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)

def get_posted():
    return _load(POSTED_FILE, [])

def is_posted(clip_id):
    return any(p.get("clip_id") == clip_id for p in get_posted())

def save_posted(record):
    posted = get_posted()
    posted.append(record)
    if len(posted) > 500:
        posted = posted[-500:]
    _save(POSTED_FILE, posted)

def posted_today():
    today = datetime.date.today().isoformat()
    return sum(1 for p in get_posted() if p.get("posted_date", "").startswith(today))

def get_queue():
    return _load(QUEUE_FILE, [])

def enqueue(clip):
    q = get_queue()
    if any(c.get("clip_id") == clip.get("clip_id") for c in q):
        return
    q.append(clip)
    _save(QUEUE_FILE, q)

def dequeue(clip_id):
    q = [c for c in get_queue() if c.get("clip_id") != clip_id]
    _save(QUEUE_FILE, q)

def get_queue_item(clip_id):
    for c in get_queue():
        if c.get("clip_id") == clip_id:
            return c
    return None

def record_stat(event, detail=""):
    stats = _load(STATS_FILE, {})
    today = datetime.date.today().isoformat()
    day = stats.setdefault(today, {})
    day[event] = day.get(event, 0) + 1
    if detail:
        day.setdefault("details", []).append(detail)
    _save(STATS_FILE, stats)

def get_stats(days=7):
    stats = _load(STATS_FILE, {})
    keys = sorted(stats.keys())[-days:]
    return {k: stats[k] for k in keys}

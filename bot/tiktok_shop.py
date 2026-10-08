"""TikTok Shop: detect produk viral + match ke produk affiliate kita.

Cara kerja:
- Search TikTok: "lagi viral tiktok shop", "klik keranjang kuning", hashtag #TikTokMadeMeBuyIt
- Extract caption + hashtag + views dari video search results
- Hitung frekuensi keyword/hashtag -> ranking trending
- Match trending signals ke products.json (affiliate produk kita) by keyword overlap
- Discover product ID dari video viral (anchor produk) -> disimpan buat user
  tambahin ke affiliate center (product ID tanpa aff_id = gak track komisi,
  jadi ini purely sinyal buat user pilih produk)

catatan: shop.tiktok.com direct dari VPS kena 502 -> deteksi via TikTok search aja.
"""
import time, re, json, os, collections
from .chrome_cdp import launch_chrome, kill_chrome, cdp_eval, navigate

ROOT = os.path.dirname(os.path.dirname(__file__))
STATE_DIR = os.path.join(ROOT, "state")
SHOP_PORT = 9233

TRENDING_QUERIES = [
    "lagi viral tiktok shop",
    "tiktok shop viral recommendation",
    "klik keranjang kuning viral",
    "TikTokMadeMeBuyIt viral",
    "produk viral tiktok shop indonesia",
]

SHOP_INDICATORS = [
    "kranjang", "keranjang", "klik keranjang", "klik kranjang", "cart",
    "tiktok shop", "tiktokshop", "checkout", "beli sekarang", "diskon",
    "free ongkir", "gratis ongkir", "cod", "promo",
]

def detect_trending(product_keywords=None, port=SHOP_PORT, max_queries=5):
    """Detect hashtag + keyword trending dari TikTok search.
    
    Returns: {"hashtags": [{tag, count}], "captions": [...], "queries_used": [...]}
    """
    print(f"  [SHOP] Launch Chrome :{port} buat trending scan...")
    if not launch_chrome(port):
        print("  [SHOP] Gak bisa launch Chrome")
        return {"hashtags": [], "captions": [], "queries_used": []}

    queries = list(TRENDING_QUERIES)
    if product_keywords:
        for kw in product_keywords[:3]:
            queries.append(f"{kw} viral tiktok shop")

    hashtags = collections.Counter()
    shop_captions = []
    used = []

    try:
        for q in queries[:max_queries]:
            qq = q.replace(" ", "%20")
            print(f"  [SHOP] Scan: '{q}'...")
            navigate(port, f"https://www.tiktok.com/search?q={qq}", wait=8)
            cdp_eval(port, "window.scrollBy(0, 800)", 4)
            time.sleep(2)

            data = cdp_eval(port, """
                (() => {
                    const links = Array.from(document.querySelectorAll('a[href*="/video/"]'));
                    const seen = new Set();
                    const out = [];
                    for (const link of links) {
                        const href = link.href.split('?')[0];
                        if (seen.has(href)) continue;
                        seen.add(href);
                        let el = link, text = '';
                        for (let i = 0; i < 6 && el; i++) {
                            el = el.parentElement;
                            if (el) text = el.innerText || '';
                            if (text.length > 40) break;
                        }
                        out.push({url: href, text: text.substring(0, 300)});
                        if (out.length >= 15) break;
                    }
                    return JSON.stringify(out);
                })()
            """)
            items = json.loads(data) if data else []
            if not items:
                # Retry sekali — TikTok kadang rate-limit rapid headless queries
                print(f"    [SHOP] 0 hasil, retry setelah 10s...")
                time.sleep(10)
                navigate(port, f"https://www.tiktok.com/search?q={qq}", wait=10)
                cdp_eval(port, "window.scrollBy(0, 800)", 4)
                time.sleep(3)
                data = cdp_eval(port, """
                    (() => {
                        const links = Array.from(document.querySelectorAll('a[href*="/video/"]'));
                        const seen = new Set();
                        const out = [];
                        for (const link of links) {
                            const href = link.href.split('?')[0];
                            if (seen.has(href)) continue;
                            seen.add(href);
                            let el = link, text = '';
                            for (let i = 0; i < 6 && el; i++) {
                                el = el.parentElement;
                                if (el) text = el.innerText || '';
                                if (text.length > 40) break;
                            }
                            out.push({url: href, text: text.substring(0, 300)});
                            if (out.length >= 15) break;
                        }
                        return JSON.stringify(out);
                    })()
                """)
                items = json.loads(data) if data else []
            if not items:
                print(f"    [SHOP] 0 hasil lagi, skip query ini")
                continue
            print(f"    [SHOP] {len(items)} items terkumpul")
            used.append(q)
            # Random delay antar query (anti rate-limit)
            time.sleep(5 + hash(q) % 6)
            for item in items:
                text = item.get("text", "")
                low = text.lower()
                # Hashtags dari caption
                for tag in re.findall(r"#(\w+)", text):
                    hashtags[tag.lower()] += 1
                # Caption yang ada indikator shop = sinyal produk viral
                if any(ind in low for ind in SHOP_INDICATORS):
                    shop_captions.append({"url": item.get("url", ""), "text": text[:200]})
    finally:
        kill_chrome(port)
        print(f"  [SHOP] Chrome :{port} ditutup")

    top_tags = [{"tag": t, "count": c} for t, c in hashtags.most_common(20)]
    print(f"  [SHOP] Trending: {len(top_tags)} hashtags, {len(shop_captions)} shop captions")
    return {"hashtags": top_tags, "captions": shop_captions[:20], "queries_used": used}

def match_products(trending, products):
    """Match trending signals ke produk affiliate kita.
    
    Score = keyword overlap antara product keywords/hashtags/Name
            dengan trending hashtags + shop captions.
    Returns: produk sorted by score desc.
    """
    if not trending or not products:
        return products or []

    trend_text = " ".join(t["tag"] for t in trending.get("hashtags", []))
    trend_text += " " + " ".join(c.get("text", "").lower() for c in trending.get("captions", []))
    trend_text = trend_text.lower()

    scored = []
    for p in products:
        score = 0
        for kw in p.get("keywords", []) + p.get("hashtags", []):
            kw_l = kw.lower().lstrip("#")
            if kw_l and kw_l in trend_text:
                score += 3
        # keyword name match per kata
        for word in re.findall(r"\w+", p.get("name", "").lower()):
            if len(word) > 4 and word in trend_text:
                score += 1
        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    print("  [SHOP] Product match scores:")
    for s, p in scored:
        print(f"    {s:>3}  {p.get('name', '')[:50]}")
    return [p for s, p in scored]

def save_discovered_products(trending, limit=10):
    """Simpan caption viral (berisi produk) ke state/ buat review user."""
    os.makedirs(STATE_DIR, exist_ok=True)
    path = os.path.join(STATE_DIR, "trending_products.json")
    existing = []
    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)
    seen = {e.get("text", "")[:80] for e in existing}
    added = 0
    for c in trending.get("captions", []):
        key = c.get("text", "")[:80]
        if key not in seen and added < limit:
            existing.append({"text": c.get("text", ""), "url": c.get("url", ""),
                             "found_at": time.strftime("%Y-%m-%d %H:%M")})
            seen.add(key)
            added += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing[-100:], f, indent=2, ensure_ascii=False)
    if added:
        print(f"  [SHOP] {added} produk viral disimpan ke state/trending_products.json")
    return added

def load_products():
    path = os.path.join(ROOT, "config", "products.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)

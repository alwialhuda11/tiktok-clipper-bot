"""Auto-source: cari video produk viral di TikTok via search page (CDP),
kumpulkan URL video teratas, download via yt-dlp.
"""
import time, re, json
from .chrome_cdp import launch_chrome, kill_chrome, cdp_eval, navigate

SEARCH_PORT = 9230

def search_product_videos(keywords, min_views=5000, max_videos_per_keyword=3,
                          search_port=SEARCH_PORT):
    """Cari video TikTok per keyword via search page.
    
    Returns: list of {"url", "keyword", "views_str", "author"}
    """
    print(f"  [AUTO] Launch Chrome :{search_port} buat search...")
    if not launch_chrome(search_port):
        print("  [AUTO] Gak bisa launch Chrome")
        return []

    results = []
    seen_urls = set()

    try:
        for kw in keywords[:5]:
            q = kw.replace(" ", "%20")
            url = f"https://www.tiktok.com/search?q={q}"
            print(f"  [AUTO] Search: '{kw}'...")
            navigate(search_port, url, wait=8)

            # Deteksi login wall
            lw = cdp_eval(search_port, """
                (() => {
                    const body = document.body.innerText;
                    const loginWall = body.includes('Log in to TikTok') || body.includes('Login to TikTok');
                    return JSON.stringify({loginWall, sample: body.substring(0, 120)});
                })()
            """)
            if lw:
                d = json.loads(lw)
                if d.get("loginWall"):
                    print("  [AUTO] Login wall terdeteksi — search tetap dicoba (TikTok sering tetap nampilin hasil)")
            
            # Scroll sekali biar results load
            cdp_eval(search_port, "window.scrollBy(0, 800)", 5)
            time.sleep(3)

            # Kumpulkan video links + engagement
            collected = cdp_eval(search_port, """
                (() => {
                    const links = Array.from(document.querySelectorAll('a[href*="/video/"]'));
                    const seen = new Set();
                    const out = [];
                    for (const link of links) {
                        const href = link.href.split('?')[0];
                        if (seen.has(href)) continue;
                        seen.add(href);
                        // Container terdekat buat ambil text (views/likes)
                        let el = link;
                        let text = '';
                        for (let i = 0; i < 6 && el; i++) {
                            el = el.parentElement;
                            if (el) text = el.innerText || '';
                            if (text.match(/\d+[KM]?\s*(views|likes)/i) || text.length > 40) break;
                        }
                        out.push({url: href, text: text.substring(0, 200)});
                        if (out.length >= 15) break;
                    }
                    return JSON.stringify(out);
                })()
            """)

            if not collected:
                continue
            for item in json.loads(collected):
                vurl = item.get("url", "")
                if not vurl or vurl in seen_urls:
                    continue
                seen_urls.add(vurl)
                text = item.get("text", "")
                # Extract views — TikTok web sering tampilin cuma "23.4K" tanpa kata "views"
                # Strategy: ambil SEMUA angka standalone (baris sendiri, dgn/tnpa K/M), ambil terbesar
                views = 0
                m = re.search(r"([\d.]+)\s*([KM])?\s*views", text, re.I)
                if m:
                    num = float(m.group(1))
                    mult = {"K": 1000, "M": 1000000}.get((m.group(2) or "").upper(), 1)
                    views = int(num * mult)
                else:
                    # Pattern 2: standalone number lines "23.4K" / "1.2M" / "4567"
                    for line in text.split("\n"):
                        line = line.strip()
                        lm = re.fullmatch(r"([\d.]+)([KMkmb])?", line)
                        if lm:
                            try:
                                num = float(lm.group(1))
                            except ValueError:
                                continue
                            suffix = (lm.group(2) or "").upper()
                            mult = {"K": 1000, "M": 1000000, "B": 1000000000}.get(suffix)
                            if mult is None:
                                # Bare number (no suffix) — could be views or date; only take if < 10M (plausible views)
                                if num < 10000000:
                                    v = int(num)
                                    if v > views:
                                        views = v
                            else:
                                v = int(num * mult)
                                if v > views:
                                    views = v
                # author dari URL: /@username/video/
                am = re.search(r"/@([^/]+)/", vurl)
                author = am.group(1) if am else ""
                results.append({"url": vurl, "keyword": kw, "views": views,
                                "views_str": text[:50], "author": author})
    finally:
        kill_chrome(search_port)
        print(f"  [AUTO] Chrome :{search_port} ditutup")

    # Filter + sort by views + limit
    filtered = [r for r in results if r["views"] >= min_views] if min_views else results
    filtered.sort(key=lambda r: r["views"], reverse=True)
    # Ambil max per keyword
    per_kw = {}
    picked = []
    for r in filtered:
        k = r["keyword"]
        per_kw.setdefault(k, 0)
        if per_kw[k] < max_videos_per_keyword:
            per_kw[k] += 1
            picked.append(r)

    print(f"  [AUTO] Total {len(results)} video ditemukan, {len(picked)} lolos filter "
          f"(min_views={min_views})")
    return picked

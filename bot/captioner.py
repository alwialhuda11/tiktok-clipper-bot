"""Generate caption TikTok: hook + body + CTA + hashtag + disclosure.
Support product matching by trending score.
"""
import json, os, random, re

ROOT = os.path.dirname(os.path.dirname(__file__))
CAPTIONS_PATH = os.path.join(ROOT, "config", "captions.json")
PRODUCTS_PATH = os.path.join(ROOT, "config", "products.json")

def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_products():
    return _load_json(PRODUCTS_PATH)

def get_product(product_id=None):
    """Ambil produk dari config. Random kalau gak specify."""
    products = load_products()
    if not products:
        return None
    if product_id:
        for p in products:
            if p.get("id") == product_id:
                return p
    return random.choice(products)

def get_product_by_trending(trending_signals=None):
    """Pilih produk berdasarkan trending signals (dari tiktok_shop.detect_trending)."""
    products = load_products()
    if not products:
        return None
    if not trending_signals:
        return random.choice(products)
    
    # Score each product by keyword overlap dengan trending hashtags/captions
    trend_text = " ".join(t.get("tag", "") for t in trending_signals.get("hashtags", []))
    trend_text += " " + " ".join(c.get("text", "").lower() for c in trending_signals.get("captions", []))
    trend_text = trend_text.lower()
    
    scored = []
    for p in products:
        score = 0
        for kw in p.get("keywords", []) + p.get("hashtags", []):
            kw_l = kw.lower().lstrip("#")
            if kw_l and kw_l in trend_text:
                score += 3
        for word in re.findall(r"\w+", p.get("name", "").lower()):
            if len(word) > 4 and word in trend_text:
                score += 1
        scored.append((score, p))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    # Pilih dari top 3 (randomize biar gak monoton)
    top = [p for s, p in scored[:3] if s > 0]
    if top:
        chosen = random.choice(top)
        print(f"    [CAP] Trending match: {chosen.get('name', '')} (score={scored[0][0]})")
        return chosen
    return random.choice(products)

def generate_caption(product, clip_source=""):
    """Generate caption lengkap: hook + body + CTA + hashtag + disclosure."""
    tpl = _load_json(CAPTIONS_PATH)
    hook = random.choice(tpl.get("hooks", ["Worth it banget"]))
    body = random.choice(tpl.get("bodies", ["Oke banget"]))
    cta = random.choice(tpl.get("ctas", ["Cek di TikTok Shop!"]))
    
    category = product.get("category", "product")
    hashtags_raw = product.get("hashtags", [category])
    hashtags = " ".join(f"#{h.lstrip('#')}" for h in hashtags_raw[:8])
    
    caption = f"{hook} {body}. {cta} {hashtags} #ad"
    
    if len(caption) > 2200:
        caption = caption[:2190] + "..."
    
    return {
        "caption": caption,
        "hook": hook,
        "body": body,
        "cta": cta,
        "hashtags": hashtags,
        "product_name": product.get("name", ""),
        "promo_link": product.get("promo_link", ""),
    }

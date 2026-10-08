"""Generate caption TikTok: hook + body + CTA + hashtag + disclosure."""
import json, os, random

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

def generate_caption(product, clip_source=""):
    """Generate caption lengkap: hook + body + CTA + hashtag + disclosure."""
    tpl = _load_json(CAPTIONS_PATH)
    hook = random.choice(tpl.get("hooks", ["Worth it banget"]))
    body = random.choice(tpl.get("bodies", ["Oke banget"]))
    cta = random.choice(tpl.get("ctas", ["Cek di TikTok Shop!"]))
    
    category = product.get("category", "product")
    hashtags_raw = product.get("hashtags", [category])
    hashtags = " ".join(f"#{h.lstrip('#')}" for h in hashtags_raw[:8])
    
    # Format: hook + body + CTA + hashtags + disclosure
    caption = f"{hook} {body}. {cta} {hashtags} #ad"
    
    # Max 2200 chars (TikTok limit), tapi idealnya < 150 buat readability
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

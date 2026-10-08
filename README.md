# TikTok Auto-Clipper Bot

Bot TikTok auto-clipper: process clip video produk affiliate, generate caption, approve via Telegram, post ke TikTok.

## Pipeline

```
1. Source clips (inbox/ folder + Telegram forward + URL list)
        ↓
2. Process clip (trim max 60s + re-encode vertikal 9:16 via ffmpeg)
        ↓
3. Generate caption (hook + body + CTA + hashtag + #ad disclosure)
        ↓
4. Kirim ke Telegram -> lo approve/reject
        ↓
5. Post ke TikTok (Content Posting API / manual hybrid mode)
```

## Setup (sekali)

### 1. Install dependencies
```bash
/usr/bin/pip3 install -r requirements.txt
```

### 2. Isi credentials
```bash
cp config/credentials.example.json config/credentials.json
```

| Field | Dari mana | Wajib? |
|-------|-----------|--------|
| `telegram.bot_token` + `chat_id` | @BotFather / @userinfobot | Recommended |
| `tiktok.client_key` + `client_secret` | developers.tiktok.com | Ya (untuk live mode) |
| `tiktok.access_token` | Jalankan `python3 get_tiktok_token.py` | Ya (untuk live mode) |

### 3. Isi produk affiliate
Edit `config/products.json` — tambah produk TikTok Shop Affiliate lo:
```json
{
  "id": "prod_001",
  "name": "Nama Produk",
  "category": "skincare",
  "promo_link": "https://shop.tiktok.com/view/product/...?aff_id=...",
  "hashtags": ["skincare", "serum", "tiktokshop"]
}
```

### 4. Masukkan clip
- **Drop video** ke folder `inbox/` (video seller dari TikTok Shop collaboration = rights-cleared)
- **Forward video** ke Telegram bot (auto-simpan ke inbox/)
- **URL list** di `config/urls.txt` (butuh yt-dlp)

### 5. Test pipeline (mock mode)
```bash
/usr/bin/python3 run.py run
/usr/bin/python3 run.py status
/usr/bin/python3 run.py inbox
```

### 6. Switch ke live mode
```bash
/usr/bin/python3 get_tiktok_token.py
```
Lalu ubah `"mode": "mock"` -> `"mode": "live"` di credentials.json.

## Post Mode

| Mode | Cara kerja |
|------|-----------|
| `api` | Auto-post via Content Posting API. **App belum audit = video PRIVATE (SELF_ONLY)**. Setelah audit TikTok, baru PUBLIC. |
| `hybrid` | Bot siapkan semua (clip + caption + product link), lo post manual di TikTok app + attach product basket. |
| `description_only` | Post via API + promo link di caption. |

**Product basket (keranjang kuning):** TikTok Content Posting API **gak support** attach product basket secara programmatic. Product basket harus di-attach manual di TikTok app. Jadi:
- `api` mode: video post + caption (product link di caption)
- `hybrid` mode: lo post manual + attach basket di app (paling optimal buat affiliate)

## Commands

```bash
/usr/bin/python3 run.py run       # Pipeline lengkap
/usr/bin/python3 run.py status    # Status hari ini
/usr/bin/python3 run.py inbox     # List video di inbox/
/usr/bin/python3 run.py cleanup   # Hapus clips lama
```

## Config

### Products (config/products.json)
Daftar produk TikTok Shop Affiliate. Setiap produk: name, category, promo_link, hashtags.

### Captions (config/captions.json)
Edit hooks, bodies, ctas, hashtags. Template: `{hook} {body}. {cta} {hashtags} #ad`

### Clipping (config/credentials.json -> clipping)
- `max_clip_duration_sec`: trim video ke durasi maks
- `target_width/height`: resolusi output (default 720x1280 vertikal)
- `trim_enabled`: trim on/off

## TikTok Shop Affiliate — Cara Kerja

1. Daftar TikTok Shop Affiliate (creator account)
2. Browse Affiliate Product Marketplace -> pilih produk
3. Seller share video promo yang **boleh creator repost** (rights-cleared)
4. Download video seller -> drop ke `inbox/` atau forward ke Telegram
5. Bot process + post dengan product basket di-attach manual di app

**Rights:** Video dari seller collaboration = rights-cleared untuk repost. Video dari URL lain = pastikan ada izin dulu.

## Rate Limits

- TikTok Content Posting API: **6 request/menit** per user access_token
- Daily post limit: edit `posts_per_day` di credentials.json

## Troubleshooting

**"yt-dlp belum terinstall"** — `/usr/bin/pip3 install yt-dlp` (butuh buat URL clipping)

**"Mode: mock" tapi mau live** — isi credentials + `python3 get_tiktok_token.py` + ubah mode ke `"live"`

**Video post PRIVATE** — App belum di-audit TikTok. Submit untuk audit di developers.tiktok.com -> My Apps -> Audit. Setelah approve, gak ada lagi restriction.

**"Tidak ada clip baru"** — Drop video ke `inbox/` atau forward ke Telegram bot.

**ffmpeg error** — Pastikan ffmpeg terinstall. Default path: `/home/ubuntu/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffmpeg`

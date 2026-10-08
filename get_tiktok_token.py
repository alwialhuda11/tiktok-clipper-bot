#!/usr/bin/env python3
"""Helper: dapat TikTok access token via OAuth2.

Cara pakai:
1. Daftar di developers.tiktok.com -> Create app -> scope video.publish + video.upload
2. Isi client_key + client_secret di config/credentials.json
3. Jalankan: python3 get_tiktok_token.py
4. Buka URL yang muncul di browser, login TikTok, authorize
5. Copy code dari URL redirect, paste di terminal
6. Token otomatis disimpan ke credentials.json

NOTE: App belum di-audit = video post SELF_ONLY (private). Setelah audit, PUBLIC.
"""
import os, sys, json, requests

API_BASE = "https://open.tiktokapis.com"
CRED_PATH = os.path.join(os.path.dirname(__file__), "config", "credentials.json")

def main():
    if not os.path.exists(CRED_PATH):
        print("credentials.json belum ada. Copy dari example dulu:")
        print("  cp config/credentials.example.json config/credentials.json")
        sys.exit(1)

    with open(CRED_PATH) as f:
        creds = json.load(f)

    tc = creds.get("tiktok", {})
    client_key = tc.get("client_key", "")
    client_secret = tc.get("client_secret", "")

    if not client_key or not client_secret:
        print("Isi client_key + client_secret dulu di config/credentials.json")
        sys.exit(1)

    # Step 1: Generate authorization URL
    redirect_uri = "https://localhost"
    scope = "user.info.basic,video.upload,video.publish"
    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize/?"
        f"client_key={client_key}"
        f"&scope={scope}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
    )

    print("=" * 60)
    print("  TIKTOK OAuth2 — Ambil Access Token")
    print("=" * 60)
    print()
    print("1. Buka URL ini di browser:")
    print()
    print(f"   {auth_url}")
    print()
    print("2. Login TikTok, authorize app")
    print("3. Copy code dari URL redirect (atau full URL)")
    print()

    code = input("Paste code atau full redirect URL: ").strip()
    if "code=" in code:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(code)
        code = parse_qs(parsed.query).get("code", [code])[0]

    print(f"\nCode: {code[:20]}...")
    print("Exchanging for access token...")

    # Step 2: Exchange code for token
    r = requests.post(f"{API_BASE}/oauth/token/", data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }, timeout=30)

    if not r.ok:
        print(f"Error: {r.status_code} — {r.text}")
        sys.exit(1)

    data = r.json()

    # Step 3: Save to credentials.json
    import time
    tc["access_token"] = data.get("access_token", "")
    tc["refresh_token"] = data.get("refresh_token", "")
    tc["expires_at"] = time.time() + data.get("expires_in", 86400)

    creds["tiktok"] = tc
    with open(CRED_PATH, "w") as f:
        json.dump(creds, f, indent=2, ensure_ascii=False)

    print("\n✅ Token disimpan ke credentials.json!")
    print(f"   Access token: {data.get('access_token', '')[:20]}...")
    print(f"   Expires in: {data.get('expires_in', 'N/A')} seconds")
    print("\nSekarang jalankan: python3 run.py run (test pipeline)")

if __name__ == "__main__":
    main()

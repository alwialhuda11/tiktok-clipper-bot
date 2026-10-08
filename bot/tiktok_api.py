"""TikTok Content Posting API client — mock mode tanpa credentials.

Flow Direct Post:
1. POST /v2/post/publish/video/init/ -> dapat upload_url + publish_id
2. Upload video file ke upload_url (multipart)
3. Poll /v2/post/publish/status/fetch/ sampai COMPLETE

Scope: video.publish (direct post) atau video.upload (upload only, post manual)
Rate limit: 6 request/menit per user access_token
Note: app belum di-audit = video post SELF_ONLY (private). Setelah audit, PUBLIC.
"""
import os, json, time, random, string, subprocess
import requests

API_BASE = "https://open.tiktokapis.com"

class TikTokClient:
    def __init__(self, creds):
        self.creds = creds
        self.mock = not creds.get("access_token") or creds.get("access_token", "").startswith("ISI")
        self.token = creds.get("access_token", "")
        self.refresh_token = creds.get("refresh_token", "")
        self.client_key = creds.get("client_key", "")
        self.client_secret = creds.get("client_secret", "")
        self.expires_at = creds.get("expires_at", 0)
        self.post_mode = creds.get("_post_mode", "SELF_ONLY")

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _refresh_if_needed(self):
        if self.mock:
            return
        if self.expires_at and time.time() > self.expires_at - 3600:
            try:
                r = requests.post(f"{API_BASE}/oauth/token/", data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                }, timeout=30)
                if r.ok:
                    data = r.json()
                    self.token = data.get("access_token", self.token)
                    self.refresh_token = data.get("refresh_token", self.refresh_token)
                    self.expires_at = time.time() + data.get("expires_in", 86400)
                    self.creds["access_token"] = self.token
                    self.creds["refresh_token"] = self.refresh_token
                    self.creds["expires_at"] = self.expires_at
            except Exception as e:
                print(f"    [TT] Refresh error: {e}")

    def post_video(self, video_path, caption, privacy_level=None):
        """Post video via Content Posting API (Direct Post flow).
        
        Returns: {"publish_id": ..., "status": ..., "mock": bool}
        """
        self._refresh_if_needed()
        
        if self.mock:
            publish_id = "mock_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
            print(f"    [TT MOCK] Video posted: {publish_id}")
            print(f"    [TT MOCK] Privacy: {self.post_mode}")
            print(f"    [TT MOCK] Caption: {caption[:60]}...")
            return {"publish_id": publish_id, "status": "COMPLETE", "mock": True}

        if not privacy_level:
            privacy_level = self.post_mode  # SELF_ONLY dulu sampai audit

        # Step 1: init
        init_payload = {
            "post_info": {
                "title": caption[:2200],
                "privacy_level": privacy_level,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": os.path.getsize(video_path),
            },
        }
        
        try:
            r = requests.post(f"{API_BASE}/v2/post/publish/video/init/",
                              headers=self._headers(), json=init_payload, timeout=30)
            
            if r.status_code == 429:
                print(f"    [TT] Rate limited (6/min), tunggu 60s...")
                time.sleep(60)
                r = requests.post(f"{API_BASE}/v2/post/publish/video/init/",
                                  headers=self._headers(), json=init_payload, timeout=30)
            
            r.raise_for_status()
            init_data = r.json()
            upload_url = init_data.get("data", {}).get("upload_url", "")
            publish_id = init_data.get("data", {}).get("publish_id", "")
            
            if not upload_url:
                print(f"    [TT] Init error: {json.dumps(init_data)[:300]}")
                return None
            
            # Step 2: upload video
            with open(video_path, "rb") as fp:
                upload_r = requests.post(upload_url, files={"video": fp}, timeout=120)
            upload_r.raise_for_status()
            
            # Step 3: poll status
            for _ in range(30):
                time.sleep(3)
                status_r = requests.post(f"{API_BASE}/v2/post/publish/status/fetch/",
                                         headers=self._headers(),
                                         json={"publish_id": publish_id}, timeout=15)
                if status_r.ok:
                    status_data = status_r.json().get("data", {})
                    status = status_data.get("status", "")
                    if status == "SEND_TO_USER_INBOX_COMPLETE":
                        print(f"    [TT] Posted! publish_id={publish_id}")
                        return {"publish_id": publish_id, "status": "COMPLETE", "mock": False}
                    elif status in ("FAILED", "UNKNOWN"):
                        print(f"    [TT] Post failed: {status_data.get('fail_reason', '')}")
                        return None
            
            print(f"    [TT] Timeout polling status")
            return {"publish_id": publish_id, "status": "PENDING", "mock": False}
            
        except Exception as e:
            print(f"    [TT] Post error: {e}")
            return None

    def get_creator_info(self):
        """Query creator info (privacy options, etc)."""
        self._refresh_if_needed()
        if self.mock:
            return {"privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"]}
        try:
            r = requests.post(f"{API_BASE}/v2/post/publish/creator_info/query/",
                              headers=self._headers(), timeout=15)
            return r.json().get("data", {})
        except Exception as e:
            print(f"    [TT] creator_info error: {e}")
            return {}

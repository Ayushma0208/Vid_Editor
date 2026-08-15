import asyncio
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from app.config import settings
from app.database import database
from app.services.cloudinary_service import CloudinaryService

INSTAGRAM_OAUTH_SCOPES = ",".join(
    [
        "instagram_business_basic",
        "instagram_business_content_publish",
    ]
)
INSTAGRAM_GRAPH_BASE = "https://graph.instagram.com/v21.0"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _http_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        text = (response.text or "").strip()
        return text[:400] or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str) and err.strip():
            return err.strip()
        desc = payload.get("error_description") or payload.get("message")
        if desc:
            return str(desc)
    return f"HTTP {response.status_code}"


def _extract_instagram_short_token(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return "", ""
    data = payload.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        item = data[0]
        return str(item.get("access_token") or ""), str(item.get("user_id") or "")
    return str(payload.get("access_token") or ""), str(payload.get("user_id") or "")


class PublishService:
    def _oauth_collection(self):
        return database["oauth_states"]

    def _token_collection(self):
        return database["user_tokens"]

    async def create_youtube_oauth_url(self, user_id: str, redirect_uri: str) -> str:
        if not settings.youtube_client_id or not settings.youtube_client_secret:
            raise ValueError("YouTube OAuth is not configured. Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET.")
        state = secrets.token_urlsafe(24)
        code_verifier = secrets.token_urlsafe(64)
        challenge = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(challenge).decode("utf-8").rstrip("=")

        await self._oauth_collection().insert_one(
            {
                "state": state,
                "user_id": user_id,
                "platform": "youtube",
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            }
        )

        query = urlencode(
            {
                "client_id": settings.youtube_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "https://www.googleapis.com/auth/youtube.upload",
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    async def complete_youtube_oauth(self, state: str, code: str) -> dict[str, Any]:
        state_doc = await self._oauth_collection().find_one({"state": state, "platform": "youtube"})
        if not state_doc:
            raise ValueError("Invalid OAuth state")
        if _as_utc(state_doc["expires_at"]) < datetime.now(timezone.utc):
            raise ValueError("Expired OAuth state")

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.youtube_client_id,
                    "client_secret": settings.youtube_client_secret,
                    "redirect_uri": state_doc["redirect_uri"],
                    "grant_type": "authorization_code",
                    "code_verifier": state_doc["code_verifier"],
                },
            )
            if not response.is_success:
                raise ValueError(_http_error_detail(response))
            token_payload = response.json()

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_payload.get("expires_in", 3600))
        await self._token_collection().update_one(
            {"user_id": state_doc["user_id"], "platform": "youtube"},
            {
                "$set": {
                    "user_id": state_doc["user_id"],
                    "platform": "youtube",
                    "access_token": token_payload["access_token"],
                    "refresh_token": token_payload.get("refresh_token"),
                    "expires_at": expires_at,
                }
            },
            upsert=True,
        )
        await self._oauth_collection().delete_one({"_id": state_doc["_id"]})
        return {"platform": "youtube", "status": "connected"}

    async def create_instagram_oauth_url(self, user_id: str, redirect_uri: str) -> str:
        if not settings.instagram_app_id or not settings.instagram_app_secret:
            raise ValueError("Instagram OAuth is not configured. Set INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET.")
        state = secrets.token_urlsafe(24)
        await self._oauth_collection().insert_one(
            {
                "state": state,
                "user_id": user_id,
                "platform": "instagram",
                "redirect_uri": redirect_uri,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            }
        )
        query = urlencode(
            {
                "client_id": settings.instagram_app_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": INSTAGRAM_OAUTH_SCOPES,
                "state": state,
            }
        )
        return f"https://www.instagram.com/oauth/authorize?{query}"

    async def complete_instagram_oauth(self, state: str, code: str) -> dict[str, Any]:
        state_doc = await self._oauth_collection().find_one({"state": state, "platform": "instagram"})
        if not state_doc:
            raise ValueError("Invalid OAuth state")
        if _as_utc(state_doc["expires_at"]) < datetime.now(timezone.utc):
            raise ValueError("Expired OAuth state")

        code = (code or "").split("#", 1)[0].strip()
        async with httpx.AsyncClient(timeout=30) as client:
            token_resp = await client.post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": settings.instagram_app_id,
                    "client_secret": settings.instagram_app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": state_doc["redirect_uri"],
                    "code": code,
                },
            )
            if not token_resp.is_success:
                raise ValueError(_http_error_detail(token_resp))
            short_token, scoped_user_id = _extract_instagram_short_token(token_resp.json())
            if not short_token:
                raise ValueError("Instagram did not return an access token")

            access_token = short_token
            expires_in = 3600
            ll_resp = await client.get(
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": settings.instagram_app_secret,
                    "access_token": short_token,
                },
            )
            if ll_resp.is_success:
                ll_payload = ll_resp.json()
                access_token = ll_payload.get("access_token") or short_token
                expires_in = int(ll_payload.get("expires_in") or 5184000)

            me_resp = await client.get(
                f"{INSTAGRAM_GRAPH_BASE}/me",
                params={
                    "fields": "id,user_id,username,account_type,name",
                    "access_token": access_token,
                },
            )
            if not me_resp.is_success:
                raise ValueError(_http_error_detail(me_resp))
            me = me_resp.json()

        ig_user_id = str(me.get("user_id") or me.get("id") or scoped_user_id or "").strip()
        if not ig_user_id:
            raise ValueError(
                "Could not read this Instagram account. Convert it to Creator or Business, then reconnect."
            )

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        await self._token_collection().update_one(
            {"user_id": state_doc["user_id"], "platform": "instagram"},
            {
                "$set": {
                    "user_id": state_doc["user_id"],
                    "platform": "instagram",
                    "access_token": access_token,
                    "refresh_token": None,
                    "expires_at": expires_at,
                    "ig_user_id": ig_user_id,
                    "ig_username": me.get("username"),
                    "ig_account_type": me.get("account_type"),
                    "auth_type": "instagram_login",
                },
                "$unset": {"page_id": "", "user_access_token": ""},
            },
            upsert=True,
        )
        await self._oauth_collection().delete_one({"_id": state_doc["_id"]})
        return {
            "platform": "instagram",
            "status": "connected",
            "ig_user_id": ig_user_id,
            "username": me.get("username"),
        }

    async def upload_youtube(
        self,
        user_id: str,
        clip: Any,
        description: str = "",
        title: str = "",
    ) -> dict[str, Any]:
        token = await self._token_collection().find_one({"user_id": user_id, "platform": "youtube"})
        if not token:
            raise ValueError("YouTube account is not connected")
        if not clip.cloudinary_clip_url:
            raise ValueError("Clip cloudinary URL is missing")

        temp_dir = Path(settings.temp_dir) / "publish" / str(clip.id)
        temp_dir.mkdir(parents=True, exist_ok=True)
        local_path = str(temp_dir / "clip.mp4")
        cloudinary_service = CloudinaryService()
        await cloudinary_service.download_to_path(clip.cloudinary_clip_url, local_path)

        title = (title or clip.label or f"Clip {clip.id}").strip()
        if clip.duration <= 60 and "#Shorts" not in title:
            title = f"{title} #Shorts"

        credentials = Credentials(
            token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
        youtube = build("youtube", "v3", credentials=credentials)
        body = {
            "snippet": {
                "title": title,
                "description": description,
            },
            "status": {"privacyStatus": "public"},
        }
        media = MediaFileUpload(local_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = await asyncio.to_thread(request.execute)
        if credentials.token and credentials.token != token.get("access_token"):
            await self._token_collection().update_one(
                {"user_id": user_id, "platform": "youtube"},
                {
                    "$set": {
                        "access_token": credentials.token,
                        "refresh_token": credentials.refresh_token or token.get("refresh_token"),
                        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=3500),
                    }
                },
            )
        video_id = response["id"]
        return {
            "youtube_video_id": video_id,
            "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
            "status": "published",
            "local_path": local_path,
        }

    async def upload_instagram(self, user_id: str, clip: Any, caption: str = "") -> dict[str, Any]:
        token = await self._token_collection().find_one({"user_id": user_id, "platform": "instagram"})
        if not token:
            raise ValueError("Instagram account is not connected")
        if not clip.cloudinary_clip_url:
            raise ValueError("Clip cloudinary URL is missing")
        ig_user_id = token.get("ig_user_id")
        if not ig_user_id:
            raise ValueError("Instagram professional account is not connected")

        access_token = token["access_token"]
        async with httpx.AsyncClient(timeout=30) as client:
            create_resp = await client.post(
                f"{INSTAGRAM_GRAPH_BASE}/{ig_user_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": clip.cloudinary_clip_url,
                    "caption": caption,
                    "access_token": access_token,
                },
            )
            if not create_resp.is_success:
                raise ValueError(_http_error_detail(create_resp))
            creation_id = create_resp.json()["id"]

            for _ in range(60):
                status_resp = await client.get(
                    f"{INSTAGRAM_GRAPH_BASE}/{creation_id}",
                    params={"fields": "status_code", "access_token": access_token},
                )
                if not status_resp.is_success:
                    raise ValueError(_http_error_detail(status_resp))
                status_code = status_resp.json().get("status_code")
                if status_code == "FINISHED":
                    break
                if status_code == "ERROR":
                    raise RuntimeError("Instagram rejected the video while processing")
                await asyncio.sleep(5)
            else:
                raise RuntimeError("Instagram media processing timed out")

            publish_resp = await client.post(
                f"{INSTAGRAM_GRAPH_BASE}/{ig_user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": access_token},
            )
            if not publish_resp.is_success:
                raise ValueError(_http_error_detail(publish_resp))
            media_id = publish_resp.json()["id"]

            permalink_resp = await client.get(
                f"{INSTAGRAM_GRAPH_BASE}/{media_id}",
                params={"fields": "permalink", "access_token": access_token},
            )
            permalink = None
            if permalink_resp.is_success:
                permalink = permalink_resp.json().get("permalink")

        return {"instagram_media_id": media_id, "permalink": permalink, "status": "published"}

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


class PublishService:
    def _oauth_collection(self):
        return database["oauth_states"]

    def _token_collection(self):
        return database["user_tokens"]

    async def create_youtube_oauth_url(self, user_id: str, redirect_uri: str) -> str:
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
        if state_doc["expires_at"] < datetime.now(timezone.utc):
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
            response.raise_for_status()
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
                "scope": "instagram_basic,instagram_content_publish,pages_show_list",
                "response_type": "code",
                "state": state,
            }
        )
        return f"https://www.facebook.com/v19.0/dialog/oauth?{query}"

    async def complete_instagram_oauth(self, state: str, code: str) -> dict[str, Any]:
        state_doc = await self._oauth_collection().find_one({"state": state, "platform": "instagram"})
        if not state_doc:
            raise ValueError("Invalid OAuth state")
        if state_doc["expires_at"] < datetime.now(timezone.utc):
            raise ValueError("Expired OAuth state")

        async with httpx.AsyncClient(timeout=30) as client:
            token_resp = await client.get(
                "https://graph.facebook.com/v19.0/oauth/access_token",
                params={
                    "client_id": settings.instagram_app_id,
                    "client_secret": settings.instagram_app_secret,
                    "redirect_uri": state_doc["redirect_uri"],
                    "code": code,
                },
            )
            token_resp.raise_for_status()
            token_payload = token_resp.json()
            access_token = token_payload["access_token"]

            pages_resp = await client.get(
                "https://graph.facebook.com/v19.0/me/accounts",
                params={"access_token": access_token, "fields": "instagram_business_account"},
            )
            pages_resp.raise_for_status()
            pages = pages_resp.json().get("data", [])
            ig_user_id = None
            for page in pages:
                ig_obj = page.get("instagram_business_account")
                if ig_obj and ig_obj.get("id"):
                    ig_user_id = ig_obj["id"]
                    break

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_payload.get("expires_in", 3600))
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
                }
            },
            upsert=True,
        )
        await self._oauth_collection().delete_one({"_id": state_doc["_id"]})
        return {"platform": "instagram", "status": "connected", "ig_user_id": ig_user_id}

    async def upload_youtube(self, user_id: str, clip: Any, description: str = "") -> dict[str, Any]:
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

        title = clip.label or f"Clip {clip.id}"
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
            raise ValueError("Instagram business account not linked")

        async with httpx.AsyncClient(timeout=30) as client:
            create_resp = await client.post(
                f"https://graph.facebook.com/v19.0/{ig_user_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": clip.cloudinary_clip_url,
                    "caption": caption,
                    "access_token": token["access_token"],
                },
            )
            create_resp.raise_for_status()
            creation_id = create_resp.json()["id"]

            for _ in range(60):
                status_resp = await client.get(
                    f"https://graph.facebook.com/v19.0/{creation_id}",
                    params={"fields": "status_code", "access_token": token["access_token"]},
                )
                status_resp.raise_for_status()
                status_code = status_resp.json().get("status_code")
                if status_code == "FINISHED":
                    break
                await asyncio.sleep(5)
            else:
                raise RuntimeError("Instagram media processing timed out")

            publish_resp = await client.post(
                f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": token["access_token"]},
            )
            publish_resp.raise_for_status()
            media_id = publish_resp.json()["id"]

            permalink_resp = await client.get(
                f"https://graph.facebook.com/v19.0/{media_id}",
                params={"fields": "permalink", "access_token": token["access_token"]},
            )
            permalink_resp.raise_for_status()
            permalink = permalink_resp.json().get("permalink")

        return {"instagram_media_id": media_id, "permalink": permalink, "status": "published"}

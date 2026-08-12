import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class CopyPoolError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        code: str | None = None,
        errors: list[dict[str, Any]] | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.errors = errors or []
        self.retry_after = retry_after


class CopyPoolService:
    """Proxy client for the external copy-pool description API."""

    def _base_url(self) -> str:
        base = (settings.copy_pool_base_url or "").strip().rstrip("/")
        if not base:
            raise CopyPoolError(
                "Copy pool is not configured. Set COPY_POOL_BASE_URL.",
                status_code=503,
                code="NOT_CONFIGURED",
            )
        return base

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        api_key = (settings.copy_pool_api_key or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _build_filter_params(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        date_field: str | None = None,
        order: str | None = None,
        extract_status: str | None = None,
        enabled: bool | None = None,
        q: str | None = None,
        hashtag: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if date_field:
            params["dateField"] = date_field
        if order:
            params["order"] = order
        if extract_status:
            params["extractStatus"] = extract_status
        if enabled is not None:
            params["enabled"] = str(enabled).lower()
        if q:
            params["q"] = q[:80]
        if hashtag:
            params["hashtag"] = hashtag.lstrip("#")
        return params

    async def get_random_description(
        self,
        *,
        exclude: list[str] | None = None,
        since: str | None = None,
        until: str | None = None,
        date_field: str | None = None,
        extract_status: str | None = None,
        enabled: bool | None = True,
        q: str | None = None,
        hashtag: str | None = None,
    ) -> dict[str, Any]:
        params = self._build_filter_params(
            since=since,
            until=until,
            date_field=date_field,
            extract_status=extract_status,
            enabled=enabled,
            q=q,
            hashtag=hashtag,
        )
        if exclude:
            # API allows max 50 ids
            params["exclude"] = ",".join(exclude[:50])

        url = f"{self._base_url()}/api/copy-pool/descriptions/random"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params, headers=self._headers())

        if response.status_code == 404:
            payload = self._safe_json(response)
            raise CopyPoolError(
                str(payload.get("message") or "No eligible descriptions in the copy pool"),
                status_code=404,
                code=str(payload.get("code") or "NOT_FOUND"),
            )
        if response.status_code == 429:
            payload = self._safe_json(response)
            retry_after = None
            raw = response.headers.get("Retry-After")
            if raw and raw.isdigit():
                retry_after = int(raw)
            raise CopyPoolError(
                str(payload.get("message") or "Rate limit exceeded"),
                status_code=429,
                code=str(payload.get("code") or "RATE_LIMITED"),
                retry_after=retry_after,
            )
        if response.status_code == 400:
            payload = self._safe_json(response)
            raise CopyPoolError(
                str(payload.get("message") or "Validation failed"),
                status_code=400,
                code=str(payload.get("code") or "VALIDATION_ERROR"),
                errors=list(payload.get("errors") or []),
            )
        if response.status_code >= 400:
            logger.warning("Copy pool random failed: %s %s", response.status_code, response.text[:300])
            raise CopyPoolError(
                "Copy pool request failed",
                status_code=502,
                code="UPSTREAM_ERROR",
            )

        payload = self._safe_json(response)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not str(data.get("description") or "").strip():
            raise CopyPoolError(
                "Copy pool returned an empty description",
                status_code=502,
                code="EMPTY_RESPONSE",
            )
        return {
            "id": str(data.get("id") or ""),
            "description": str(data.get("description") or "").strip(),
            "title": data.get("title"),
            "caption": data.get("caption"),
            "hashtags": data.get("hashtags") or [],
            "keywords": data.get("keywords") or [],
            "sourceUrl": data.get("sourceUrl"),
            "extractStatus": data.get("extractStatus"),
            "extractedAt": data.get("extractedAt"),
            "createdAt": data.get("createdAt"),
        }

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

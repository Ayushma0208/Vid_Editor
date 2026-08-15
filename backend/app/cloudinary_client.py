import logging
from urllib.parse import urlparse

import cloudinary

from app.config import settings

logger = logging.getLogger(__name__)


def _cloud_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").strip()


def _configure_cloudinary() -> None:
    """Prefer explicit credentials so a truncated CLOUDINARY_URL cannot win."""
    cloud_name = (settings.cloudinary_cloud_name or "").strip()
    api_key = (settings.cloudinary_api_key or "").strip()
    api_secret = (settings.cloudinary_api_secret or "").strip()
    url = (settings.cloudinary_url or "").strip()
    url_cloud = _cloud_name_from_url(url) if url else ""

    if cloud_name and url_cloud and cloud_name != url_cloud:
        logger.warning(
            "CLOUDINARY_URL cloud_name %r does not match CLOUDINARY_CLOUD_NAME %r; using CLOUDINARY_CLOUD_NAME",
            url_cloud,
            cloud_name,
        )

    if cloud_name and api_key and api_secret:
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )
        return

    if url:
        cloudinary.config(cloudinary_url=url, secure=True)


_configure_cloudinary()

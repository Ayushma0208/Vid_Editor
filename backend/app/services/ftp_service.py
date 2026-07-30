from __future__ import annotations

import io
from ftplib import FTP, FTP_TLS, error_perm
from pathlib import PurePosixPath
from urllib.parse import quote

from app.config import settings


class FtpStorageError(RuntimeError):
    pass


class FtpStorageService:
    def is_configured(self) -> bool:
        return bool(settings.ftp_host and settings.ftp_user and settings.ftp_password)

    def _connect(self) -> FTP:
        host = settings.ftp_host
        port = settings.ftp_port
        user = settings.ftp_user
        password = settings.ftp_password

        # Prefer explicit FTPS (cPanel), fall back to plain FTP.
        try:
            ftp: FTP = FTP_TLS()
            ftp.connect(host, port, timeout=60)
            ftp.login(user, password)
            ftp.prot_p()
            ftp.set_pasv(True)
            return ftp
        except Exception:
            ftp = FTP()
            ftp.connect(host, port, timeout=60)
            ftp.login(user, password)
            ftp.set_pasv(True)
            return ftp

    def _chdir_or_mkdir(self, ftp: FTP, remote_dir: str) -> None:
        remote_dir = remote_dir.strip() or "/"
        if remote_dir in {"/", "."}:
            return

        parts = [p for p in PurePosixPath(remote_dir).parts if p not in ("/", ".")]
        if remote_dir.startswith("/"):
            try:
                ftp.cwd("/")
            except error_perm:
                pass

        for part in parts:
            try:
                ftp.cwd(part)
            except error_perm:
                try:
                    ftp.mkd(part)
                    ftp.cwd(part)
                except error_perm as exc:
                    raise FtpStorageError(f"Could not create/enter remote directory '{part}': {exc}") from exc

    def upload_bytes(self, data: bytes, remote_filename: str, subdir: str = "") -> str:
        if not self.is_configured():
            raise FtpStorageError("FTP is not configured")

        filename = PurePosixPath(remote_filename).name
        if not filename:
            raise FtpStorageError("Remote filename is required")

        clean_subdir = subdir.strip().strip("/")
        ftp = self._connect()
        try:
            base = (settings.ftp_remote_dir or "/").strip() or "/"
            self._chdir_or_mkdir(ftp, base)
            if clean_subdir:
                self._chdir_or_mkdir(ftp, clean_subdir)

            bio = io.BytesIO(data)
            ftp.storbinary(f"STOR {filename}", bio)
        finally:
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass

        public_base = (settings.ftp_public_base_url or "").rstrip("/")
        if not public_base:
            raise FtpStorageError("FTP_PUBLIC_BASE_URL is not configured")

        encoded_name = quote(filename)
        if clean_subdir:
            encoded_subdir = "/".join(quote(p) for p in clean_subdir.split("/"))
            return f"{public_base}/{encoded_subdir}/{encoded_name}"
        return f"{public_base}/{encoded_name}"

"""
Bhoonidhi API client -- authentication, search, and download with robust error handling.

Credentials are read from environment variables:
  BHOONIDHI_USER_ID
  BHOONIDHI_PASSWORD

Downloads are saved as ZIP files and auto-extracted.
GeoTIFF / raster files inside the ZIP are returned for QGIS / GEE use.
"""

from __future__ import annotations

import os
import re
import time
import zipfile
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("BHOONIDHI_BASE_URL", "https://bhoonidhi-api.nrsc.gov.in").rstrip("/")

def get_download_dir() -> Path:
    """Return a verified writable download directory, prioritizing the local workspace directory."""
    env_dir = os.environ.get("BHOONIDHI_DOWNLOAD_DIR")
    candidates: list[Path] = []
    if env_dir:
        candidates.append(Path(env_dir))
    # Prefer project workspace downloads folder
    candidates.append(Path(__file__).resolve().parent / "downloads")
    candidates.append(Path.home() / "Downloads" / "bhoonidhi_data")
    candidates.append(Path("/tmp/bhoonidhi_downloads"))

    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            test_file = c / ".write_test"
            test_file.touch(exist_ok=True)
            test_file.unlink(missing_ok=True)
            return c
        except Exception:
            continue

    fallback = Path(__file__).resolve().parent / "downloads"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return fallback

DOWNLOAD_DIR = get_download_dir()

# Raster extensions found inside Bhoonidhi product ZIPs
RASTER_EXTENSIONS = {".tif", ".tiff", ".img", ".hdf", ".h5", ".nc", ".vrt"}

# Module-level token cache
_token_lock = threading.Lock()
_token_cache: dict[str, Any] = {
    "access_token": None,
    "refresh_token": None,
    "expires_at": 0.0,
}


# ---------------------------------------------------------------------------
# Custom Exceptions for Bhoonidhi Error Handling Layer
# ---------------------------------------------------------------------------

class BhoonidhiError(Exception):
    """Base exception for all Bhoonidhi client errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BhoonidhiAuthError(BhoonidhiError):
    """Raised when authentication fails (invalid credentials, bad format, expired token)."""
    pass


class BhoonidhiTimeoutError(BhoonidhiError):
    """Raised when an API request times out."""
    pass


class BhoonidhiRateLimitError(BhoonidhiError):
    """Raised when rate limit is exceeded (HTTP 429)."""
    pass


class BhoonidhiDateRangeError(BhoonidhiError):
    """Raised when date range exceeds API limits (e.g. 366 days / HTTP 406)."""
    pass


class BhoonidhiGatewayError(BhoonidhiError):
    """Raised when server / gateway errors occur (HTTP 500, 502, 503, 504)."""
    pass


class BhoonidhiNetworkError(BhoonidhiError):
    """Raised when network connectivity or DNS resolution fails."""
    pass


class BhoonidhiDownloadError(BhoonidhiError):
    """Raised when product download or decompression fails."""
    pass


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def _store_tokens(data: dict) -> None:
    with _token_lock:
        _token_cache["access_token"] = data["access_token"]
        _token_cache["refresh_token"] = data.get("refresh_token")
        _token_cache["expires_at"] = time.time() + data.get("expires_in", 1200) - 60


def authenticate(timeout: int = 30) -> str:
    """
    Obtain a fresh access token using userId + password.
    Raises BhoonidhiAuthError, BhoonidhiTimeoutError, or BhoonidhiNetworkError.
    """
    user_id = os.environ.get("BHOONIDHI_USER_ID", "").strip()
    password = os.environ.get("BHOONIDHI_PASSWORD", "").strip()

    if not user_id or not password:
        raise BhoonidhiAuthError(
            "BHOONIDHI_USER_ID and BHOONIDHI_PASSWORD must be configured in .env",
            details={"type": "missing_credentials"}
        )

    token_url = f"{BASE_URL}/auth/token"
    payload = {"userId": user_id, "password": password, "grant_type": "password"}

    try:
        resp = requests.post(token_url, json=payload, timeout=timeout)
    except requests.Timeout:
        raise BhoonidhiTimeoutError(
            f"Authentication request to Bhoonidhi ({token_url}) timed out after {timeout}s.",
            details={"url": token_url}
        )
    except requests.ConnectionError as exc:
        raise BhoonidhiNetworkError(
            f"Failed to connect to Bhoonidhi authentication gateway at {token_url}. "
            f"Check your internet connection or NRSC gateway status.",
            details={"error": str(exc)}
        )
    except Exception as exc:
        raise BhoonidhiError(f"Unexpected connection error during authentication: {exc}")

    if resp.status_code == 400:
        err_msg = resp.text
        try:
            err_msg = resp.json().get("Action", resp.json().get("Description", err_msg))
        except Exception:
            pass
        if "-" in user_id or "@" in user_id:
            raise BhoonidhiAuthError(
                f"400 Bad Request: Bhoonidhi rejected userId '{user_id}'. "
                "Bhoonidhi API does not accept hyphens (-) or @ in userId.",
                details={"status_code": 400, "user_id": user_id, "response": err_msg}
            )
        raise BhoonidhiAuthError(f"400 Bad Request: {err_msg}", details={"status_code": 400, "response": err_msg})

    if resp.status_code == 401:
        raise BhoonidhiAuthError(
            "401 Unauthorized: Invalid username or password. Please verify your Bhoonidhi credentials.",
            details={"status_code": 401}
        )

    if resp.status_code == 429:
        raise BhoonidhiRateLimitError(
            "429 Too Many Requests: Rate limit exceeded on Bhoonidhi authentication endpoint.",
            details={"status_code": 429}
        )

    if resp.status_code >= 500:
        raise BhoonidhiGatewayError(
            f"Bhoonidhi Server Error (HTTP {resp.status_code}) during authentication.",
            details={"status_code": resp.status_code, "text": resp.text[:200]}
        )

    try:
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise BhoonidhiAuthError("Bhoonidhi auth response missing 'access_token' field.", details={"data": data})
        _store_tokens(data)
        return data["access_token"]
    except Exception as exc:
        if isinstance(exc, BhoonidhiError):
            raise
        raise BhoonidhiAuthError(f"Failed to parse auth token from Bhoonidhi response: {exc}")


def _refresh_access_token(timeout: int = 30) -> str:
    """Refresh the access token using the cached refresh token, falling back to full authentication."""
    with _token_lock:
        refresh_token = _token_cache.get("refresh_token")
    if not refresh_token:
        return authenticate(timeout=timeout)

    user_id = os.environ.get("BHOONIDHI_USER_ID", "").strip()
    payload = {
        "userId": user_id,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    try:
        resp = requests.post(f"{BASE_URL}/auth/token", json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if "access_token" in data:
                _store_tokens(data)
                return data["access_token"]
        return authenticate(timeout=timeout)
    except Exception:
        return authenticate(timeout=timeout)


def get_valid_token() -> str:
    """Return a cached valid token, refreshing if expired."""
    with _token_lock:
        token = _token_cache["access_token"]
        expires_at = _token_cache["expires_at"]
    if token and time.time() < expires_at:
        return token
    return _refresh_access_token()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_stac(
    collections: list[str],
    start_date: str,
    end_date: str,
    bbox: list[float],
    limit: int = 200,
    online_only: bool = True,
    timeout: int = 90,
) -> list[dict]:
    """
    Search Bhoonidhi STAC catalogue and return a list of STAC feature dicts.
    Robustly handles timeouts, pagination, and error categorization.
    """
    token = get_valid_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    datetime_str = f"{start_date}T00:00:00Z/{end_date}T23:59:59Z"
    payload: dict[str, Any] = {
        "collections": collections,
        "datetime": datetime_str,
        "bbox": bbox,
        "limit": min(limit, 500),
    }
    if online_only:
        payload["filter"] = {"args": [{"property": "Online"}, "Y"], "op": "eq"}
        payload["filter-lang"] = "cql2-json"

    features: list[dict] = []
    url = f"{BASE_URL}/data/search"

    while url:
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.Timeout:
            raise BhoonidhiTimeoutError(
                f"Bhoonidhi STAC search request timed out after {timeout}s. "
                "For dense SAR collections (e.g. Sentinel-1A), please narrow your AOI bounding box or reduce the observation window to <= 30 days.",
                details={"collections": collections, "bbox": bbox, "datetime": datetime_str}
            )
        except requests.ConnectionError as exc:
            raise BhoonidhiNetworkError(
                f"Network connection failure while querying Bhoonidhi STAC catalog: {exc}",
                details={"error": str(exc)}
            )
        except Exception as exc:
            raise BhoonidhiError(f"Unexpected error querying Bhoonidhi search endpoint: {exc}")

        if resp.status_code == 401:
            try:
                token = _refresh_access_token()
                headers["Authorization"] = f"Bearer {token}"
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            except requests.Timeout:
                raise BhoonidhiTimeoutError("Bhoonidhi STAC search timed out during token refresh retry.")
            except Exception as exc:
                raise BhoonidhiAuthError(f"Re-authentication failed during search: {exc}")

        if resp.status_code == 404:
            break

        if resp.status_code == 406:
            raise BhoonidhiDateRangeError(
                "406 Not Acceptable: Observation window exceeds the Bhoonidhi maximum limit of 366 days.",
                details={"status_code": 406}
            )

        if resp.status_code == 429:
            raise BhoonidhiRateLimitError(
                "429 Too Many Requests: Rate limit exceeded on Bhoonidhi STAC search API. Please wait a few moments before searching again.",
                details={"status_code": 429}
            )

        if resp.status_code in (502, 503, 504):
            raise BhoonidhiGatewayError(
                f"Bhoonidhi Gateway Timeout / Server Overload (HTTP {resp.status_code}). "
                "The server took too long to scan the catalog for this AOI and date range. "
                "Try narrowing your bounding box or selecting a 7-day or 30-day window.",
                details={"status_code": resp.status_code}
            )

        if resp.status_code >= 400:
            detail = ""
            try:
                err = resp.json()
                detail = f"{err.get('Description','')} {err.get('Action','')}".strip()
            except Exception:
                detail = resp.text[:200]
            raise BhoonidhiError(
                f"Bhoonidhi API error (HTTP {resp.status_code}): {detail}",
                details={"status_code": resp.status_code, "detail": detail}
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise BhoonidhiError(f"Failed to parse JSON response from Bhoonidhi search: {exc}")

        features.extend(data.get("features", []))

        url = None
        for link in data.get("links", []):
            if link.get("rel") == "next":
                url = link.get("href")
                payload = {}
                break

    return features


# ---------------------------------------------------------------------------
# Size pre-check (HEAD request — no data transferred)
# ---------------------------------------------------------------------------

def get_file_size_mb(item_id: str, collection: str, timeout: int = 15) -> float | None:
    """
    Issue a HEAD request to the Bhoonidhi download endpoint to get Content-Length.
    Returns size in MB, or None if not reported.
    """
    try:
        token = get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        params = {"id": item_id, "collection": collection}
        resp = requests.head(
            f"{BASE_URL}/download",
            headers=headers,
            params=params,
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            length = resp.headers.get("Content-Length")
            if length:
                return round(int(length) / (1024 * 1024), 1)
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Quicklook preview (thumbnail / browse image)
# ---------------------------------------------------------------------------

def get_quicklook_url(feature: dict) -> str | None:
    """
    Extract a quicklook / thumbnail URL from a STAC feature dict.
    """
    assets = feature.get("assets", {})
    for key in ("thumbnail", "overview", "quicklook", "browse"):
        asset = assets.get(key, {})
        href = asset.get("href") or asset.get("url")
        if href:
            return href

    for link in feature.get("links", []):
        rel = link.get("rel", "").lower()
        if rel in ("thumbnail", "overview", "quicklook", "browse", "preview"):
            href = link.get("href")
            if href:
                return href

    item_id = feature.get("id", "")
    collection = feature.get("collection", "")
    if item_id and collection:
        return f"{BASE_URL}/data/browse?id={item_id}&collection={collection}"

    return None


def fetch_quicklook(feature: dict, timeout: int = 20) -> bytes | None:
    """
    Fetch the quicklook image bytes for a STAC feature.
    Returns raw bytes or None on failure.
    """
    url = get_quicklook_url(feature)
    if not url:
        return None
    try:
        token = get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        ct = resp.headers.get("Content-Type", "")
        if resp.status_code == 200 and ("image" in ct or len(resp.content) > 1000):
            return resp.content
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Download and Extraction
# ---------------------------------------------------------------------------

def _extract_zip(zip_path: Path) -> list[Path]:
    """
    Extract downloaded ZIP and return paths to raster files inside it.
    """
    if not zipfile.is_zipfile(zip_path):
        return [zip_path] if zip_path.suffix.lower() in RASTER_EXTENSIONS else []

    extract_dir = zip_path.parent / zip_path.stem
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    except Exception as exc:
        raise BhoonidhiDownloadError(f"Corrupted or incomplete ZIP archive for {zip_path.name}: {exc}")

    rasters = [
        p for p in extract_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in RASTER_EXTENSIONS
    ]
    return rasters


def _download_single(
    item_id: str,
    collection: str,
    progress_callback: Optional[Callable[[float], None]] = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """
    Download one product ZIP from Bhoonidhi, auto-extract it.
    """
    token = get_valid_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {"id": item_id, "collection": collection}

    try:
        resp = requests.get(
            f"{BASE_URL}/download",
            headers=headers,
            params=params,
            stream=True,
            timeout=timeout,
        )
    except requests.Timeout:
        raise BhoonidhiTimeoutError(f"Download connection for scene '{item_id}' timed out.")
    except requests.ConnectionError as exc:
        raise BhoonidhiNetworkError(f"Download connection failed for scene '{item_id}': {exc}")

    if resp.status_code == 401:
        token = _refresh_access_token()
        headers["Authorization"] = f"Bearer {token}"
        try:
            resp = requests.get(
                f"{BASE_URL}/download",
                headers=headers,
                params=params,
                stream=True,
                timeout=timeout,
            )
        except Exception as exc:
            raise BhoonidhiDownloadError(f"Failed to retry download after token refresh: {exc}")

    if resp.status_code == 403 or resp.status_code == 401:
        raise BhoonidhiAuthError(
            f"Access denied for downloading product '{item_id}'. "
            "Please check if your Bhoonidhi account has permission for this dataset."
        )

    if resp.status_code == 404:
        raise BhoonidhiDownloadError(
            f"Product '{item_id}' not found in collection '{collection}' on Bhoonidhi download endpoint."
        )

    if resp.status_code >= 400:
        raise BhoonidhiDownloadError(f"Download failed with HTTP {resp.status_code}: {resp.text[:200]}")

    cd = resp.headers.get("Content-Disposition", "")
    if "filename=" in cd:
        filename = cd.split("filename=")[-1].strip().strip('"')
    else:
        ct = resp.headers.get("Content-Type", "")
        ext = ".tif" if "tiff" in ct.lower() else ".zip"
        filename = item_id + ext

    save_dir = DOWNLOAD_DIR / collection / item_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / filename

    downloaded = 0
    total = int(resp.headers.get("Content-Length", 0)) or None

    try:
        with open(save_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if chunk:
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total:
                        progress_callback(min(downloaded / total, 1.0))
    except Exception as exc:
        if save_path.exists():
            save_path.unlink()
        raise BhoonidhiDownloadError(f"Failed writing downloaded stream to disk: {exc}")

    rasters = _extract_zip(save_path)

    return {
        "zip_path": str(save_path),
        "raster_files": [str(r) for r in rasters],
        "collection": collection,
    }


def download_products(
    items: list[dict],
    max_workers: int = 3,
    progress_callbacks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Download multiple products concurrently (max 5 per Bhoonidhi limit).
    Returns dict mapping item_id -> {'status': 'ok'|'error', ...}
    """
    max_workers = min(max_workers, 5)
    progress_callbacks = progress_callbacks or {}
    results: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                _download_single,
                item["id"],
                item["collection"],
                progress_callbacks.get(item["id"]),
            ): item["id"]
            for item in items
        }
        for future in as_completed(future_map):
            item_id = future_map[future]
            try:
                result = future.result()
                results[item_id] = {"status": "ok", **result}
            except Exception as exc:
                results[item_id] = {"status": "error", "error": str(exc)}

    return results

"""Strict parsing helpers for the configured public HTTP origin."""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import urlsplit


class PublicOriginError(ValueError):
    def __init__(self, reason: str = "public_origin_invalid"):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CanonicalOrigin:
    scheme: str
    hostname: str
    effective_port: int
    normalized_host: str
    normalized_netloc: str


_BAD_HOST_CHARS = re.compile(r"[\s\x00-\x20\x7f]")


def _canonical_host(hostname: str) -> tuple[str, str]:
    if not hostname or hostname == "*" or _BAD_HOST_CHARS.search(hostname):
        raise PublicOriginError()
    try:
        address = ipaddress.ip_address(hostname)
        normalized = address.compressed.lower()
        return normalized, f"[{normalized}]" if address.version == 6 else normalized
    except ValueError:
        pass
    if ":" in hostname or "*" in hostname:
        raise PublicOriginError()
    try:
        normalized = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise PublicOriginError() from exc
    if not normalized or len(normalized) > 253:
        raise PublicOriginError()
    labels = normalized.split(".")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels):
        raise PublicOriginError()
    if any(not re.fullmatch(r"[a-z0-9-]+", label) for label in labels):
        raise PublicOriginError()
    return normalized, normalized


def _from_parts(scheme: str, hostname: str, port: int | None) -> CanonicalOrigin:
    scheme = scheme.lower()
    if scheme not in ("http", "https"):
        raise PublicOriginError()
    normalized_host, display_host = _canonical_host(hostname)
    default_port = 80 if scheme == "http" else 443
    effective_port = default_port if port is None else port
    if not 1 <= effective_port <= 65535:
        raise PublicOriginError()
    netloc = display_host if effective_port == default_port else f"{display_host}:{effective_port}"
    return CanonicalOrigin(scheme, normalized_host, effective_port, normalized_host, netloc)


def parse_public_origin(value: str | None) -> CanonicalOrigin:
    """Parse TEDDY_PUBLIC_ORIGIN; only an origin and optional trailing slash are allowed."""
    if value is None or not str(value).strip():
        raise PublicOriginError("public_origin_missing")
    value = str(value)
    if value != value.strip() or "?" in value or "#" in value:
        raise PublicOriginError()
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
            raise PublicOriginError()
        if parts.username is not None or parts.password is not None:
            raise PublicOriginError()
        if parts.netloc.endswith(":"):
            raise PublicOriginError()
        if parts.path not in ("", "/") or parts.query or parts.fragment:
            raise PublicOriginError()
        if "*" in parts.netloc:
            raise PublicOriginError()
        hostname = parts.hostname
        port = parts.port
        if hostname is None:
            raise PublicOriginError()
        return _from_parts(parts.scheme, hostname, port)
    except PublicOriginError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise PublicOriginError() from exc


def parse_origin(value: str) -> CanonicalOrigin:
    """Parse a browser Origin header using the same canonical scheme/authority rules."""
    if not value:
        raise PublicOriginError("origin_missing")
    parsed = parse_public_origin(value)
    if urlsplit(value).path:
        raise PublicOriginError()
    return parsed


def parse_request_host(value: str, *, scheme: str) -> CanonicalOrigin:
    """Parse the app-visible Host authority, assigning the configured scheme's default port."""
    if not value or "/" in value or "?" in value or "#" in value or "@" in value:
        raise PublicOriginError()
    try:
        parts = urlsplit("//" + value)
        if not parts.netloc or parts.path or parts.query or parts.fragment or parts.username is not None:
            raise PublicOriginError()
        if parts.netloc.endswith(":"):
            raise PublicOriginError()
        hostname = parts.hostname
        port = parts.port
        if hostname is None:
            raise PublicOriginError()
        return _from_parts(scheme, hostname, port)
    except PublicOriginError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise PublicOriginError() from exc

from __future__ import annotations

import ipaddress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import SplitResult, urlsplit, urlunsplit


def _clean_strings(value: object, field_name: str, *, limit: int = 30) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings.")
    cleaned = tuple(
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    )
    if len(cleaned) != len(value):
        raise ValueError(f"{field_name} contains an empty or non-string value.")
    if len(cleaned) > limit:
        raise ValueError(f"{field_name} cannot contain more than {limit} items.")
    return cleaned


@dataclass(frozen=True)
class ResearchPlan:
    objective: str
    scope: str
    topics: tuple[str, ...]
    subtopics: dict[str, tuple[str, ...]] = field(default_factory=dict)
    search_queries: tuple[str, ...] = ()
    preferred_domains: tuple[str, ...] = ()
    excluded_domains: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    quality_criteria: tuple[str, ...] = ()
    target_record_count: int = 100
    dataset_type: str = "instruction"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchPlan:
        objective = data.get("objective")
        scope = data.get("scope")
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("Research plan objective is required.")
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("Research plan scope is required.")

        raw_subtopics = data.get("subtopics", {})
        if not isinstance(raw_subtopics, dict):
            raise ValueError("subtopics must be an object.")
        subtopics: dict[str, tuple[str, ...]] = {}
        for topic, values in raw_subtopics.items():
            if not isinstance(topic, str) or not topic.strip():
                raise ValueError("subtopics contains an invalid topic name.")
            subtopics[topic.strip()] = _clean_strings(
                values, f"subtopics.{topic}", limit=20
            )

        target_count = data.get("target_record_count", 100)
        if isinstance(target_count, bool) or not isinstance(target_count, int):
            raise ValueError("target_record_count must be an integer.")
        if not 1 <= target_count <= 1_000_000:
            raise ValueError("target_record_count must be between 1 and 1,000,000.")

        dataset_type = data.get("dataset_type", "instruction")
        if not isinstance(dataset_type, str) or not dataset_type.strip():
            raise ValueError("dataset_type must be a non-empty string.")

        return cls(
            objective=objective.strip()[:4000],
            scope=scope.strip()[:8000],
            topics=_clean_strings(data.get("topics", []), "topics"),
            subtopics=subtopics,
            search_queries=_clean_strings(data.get("search_queries", []), "search_queries"),
            preferred_domains=_clean_strings(
                data.get("preferred_domains", []), "preferred_domains"
            ),
            excluded_domains=_clean_strings(
                data.get("excluded_domains", []), "excluded_domains"
            ),
            source_types=_clean_strings(data.get("source_types", []), "source_types"),
            quality_criteria=_clean_strings(
                data.get("quality_criteria", []), "quality_criteria"
            ),
            target_record_count=target_count,
            dataset_type=dataset_type.strip()[:100],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""
    provider: str = ""


class SearchProvider(Protocol):
    """Adapter contract for external search services; implementations return candidates only."""

    name: str

    def search(self, query: str, max_results: int = 10) -> tuple[SearchResult, ...]:
        ...


@dataclass(frozen=True)
class SourceCandidate:
    url: str
    domain: str
    title: str = ""
    snippet: str = ""
    discovery_method: str = "manual"
    discovered_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    review_status: str = "pending"


def _is_unsafe_host(host: str) -> bool:
    lowered = host.rstrip(".").lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return True
    if lowered.endswith((".localhost", ".local", ".internal", ".test")):
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return not address.is_global


def normalize_public_url(value: str) -> str:
    """Normalize a candidate URL and reject obvious local/private destinations.

    Phase 4 must repeat DNS and redirect validation immediately before any network request.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("URL cannot be empty.")
    raw = value.strip()
    try:
        parsed: SplitResult = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL is malformed.") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS URLs are supported.")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs containing embedded credentials are not allowed.")

    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise ValueError("URL hostname is invalid.") from exc
    if not host or _is_unsafe_host(host):
        raise ValueError("Local, private, and reserved network destinations are not allowed.")

    if port is not None and not 1 <= port <= 65535:
        raise ValueError("URL port is invalid.")

    netloc = f"[{host}]" if ":" in host else host
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{netloc}:{port}"

    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def domain_from_url(url: str) -> str:
    normalized = normalize_public_url(url)
    host = urlsplit(normalized).hostname
    if host is None:
        raise ValueError("URL must include a hostname.")
    return host.lower()


def normalize_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if domain.startswith("*."):
        domain = domain[2:]
    if not domain or "/" in domain or ":" in domain or "@" in domain:
        raise ValueError(f"Invalid domain filter: {value!r}")
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"Invalid domain filter: {value!r}") from exc
    if _is_unsafe_host(domain):
        raise ValueError("Local and private domains cannot be used as source filters.")
    return domain


@dataclass(frozen=True)
class DomainFilter:
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        include: tuple[str, ...] | list[str] = (),
        exclude: tuple[str, ...] | list[str] = (),
    ) -> DomainFilter:
        return cls(
            include=tuple(normalize_domain(item) for item in include),
            exclude=tuple(normalize_domain(item) for item in exclude),
        )

    @staticmethod
    def _matches(domain: str, rule: str) -> bool:
        return domain == rule or domain.endswith(f".{rule}")

    def allows(self, url: str) -> bool:
        domain = domain_from_url(url)
        if any(self._matches(domain, rule) for rule in self.exclude):
            return False
        return not self.include or any(
            self._matches(domain, rule) for rule in self.include
        )


def import_url_candidates(
    text: str,
    filters: DomainFilter | None = None,
) -> tuple[tuple[SourceCandidate, ...], tuple[tuple[str, str], ...]]:
    """Parse newline-separated URLs into safe candidates and per-line rejections."""
    accepted: list[SourceCandidate] = []
    rejected: list[tuple[str, str]] = []
    active_filters = filters or DomainFilter()
    seen: set[str] = set()

    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            url = normalize_public_url(raw)
            domain = domain_from_url(url)
            if not active_filters.allows(url):
                raise ValueError("URL does not match the configured domain filters.")
            if url in seen:
                continue
            seen.add(url)
            accepted.append(SourceCandidate(url=url, domain=domain))
        except ValueError as exc:
            rejected.append((raw, str(exc)))

    return tuple(accepted), tuple(rejected)

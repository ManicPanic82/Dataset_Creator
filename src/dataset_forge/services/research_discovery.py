from __future__ import annotations

from dataset_forge.services.research import (
    DomainFilter,
    ResearchPlan,
    SearchProvider,
    SourceCandidate,
    domain_from_url,
    normalize_public_url,
)


class ResearchDiscoveryService:
    """Runs an injected search adapter and converts results into reviewable candidates."""

    def discover(
        self,
        plan: ResearchPlan,
        provider: SearchProvider,
        filters: DomainFilter | None = None,
        *,
        max_results_per_query: int = 10,
    ) -> tuple[tuple[SourceCandidate, ...], tuple[tuple[str, str], ...]]:
        if not 1 <= max_results_per_query <= 50:
            raise ValueError("max_results_per_query must be between 1 and 50.")

        active_filters = filters or DomainFilter()
        accepted: list[SourceCandidate] = []
        rejected: list[tuple[str, str]] = []
        seen: set[str] = set()

        for query in plan.search_queries:
            for result in provider.search(query, max_results=max_results_per_query):
                try:
                    url = normalize_public_url(result.url)
                    domain = domain_from_url(url)
                    if not active_filters.allows(url):
                        raise ValueError(
                            "Search result does not match the configured domain filters."
                        )
                    if url in seen:
                        continue
                    seen.add(url)
                    accepted.append(
                        SourceCandidate(
                            url=url,
                            domain=domain,
                            title=result.title[:500],
                            snippet=result.snippet[:2000],
                            discovery_method=provider.name,
                        )
                    )
                except ValueError as exc:
                    rejected.append((result.url, str(exc)))

        return tuple(accepted), tuple(rejected)

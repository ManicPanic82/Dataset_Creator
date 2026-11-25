# Phase 3: Research and Discovery

## Objective

Turn a user's research objective into an editable, reviewable research plan and a controlled set of candidate source URLs. Phase 3 stops before crawling or extracting webpage content; those belong to Phase 4.

## Scope

### 1. Research brief
- Capture a natural-language research objective within a project.
- Keep research inputs project-scoped.
- Validate empty prompts and unreasonable input sizes.
- Preserve the original prompt for traceability.

### 2. AI-generated research plan
- Use the configured Phase 2 AI provider and selected model.
- Ask the model for a structured plan containing objective, scope, topics, subtopics, search queries, preferred domains, excluded domains, source types, quality criteria, target record count, and proposed dataset type.
- Parse and validate model output before presenting it.
- Treat model output as untrusted data. Do not execute instructions, URLs, or tool calls returned by the model.
- Provide clear errors for unavailable providers, malformed JSON, missing fields, and unsupported output.
- Let the user edit the plan before approval.
- Persist approved plans and their source prompt against the current project.

### 3. Source discovery foundations
- Define a provider-neutral search interface so search vendors can be added without changing the research workflow.
- Support importing user-supplied HTTP/HTTPS URLs, including pasted multi-line lists.
- Validate and normalize URLs; reject unsupported schemes, credentials in URLs, localhost, private, loopback, link-local, and reserved IP destinations.
- Apply include/exclude domain rules to candidate sources.
- Preserve discovery method, timestamp, URL, domain, title when known, and review status.
- Keep URL import and search results as candidates until the user reviews them.
- Do not fetch pages in Phase 3. Crawling, redirects, DNS/IP revalidation at connection time, robots.txt, extraction, and SSRF-safe HTTP execution are Phase 4 responsibilities.

### 4. Research UI
- Replace the Research placeholder with a usable project-scoped workflow.
- Provide prompt entry, plan generation, editable plan content, approve/save, URL import, domain include/exclude controls, and a candidate-source list.
- Run AI planning and any search operations in background tasks.
- Show progress and useful failure messages without blocking the UI.

## Out of scope

- Fetching or crawling candidate URLs.
- Sitemap parsing and link following.
- Webpage extraction or content storage.
- Knowledge-pool construction.
- Training-example generation.
- Dataset validation and export.
- Browser automation or bypassing access controls.
- Hard-coding a search vendor or AI model.

## Safety and privacy

- Only HTTP and HTTPS URLs are accepted.
- Reject embedded URL usernames/passwords and local/private/reserved network destinations.
- URL validation at import time is an initial guard, not a substitute for Phase 4 connection-time DNS and redirect validation.
- Search results and AI output are untrusted data.
- API keys remain runtime-only and are never written to project records or SQLite settings.
- Do not crawl, fetch, or execute any imported URL in this phase.

## Acceptance criteria

1. A user can open a project and enter a non-empty research objective.
2. The configured AI provider can generate a structured research plan using the currently selected model.
3. Invalid or malformed model output is rejected with an actionable message.
4. The user can edit and approve a plan.
5. Approved plans persist and can be reopened with their project.
6. A user can import multiple URLs in one action.
7. Invalid and unsafe URLs are rejected with per-URL reasons.
8. Include/exclude domain filters work deterministically.
9. Candidate sources persist with provenance and can be reviewed.
10. Research operations execute off the UI thread.
11. Ruff and pytest pass on Windows, and the desktop application remains runnable.

## Implementation sequence

1. Add research-plan and source-candidate models plus validation tests.
2. Add structured AI generation to the existing provider adapter.
3. Add project-scoped research persistence without disturbing existing project/settings data.
4. Add URL normalization, safety checks, domain filtering, and search-provider protocol.
5. Build the Research UI and background task integration.
6. Run automated and Windows GUI validation before accepting Phase 3.

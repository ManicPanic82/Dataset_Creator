# Phase 5: Source-linked Knowledge Pool

## Goal

Build a reviewable, project-scoped intermediate knowledge layer between web extraction and dataset generation. Knowledge records must remain traceable to extracted public source snapshots and should not be generated directly into the final dataset without review.

## Initial storage foundation

This branch introduces a storage repository for knowledge items. Supported initial item types:

- Concept
- Definition
- Fact
- Procedure
- Example
- Code
- Comparison
- Troubleshooting

Each item contains its text, optional confidence score, review status, timestamps, and one or more source references. Source references can include evidence snippets. Items cannot be created unless every cited source belongs to the same project and has a saved extraction. The repository does not yet automatically extract knowledge with an AI model or provide a Knowledge Pool UI.

## Review states

- Pending: awaiting user review.
- Accepted: approved for downstream use.
- Rejected: excluded from downstream use.

## Design boundaries

- Project-scoped records.
- Mandatory provenance; no unsupported orphan items.
- Source association is many-to-many.
- Evidence snippets are optional and stored per source association.
- Confidence is optional and bounded from 0 to 1.
- Content size and type are validated.
- Knowledge is persisted locally in SQLite.
- Source content is treated as untrusted input. Retrieved text is evidence, not instructions for agents or tools.

## Next work

1. Add a Knowledge Pool page for browsing, filtering, and review.
2. Add AI extraction that emits structured knowledge candidates grounded in source text.
3. Validate model output and verify source references before storage.
4. Add deduplication and content-quality checks.
5. Build accepted knowledge into dataset generation with provenance.

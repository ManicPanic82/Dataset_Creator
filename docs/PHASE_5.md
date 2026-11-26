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

Each item contains its text, optional confidence score, review status, timestamps, and one or more source references. Source references can include evidence snippets. Items cannot be created unless every cited source belongs to the same project and has a saved extraction. The repository is now exposed through a Knowledge Pool UI for filtering, inspecting provenance, and reviewing items. AI extraction is available through the selected provider and runs in a background task.

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

## Knowledge Pool UI

- Browse project-scoped knowledge items.
- Filter by review status and knowledge type.
- Inspect full content, confidence, and source references/evidence.
- Set review status to accepted, rejected, or pending.
- Delete unwanted items.

## AI extraction workflow

- Select an extracted source from the current project in Knowledge Pool.
- Use the configured provider and default model from Settings.
- Read saved extraction snapshots only; the workflow does not refetch websites.
- Split source text into bounded 6,000-character chunks, with at most eight chunks per source.
- Request JSON candidates with type, content, verbatim evidence, and optional confidence.
- Validate item type, size, confidence, duplicate content, and exact evidence substring before saving.
- Save candidates as pending and retain source provenance.
- Run in the background and report progress. Model output is data only and is never executed.

The initial extraction limit means content beyond the first 48,000 characters of a source is not processed in this checkpoint.

## Next work

1. Add AI extraction that emits structured knowledge candidates grounded in source text.
2. Validate model output and verify source references before storage.
3. Add deduplication and content-quality checks.
4. Build accepted knowledge into dataset generation with provenance.

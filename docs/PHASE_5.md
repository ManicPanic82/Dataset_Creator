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
- Deduplicate within a project by knowledge type and normalized content (case-insensitive, whitespace-normalized). Repeated extraction reuses the existing item rather than creating another row.
- When the same knowledge is found in another source, attach its source and evidence to the existing item. Existing review status is preserved.
- Save candidates as pending and retain source provenance.
- Run in the background and report progress. Model output is data only and is never executed.

The initial extraction limit means content beyond the first 48,000 characters of a source is not processed in this checkpoint.

## Downstream dataset-generation context

The `KnowledgeContextService` provides the Phase 6 generation boundary:

- By default, it selects accepted items from the requested project only.
- Callers may pass an explicit list of knowledge IDs to limit generation scope.
- Explicit selections fail closed if an item is pending, rejected, missing, or belongs to another project.
- Duplicate IDs in a selection are rejected.
- Each prepared item includes its knowledge ID, type, content, confidence, and every linked source URL/title/domain plus its evidence snippet.
- Pending and rejected items are never silently included.
- The service prepares structured context for downstream generation while enforcing the accepted-only boundary.

This keeps generation grounded in reviewed knowledge while preserving enough provenance for generated records to be traced back to the original sources.

## Remaining Phase 5 work

1. Add deeper content-quality checks and review tooling for larger knowledge pools.

## Phase 6: first grounded-generation backend checkpoint

The first dataset-generation backend is now available on this feature branch.

- Supports instruction, question-and-answer, and conversational record shapes.
- Generates bounded batches of 1–20 records using the configured AI provider/model.
- Uses accepted project knowledge only, with an optional explicit knowledge selection.
- Rejects unsupported dataset types, invalid difficulty values, oversized batches, and empty knowledge selections.
- Validates every generated record against its exact data shape.
- Requires each record to reference one or more IDs from the accepted knowledge supplied to the model.
- Rejects unknown or cross-project knowledge references and does not save malformed records.
- Deduplicates identical records within each batch.
- Persists generated records as `pending_review`, never as automatically accepted training data.
- Snapshots each linked source URL, title, domain, and evidence snippet when the record is created, so later source edits or deletion do not erase its provenance.

The generator treats all source-derived knowledge as untrusted reference data. It does not browse, execute model output, or allow the model to create provenance IDs. Generated records remain pending review. The source metadata and evidence are snapshotted when the record is saved.

The Dataset Builder UI is now wired into the main workspace. It lets users choose a dataset format, difficulty, batch size, and up to 20 accepted knowledge items; generation runs in the background. Generated drafts can be inspected with their snapshotted source provenance and marked accepted, rejected, or returned to pending review. The UI defaults to selecting at most 20 knowledge items. The generation prompt explicitly requests one narrowly scoped concept per record and tells the model not to combine independent facts.

The first quality-screening pass is also available in the record review panel. It checks prompt/answer keyword overlap, answer length, supporting knowledge availability, and whether multiple linked knowledge items appear unrelated to the prompt. It reports a score, label, and explanatory flags. This is deliberately heuristic: it cannot prove semantic relevance or factual correctness, and it never changes review status or automatically accepts/rejects a record. Human review against the displayed source evidence remains required. Only the three listed dataset types are currently supported. Schema editing, target distributions, resumable generation, record editing, bulk review, and deeper semantic verification remain subsequent work.


## Accepted dataset export checkpoint

The Projects & Export workspace now exports reviewed training records as JSON Lines.

- Export is scoped to the currently open project.
- The user selects one of the three supported dataset formats per export, keeping each JSONL file schema-consistent.
- Only records with review status `accepted` and the selected format are considered.
- Pending and rejected records are excluded.
- Each JSONL row contains the dataset payload only, without application metadata.
- An optional `<filename>.provenance.jsonl` sidecar maps each exported record ID to its dataset type and snapshotted knowledge/source provenance.
- Invalid payloads are skipped and counted; the export summary reports exported, skipped, and available counts.
- Files are written as UTF-8, one JSON object per line. An empty selection produces a valid empty JSONL file.
- The export service validates the expected record shape and requires a `.jsonl` destination.

The sidecar is intended for traceability and audit, not as model-training input. The training JSONL remains clean. Export does not change record review states. CSV, schema customization, train/validation/test splitting, and richer export profiles remain future work.

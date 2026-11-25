# Dataset Forge AI
## Project Vision and Development Plan

**Working name:** Dataset Forge AI  
**Repository:** https://github.com/ManicPanic82/Dataset_Creator  
**Companion application:** Simple HF Trainer  
**Platform:** Windows-first desktop application  
**Status:** Initial project proposal  
**Purpose:** Research, extract, transform, validate and export high-quality datasets for AI model training.

---

## 1. Project vision

Dataset Forge AI is a standalone AI-powered dataset creation workstation. A user describes the information or skills they want a model to learn. The application plans the research, discovers relevant public web sources, extracts and organises useful information, generates training examples, validates their quality and exports training-ready datasets.

The application must remain independent from Simple HF Trainer. The two applications should work alongside one another through standard dataset files and an optional handoff mechanism, without making either application depend on the other.

The central workflow is:

1. **Discover:** Search for relevant websites, documentation, articles and other permitted sources.
2. **Understand:** Extract, clean, classify and analyse the collected information.
3. **Build:** Transform supported knowledge into configurable training examples.
4. **Validate:** Check structure, quality, duplication, coverage, traceability and suitability.
5. **Export:** Produce JSON, JSONL and other useful formats for downstream training.

The application should not be merely a web scraper with an AI feature bolted on. Its core value is a controlled, auditable research-to-dataset pipeline.

## 2. Example user workflow

A user might request:

> Create a dataset to train a small language model to become proficient at Python debugging. Research official Python documentation, troubleshooting guides, common programming errors and practical debugging techniques. Generate 5,000 question-and-answer and instruction examples, from beginner to advanced, suitable for supervised fine-tuning.

Dataset Forge AI should:

1. Convert the prompt into an editable research plan.
2. Propose topic categories, search queries, source criteria and a dataset schema.
3. Discover candidate sources and explain why they are relevant.
4. Crawl permitted pages within user-configurable limits.
5. Extract and clean useful content.
6. Build an intermediate, source-linked knowledge pool.
7. Generate diverse training examples grounded in that knowledge.
8. Validate and score the generated records.
9. Let the user review, edit, reject or regenerate records.
10. Split and export the final dataset with provenance and quality reports.

The user should approve the research plan before a substantial crawl begins.

## 3. Application interface

Proposed primary navigation:

1. **Research** - Research prompt, plan, search scope, source preferences and approval.
2. **Sources** - Discovered URLs, extraction status, previews, quality assessments and source management.
3. **Dataset Builder** - Dataset type, schema, target size, categories, difficulty and generation settings.
4. **Generation** - Pipeline progress, queues, logs, errors, pause/resume and retries.
5. **Quality Control** - Validation results, duplicate detection, coverage, sampling and human review.
6. **Projects & Export** - Project history, dataset versions, export formats, manifests and training handoff.
7. **Settings** - AI providers, model routing, search providers, crawl defaults, storage and application preferences.

The interface should be a compact, modern native Windows desktop application. It should prioritise clear status information, useful tables and previews, background processing and recoverable workflows.

## 4. Research and source discovery

Support three initial research modes:

### 4.1 URL mode
The user supplies one or more URLs. The application extracts the supplied pages and can optionally follow relevant links within defined limits.

### 4.2 Discovery mode
The user supplies a natural-language research objective. A search-provider integration discovers candidate sources and returns them for relevance assessment.

### 4.3 Domain exploration mode
The user supplies a domain or documentation site. The crawler explores accessible pages, sitemaps and relevant links within a bounded scope.

Potential discovery methods:

- Search-provider integrations.
- Manually supplied URLs and URL lists.
- Public XML sitemaps.
- Relevant links discovered on pages.
- Public documentation portals.
- User-imported local documents in a future phase.

Search providers must be pluggable. Do not tightly couple the application to one search vendor or assume that a general-purpose search API is free or available.

### 4.4 Research planning

Before crawling, the AI should propose an editable plan containing:

- Research objective and scope.
- Topic and subtopic breakdown.
- Search queries.
- Preferred and excluded domains.
- Source types and quality criteria.
- Desired knowledge coverage.
- Proposed dataset type and schema.
- Target record count.
- Estimated source and processing workload, where possible.

The user can edit and approve the plan before execution.

## 5. Crawler and extraction engine

Recommended Python components:

| Technology | Responsibility |
|---|---|
| HTTPX | HTTP requests and connection management |
| Trafilatura | Primary article and webpage text extraction |
| BeautifulSoup4 | HTML parsing and custom extraction |
| lxml | XML and sitemap parsing |
| Playwright | Optional JavaScript-rendered page extraction |
| readability-lxml | Alternative article extraction |
| Tenacity | Controlled retries |
| Pydantic | Typed data models and validation |

Prefer lightweight HTTP extraction. Use Playwright only when a page cannot be adequately extracted through normal HTTP methods.

Proposed initial crawl defaults, all configurable:

| Setting | Initial default |
|---|---:|
| Maximum candidate websites | 30 |
| Maximum pages per domain | 20 |
| Maximum crawl depth | 2 |
| Concurrent requests | 2 |
| Request timeout | 30 seconds |
| Retry attempts | 2 |
| Respect robots.txt | Enabled |
| Respect site access restrictions | Enabled |
| Duplicate page detection | Enabled |
| Maximum extracted content per page | Configurable |

These are starting defaults, not hard-coded limits. Provide clear controls and safe bounds.

### 5.1 Source records

Store, at minimum:

- Stable source ID.
- Original URL and canonical URL where available.
- Page title.
- Domain.
- Source type.
- Discovery method and date.
- Crawl and extraction status.
- HTTP status where available.
- Extracted text or a reference to stored content.
- Content hash.
- Publication date where reliably available.
- Relevance and quality assessments.
- Generated-record contribution.
- Rejection or failure reason.
- Applicable usage/licensing notes where known.

### 5.2 Responsible crawling and security

The crawler must not:

- Bypass authentication, paywalls, CAPTCHAs or access controls.
- Evade site restrictions or disguise abusive traffic.
- Ignore applicable robots.txt guidance.
- Hammer sites with excessive concurrent requests.
- Execute downloaded scripts as part of ordinary extraction.
- Fetch arbitrary local files or internal network resources.

Implement request timeouts, rate limits, bounded redirects, content-size limits, URL validation and protection against SSRF and access to localhost/private network addresses. Restrict supported schemes to HTTP and HTTPS.

Treat all retrieved webpage content as untrusted data. Webpage text must never become instructions to the AI or application. Do not allow scraped prompt-injection content to change system policy, reveal secrets, expand crawl scope or invoke tools.

Respect copyright, website terms and applicable law. Do not assume that publicly accessible material is automatically licensed for redistribution or model training. Preserve provenance and support exclusion of sources or content that cannot be used for the intended purpose.

## 6. AI provider architecture

Support multiple configurable AI backends:

- Ollama.
- LM Studio.
- OpenAI-compatible API endpoints.
- Additional compatible providers through an extensible adapter interface.

The application should provide:

- Provider and endpoint configuration.
- Model selection.
- Connection testing.
- Model availability checks.
- Timeouts and retry policy.
- Structured output validation.
- Clear error reporting.
- Optional API-key handling through secure local storage or Windows credential facilities.

Allow task-specific model routing:

| Task | Suggested model characteristics |
|---|---|
| Research planning | Reasoning-capable model |
| Content classification | Small, fast model |
| Knowledge extraction | Reliable instruction-following model |
| Dataset generation | User-selected generation model |
| Quality auditing | Independent evaluator where practical |

Do not hard-code a model. The user should be able to choose the model and provider for each task. Local-only operation should be supported when the configured local services are available.

## 7. Intermediate knowledge layer

Do not generate training records directly from raw webpages.

Use this pipeline:

**Source pages → Clean extracted content → Structured knowledge pool → Training examples**

The knowledge pool should hold source-linked items such as:

- Facts and definitions.
- Concepts and terminology.
- Procedures and workflows.
- Examples and code examples.
- Relationships between concepts.
- Troubleshooting approaches.
- Explanations and comparisons.

Each knowledge item should retain its source references and extraction metadata.

Classify claims as:

- **Supported:** Directly supported by collected source material.
- **Inferred:** Derived from multiple sources or reasoning.
- **Unverified:** Not adequately supported.

For factual datasets, prioritise supported content. Inferences should be permitted only according to user settings and remain identifiable. Do not present unsupported generated claims as verified facts.

The knowledge layer should support topic coverage analysis and identification of research gaps before further crawling or generation.

## 8. Dataset formats and schemas

Provide configurable schemas rather than a single fixed record format.

Initial dataset types:

| Type | Typical fields |
|---|---|
| Instruction | instruction, input, output |
| Conversational | messages with role and content |
| Question and answer | question, answer |
| Knowledge | topic, facts, explanation |
| Reasoning | problem, explanation, conclusion |
| Code | prompt, code, explanation |
| Classification | text, category |
| Summarisation | source text, summary |
| Custom | User-defined fields and types |

The schema editor should define field names, types, required/optional status and validation rules. Validate generated records against the selected schema.

Illustrative instruction record:

```json
{
  "instruction": "Explain how to diagnose a Python KeyError.",
  "input": "A dictionary lookup fails when accessing 'name'.",
  "output": "A KeyError occurs when a requested key is not present in a mapping.",
  "metadata": {
    "topics": ["python", "exceptions"],
    "difficulty": "beginner",
    "source_ids": ["src_00012"],
    "generation_method": "grounded_synthesis",
    "quality_status": "pending_review"
  }
}
```

Metadata should be configurable. The application should be able to keep provenance in a sidecar file or manifest rather than embedding metadata in a training format that does not support it.

## 9. Dataset generation

Support generation of original examples grounded in the collected knowledge, not just copying extracted text into training records.

Examples include:

- Concept questions and explanations.
- Practical scenarios.
- Troubleshooting exercises.
- Code debugging tasks.
- Step-by-step instructions.
- Comparisons.
- Multiple-choice questions.
- Conversational exchanges.
- Edge cases and advanced problems.

Provide controls for:

- Target record count.
- Dataset type and schema.
- Topic/category distribution.
- Difficulty distribution.
- Output length.
- Generation batch size.
- Transformation level.
- Permitted use of inference.
- Content restrictions.
- Model and generation parameters.

### 9.1 Difficulty levels

- Beginner: basic facts, definitions and simple instructions.
- Intermediate: multi-step explanations, comparisons and troubleshooting.
- Advanced: complex scenarios and challenging problems.
- Expert: specialised concepts, nuanced decisions and difficult edge cases.

Allow a selected level or configurable mixture.

### 9.2 Diversity and balancing

The application should plan and monitor category distributions to reduce repetitive datasets. An illustrative distribution might be:

| Category | Target |
|---|---:|
| Concept explanations | 20% |
| Practical problems | 20% |
| Troubleshooting | 15% |
| Examples | 15% |
| Comparisons | 10% |
| Step-by-step instructions | 10% |
| Advanced questions | 10% |

These targets must be editable. Report planned versus actual coverage and prioritise underrepresented categories when the user requests additional generation.

### 9.3 Resumable generation

Generation should run in bounded batches. Persist progress and outputs incrementally so that a crash or cancellation does not lose completed work.

Support pause, resume, cancel, retry failed batches, regenerate selected records, regenerate a category and expand an existing dataset.

## 10. Quality control and human review

Quality checks should run before export.

Initial checks:

| Check | Purpose |
|---|---|
| Schema validation | Missing fields, invalid JSON and wrong types |
| Exact duplicates | Identical records |
| Near duplicates | Highly similar records |
| Relevance | Drift from the research objective |
| Answer quality | Incomplete or incoherent examples |
| Source traceability | Missing or invalid source links |
| Factual consistency | Conflicts with collected evidence |
| Diversity | Overrepresented topics or styles |
| Leakage | Potential overlap between training and evaluation data |
| Length | Unusually short or long examples |
| Content filtering | Disallowed content and personal data |

Do not rely on one opaque AI-generated quality score. Show individual checks, reasons, evidence and thresholds. Distinguish deterministic validation from subjective AI assessments.

Human review should support:

- Random sampling.
- Review of flagged records.
- Review of all records.
- Individual accept/reject/edit.
- Bulk actions.
- Regeneration of selected records.
- Before-and-after comparison.

Automated validation should always run. Human review can be optional for high-volume workflows but should remain readily accessible.

## 11. Dataset splitting and export

Initial export formats:

- JSON.
- JSONL, one record per line.
- CSV.
- Hugging Face-compatible dataset layouts and manifests.

Provide configurable train, validation and test splits. A sensible initial default is 90% train, 5% validation and 5% test.

Avoid leakage by grouping related records by source, article or topic where possible before assigning splits. Do not rely solely on random record-level shuffling.

Example export layout:

```text
Python_Debugging_Dataset/
├── dataset.json
├── dataset.jsonl
├── train.jsonl
├── validation.jsonl
├── test.jsonl
├── sources.json
├── rejected_records.jsonl
├── quality_report.json
├── dataset_manifest.json
└── project_metadata.json
```

The exact files should depend on the selected export options. Preserve source data and project metadata separately from training records.

## 12. Project storage and versioning

Use SQLite for project metadata, source records, job state and other structured application data. Store large extracted content and dataset artifacts as files, with database references and content hashes.

Each project should preserve:

- Original research prompt.
- Approved research plan.
- Source inventory.
- Extracted content references.
- Knowledge pool.
- Dataset schema.
- AI provider and model identifiers.
- Generation settings.
- Dataset records and versions.
- Validation results.
- Rejected records.
- Export history.
- Timestamps and application version.

Version each generation. Allow users to compare dataset versions by size, category coverage, quality results and record changes.

Projects must survive application restarts. Background jobs should have recoverable states and clear handling for interrupted work.

## 13. Integration with Simple HF Trainer

The applications remain separate repositories and separate desktop applications.

**Dataset Forge AI responsibilities:**
- Research and discovery.
- Crawling and extraction.
- Knowledge organisation.
- Dataset generation.
- Dataset editing and quality control.
- Dataset export.

**Simple HF Trainer responsibilities:**
- Dataset import and training configuration.
- Model loading and training.
- Evaluation.
- Model export.

Initial integration should be file-based:

1. Dataset Forge AI exports a standard dataset folder.
2. The user selects the export location or uses an optional handoff action.
3. Simple HF Trainer imports the dataset using its normal dataset-loading workflow.
4. The trainer performs its own independent validation.

The training app must never require Dataset Forge AI to be installed. Do not modify the trainer repository as part of Dataset Forge AI development unless a separate, explicitly agreed integration task is created.

Future optional handoff mechanisms could include a shared export directory, launch arguments or a local integration protocol. Avoid inter-process complexity in the MVP.

## 14. Recommended technical architecture

| Component | Recommendation |
|---|---|
| Language | Python 3.12 |
| Desktop UI | PySide6 |
| Database | SQLite |
| AI | Ollama, LM Studio and compatible API providers |
| Search | Pluggable provider interface |
| Scraping | HTTPX, Trafilatura, BeautifulSoup |
| Browser extraction | Optional Playwright |
| Validation | Pydantic |
| Dataset formats | JSON, JSONL, CSV |
| Tests | pytest |
| Linting | Ruff |
| Platform | Windows-first |

Use a service-oriented architecture with clear boundaries between UI, providers, services, workers, models and storage. Keep network crawling and AI generation off the UI thread. Use bounded background workers, cancellation support and structured logging.

### Proposed initial project structure

```text
Dataset_Creator/
├── main.py
├── pyproject.toml
├── README.md
├── src/
│   ├── app/
│   │   ├── bootstrap.py
│   │   └── config.py
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── research_tab.py
│   │   ├── sources_tab.py
│   │   ├── dataset_builder_tab.py
│   │   ├── generation_tab.py
│   │   ├── quality_tab.py
│   │   ├── projects_tab.py
│   │   └── settings_tab.py
│   ├── services/
│   │   ├── research_service.py
│   │   ├── search_service.py
│   │   ├── crawl_service.py
│   │   ├── extraction_service.py
│   │   ├── knowledge_service.py
│   │   ├── generation_service.py
│   │   ├── validation_service.py
│   │   ├── export_service.py
│   │   └── integration_service.py
│   ├── providers/
│   │   ├── ai/
│   │   ├── search/
│   │   └── scraping/
│   ├── workers/
│   ├── models/
│   ├── storage/
│   └── utils/
├── tests/
├── projects/
├── exports/
└── docs/
```

This is a proposed structure, not a requirement to create every file at the start. Evolve it as implementation needs become clear.

## 15. Development roadmap

Build in small, testable phases. Each phase should leave the application runnable and include automated tests and a clear acceptance point.

### Phase 1 - Desktop foundation
- Native Windows desktop application.
- Main window and navigation.
- Project management.
- SQLite storage.
- Settings and configuration.
- Logging.
- Background task framework.
- Persistence and recovery basics.

### Phase 2 - AI provider system
- Ollama integration.
- LM Studio integration.
- Compatible API provider interface.
- Provider and model selection.
- Connection tests.
- Structured response validation.
- Task-specific model routing.

### Phase 3 - Research and discovery
- Natural-language research prompts.
- AI-generated research plans.
- Search-provider abstraction.
- URL import.
- Source discovery.
- Domain filters and exclusions.
- Plan editing and approval.

### Phase 4 - Crawler and extraction
- Bounded website crawling.
- Sitemap support.
- Link discovery.
- Text extraction and cleaning.
- Crawl restrictions and safety controls.
- Source management and previews.
- Retry and failure handling.

### Phase 5 - Knowledge engine
- Knowledge extraction.
- Topic categorisation.
- Source linking.
- Knowledge pool persistence.
- Coverage analysis.
- Knowledge gap detection.
- Research expansion.

### Phase 6 - Dataset generation
- Configurable schemas.
- Instruction, conversational and Q&A formats.
- Code and other dataset types.
- Difficulty and diversity controls.
- Batch generation.
- Progress persistence and retries.

### Phase 7 - Quality and review
- Schema validation.
- Duplicate and similarity detection.
- Quality assessment.
- Source traceability.
- Review interface.
- Rejection and regeneration.
- Coverage metrics.

### Phase 8 - Export and integration
- JSON, JSONL and CSV.
- Train/validation/test splitting.
- Leakage-aware grouping.
- Source metadata and manifests.
- Quality reports.
- Training-app handoff through standard files.

### Phase 9 - Advanced capabilities
- Semantic similarity.
- Advanced dataset balancing.
- Knowledge-gap targeting.
- Version comparisons.
- Reusable dataset recipes.
- Knowledge maps.
- Optional embeddings and advanced research workflows.

## 16. Features deliberately excluded from the MVP

Keep the first release focused. Do not initially build:

- Unrestricted autonomous web agents.
- Multi-agent orchestration.
- Website account login automation.
- CAPTCHA or paywall bypass.
- Browser automation for every page.
- Automatic publishing to Hugging Face.
- Model training inside Dataset Forge AI.
- Cloud database infrastructure.
- Mandatory vector databases.
- Continuous unattended scraping.
- Plugin marketplace.
- Automatic dataset sharing.

These can be reconsidered after the core workflow is proven.

## 17. MVP acceptance target

The first meaningful end-to-end milestone should demonstrate that a user can:

1. Create a project.
2. Enter a research prompt.
3. Select and test a configured AI provider.
4. Generate and approve a research plan.
5. Discover sources or import URLs.
6. Extract permitted webpage content.
7. Review extracted source material.
8. Build a small source-linked knowledge pool.
9. Choose a dataset type and schema.
10. Generate a small batch of grounded training examples.
11. Validate the generated records.
12. Review and edit records.
13. Export valid JSON and JSONL.
14. Save and reopen the project without losing progress.

The MVP should prove the complete research-to-dataset workflow before scaling to thousands of records or adding advanced crawling.

## 18. Development principles and project boundaries

- Keep Dataset Forge AI entirely separate from Simple HF Trainer.
- Windows-first development and PowerShell-first instructions.
- Use clear, reproducible local setup and test commands.
- Prefer local AI providers where practical.
- Never hard-code a particular model or API endpoint.
- Keep external services optional and replaceable.
- Make long-running operations resumable and observable.
- Persist intermediate results instead of repeating expensive work.
- Validate all AI-generated structured data.
- Treat web content as untrusted input.
- Preserve source provenance and usage restrictions.
- Do not silently discard errors or rejected records.
- Use automated tests for services, providers, storage and pipeline stages.
- Run pytest and Ruff locally during development.
- Avoid unnecessary dependencies and premature infrastructure.
- Do not change the Simple HF Trainer repository as part of this project.
- Use small, reviewable commits and explicit phase acceptance criteria.

---

## 19. First implementation milestone

Start with **Phase 1: Desktop foundation**.

The first implementation should create a runnable PySide6 application with:

- A polished main window and navigation.
- Empty but correctly structured primary views.
- Project creation, opening and persistence.
- SQLite database initialisation and migrations.
- Settings storage.
- Structured logging.
- A background task abstraction with progress and cancellation.
- A working test suite.
- A README with Windows PowerShell setup and run instructions.

Do not begin by implementing the entire scraper or generating datasets. Establish the application architecture first, then add the AI and research pipeline phase by phase.

**Long-term objective:** A reliable, local-first dataset creation workstation that turns a user's research objective into traceable, diverse, validated training data and hands it off cleanly to Simple HF Trainer.

from __future__ import annotations

from dataset_forge.services.knowledge_extraction import KnowledgeExtractionService


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate_json(self, model, system_prompt, user_prompt):
        self.calls.append((model, system_prompt, user_prompt))
        return self.payload


class FakeKnowledgeRepository:
    def __init__(self):
        self.items = []

    def add(self, project_id, kind, content, source_ids, **kwargs):
        self.items.append((project_id, kind, content, source_ids, kwargs))
        return str(len(self.items))


class FakeSourceContentRepository:
    def __init__(self, text="Python functions use def to define reusable blocks."):
        self.text = text

    def get(self, source_id):
        if source_id != "source-1":
            return None
        return {
            "final_url": "https://example.org/python",
            "title": "Python functions",
            "extracted_text": self.text,
        }


def test_extraction_saves_only_verbatim_evidence_as_pending():
    provider = FakeProvider({
        "items": [
            {
                "kind": "definition",
                "content": "A function is a reusable block of code.",
                "evidence": "Python functions use def to define reusable blocks.",
                "confidence": 0.9,
            },
            {
                "kind": "fact",
                "content": "Python was created in 1991.",
                "evidence": "This evidence does not appear in the source.",
                "confidence": 0.8,
            },
        ]
    })
    repository = FakeKnowledgeRepository()
    service = KnowledgeExtractionService(
        provider, "test-model", repository, FakeSourceContentRepository()
    )

    count = service.extract_source("project-1", "source-1")

    assert count == 1
    assert repository.items[0][0:4] == (
        "project-1",
        "definition",
        "A function is a reusable block of code.",
        ["source-1"],
    )
    assert repository.items[0][4]["evidence"] == {
        "source-1": "Python functions use def to define reusable blocks."
    }


def test_extraction_rejects_missing_source_snapshot():
    service = KnowledgeExtractionService(
        FakeProvider({"items": []}),
        "test-model",
        FakeKnowledgeRepository(),
        FakeSourceContentRepository(),
    )
    try:
        service.extract_source("project-1", "missing")
    except ValueError as exc:
        assert "no saved extraction" in str(exc)
    else:
        raise AssertionError("Expected missing source extraction to be rejected.")


def test_extraction_chunks_large_source_with_bounded_requests():
    text = "A" * 13_000
    provider = FakeProvider({"items": []})
    service = KnowledgeExtractionService(
        provider,
        "test-model",
        FakeKnowledgeRepository(),
        FakeSourceContentRepository(text),
    )

    assert service.extract_source("project-1", "source-1") == 0
    assert len(provider.calls) == 3
    assert all(len(call[2]) < 7_000 for call in provider.calls)


def test_extraction_stops_when_cancelled():
    provider = FakeProvider({"items": []})
    service = KnowledgeExtractionService(
        provider,
        "test-model",
        FakeKnowledgeRepository(),
        FakeSourceContentRepository("A" * 13_000),
    )
    count = service.extract_source(
        "project-1", "source-1", cancelled=lambda: True
    )
    assert count == 0
    assert provider.calls == []


def test_extraction_ignores_malformed_and_duplicate_candidates():
    provider = FakeProvider({
        "items": [
            {
                "kind": "fact",
                "content": "A useful fact.",
                "evidence": "Python functions use def",
                "confidence": 0.7,
            },
            {
                "kind": "fact",
                "content": " A useful   fact. ",
                "evidence": "Python functions use def",
                "confidence": 0.6,
            },
            {
                "kind": "unknown",
                "content": "Unsupported kind.",
                "evidence": "Python functions use def",
                "confidence": 0.6,
            },
            "not an object",
        ]
    })
    repository = FakeKnowledgeRepository()
    service = KnowledgeExtractionService(
        provider, "test-model", repository, FakeSourceContentRepository()
    )

    assert service.extract_source("project-1", "source-1") == 1
    assert len(repository.items) == 1



def test_extraction_accepts_whitespace_normalized_evidence_and_stores_source_text():
    source_text = "The first step is to determine whether\nthe problem has already been reported."
    provider = FakeProvider({
        "items": [
            {
                "kind": "procedure",
                "content": "Check whether the problem has already been reported.",
                "evidence": "determine whether the problem has already been reported.",
                "confidence": 0.9,
            }
        ]
    })
    repository = FakeKnowledgeRepository()
    service = KnowledgeExtractionService(
        provider, "test-model", repository, FakeSourceContentRepository(source_text)
    )

    assert service.extract_source("project-1", "source-1") == 1
    assert repository.items[0][4]["evidence"]["source-1"] == (
        "determine whether\nthe problem has already been reported."
    )


def test_extraction_still_rejects_changed_evidence_wording():
    provider = FakeProvider({
        "items": [
            {
                "kind": "fact",
                "content": "The tracker should be checked first.",
                "evidence": "Check the issue tracker before filing a report.",
                "confidence": 0.9,
            }
        ]
    })
    repository = FakeKnowledgeRepository()
    service = KnowledgeExtractionService(
        provider, "test-model", repository, FakeSourceContentRepository()
    )

    assert service.extract_source("project-1", "source-1") == 0
    assert repository.items == []

def test_extraction_rejects_evidence_over_word_limit_even_when_verbatim():
    source_text = "This source contains a deliberately long sentence with enough words "
    source_text += "to exceed the short evidence quotation limit set by the extractor."
    provider = FakeProvider({
        "items": [
            {
                "kind": "fact",
                "content": "The source contains a long sentence.",
                "evidence": source_text,
                "confidence": 0.9,
            }
        ]
    })
    repository = FakeKnowledgeRepository()
    service = KnowledgeExtractionService(
        provider, "test-model", repository, FakeSourceContentRepository(source_text)
    )

    assert service.extract_source("project-1", "source-1") == 0
    assert repository.items == []

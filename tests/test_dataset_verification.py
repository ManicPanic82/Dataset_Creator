import pytest

from dataset_forge.services.dataset_verification import DatasetVerificationService


class StubProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_json(self, *, model, system_prompt, user_prompt):
        self.calls.append((model, system_prompt, user_prompt))
        return self.response


KNOWLEDGE = [
    {
        "knowledge_id": "knowledge-1",
        "kind": "fact",
        "content": (
            "Exceptions nested within an ExceptionGroup must be instances "
            "rather than exception types."
        ),
        "sources": [
            {
                "url": "https://docs.python.org/example",
                "title": "Python documentation",
                "evidence": "must be instances rather than exception types",
            }
        ],
    }
]


def _report(**overrides):
    result = {
        "verdict": "review",
        "score": 72,
        "summary": "The answer is relevant, but one claim needs closer inspection.",
        "findings": [
            {
                "severity": "medium",
                "category": "unsupported_claim",
                "claim": "They must be exception instances, not exception types.",
                "explanation": (
                    "The source supports this claim, but the answer adds an implication."
                ),
                "knowledge_id": "knowledge-1",
                "evidence": "must be instances rather than exception types",
            }
        ],
    }
    result.update(overrides)
    return result


def test_verification_returns_validated_advisory_report():
    provider = StubProvider(_report())
    service = DatasetVerificationService(provider, "local-model")

    result = service.verify(
        "question_answer",
        {
            "question": "What must nested exceptions be?",
            "answer": "They must be exception instances, not exception types.",
        },
        KNOWLEDGE,
    )

    assert result["verdict"] == "review"
    assert result["score"] == 72
    assert result["method"] == "model_assisted"
    assert result["findings"][0]["knowledge_id"] == "knowledge-1"
    assert result["findings"][0]["evidence"] in KNOWLEDGE[0]["content"]
    assert "does not change" in result["disclaimer"]
    assert provider.calls[0][0] == "local-model"
    assert "untrusted data" in provider.calls[0][1]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"verdict": "approved"}, "invalid verdict"),
        ({"score": True}, "score must be an integer"),
        ({"score": 101}, "score must be an integer"),
        ({"summary": ""}, "summary is missing"),
        ({"findings": "none"}, "findings must be a list"),
    ],
)
def test_verification_rejects_invalid_top_level_response(overrides, message):
    service = DatasetVerificationService(StubProvider(_report(**overrides)), "model")

    with pytest.raises(ValueError, match=message):
        service.verify(
            "instruction",
            {
                "instruction": "Q",
                "output": "They must be exception instances, not exception types.",
            },
            KNOWLEDGE,
        )


def test_verification_rejects_unknown_knowledge_reference():
    finding = _report()["findings"][0] | {"knowledge_id": "invented"}
    service = DatasetVerificationService(
        StubProvider(_report(findings=[finding])), "model"
    )

    with pytest.raises(ValueError, match="unknown knowledge"):
        service.verify(
            "instruction",
            {
                "instruction": "Q",
                "output": "They must be exception instances, not exception types.",
            },
            KNOWLEDGE,
        )


def test_verification_rejects_non_verbatim_evidence():
    finding = _report()["findings"][0] | {"evidence": "A paraphrased quote"}
    service = DatasetVerificationService(
        StubProvider(_report(findings=[finding])), "model"
    )

    with pytest.raises(ValueError, match="exact quote"):
        service.verify(
            "instruction",
            {
                "instruction": "Q",
                "output": "They must be exception instances, not exception types.",
            },
            KNOWLEDGE,
        )


def test_verification_rejects_oversized_record_before_provider_call():
    provider = StubProvider(_report())
    service = DatasetVerificationService(provider, "model")

    with pytest.raises(ValueError, match="too large"):
        service.verify(
            "instruction",
            {"instruction": "Q", "output": "x" * 12_001},
            KNOWLEDGE,
        )

    assert provider.calls == []


def test_verification_rejects_empty_or_duplicate_provenance():
    provider = StubProvider(_report())
    service = DatasetVerificationService(provider, "model")

    with pytest.raises(ValueError, match="between 1 and 20"):
        service.verify("instruction", {"instruction": "Q", "output": "A"}, [])

    duplicate = KNOWLEDGE + [KNOWLEDGE[0]]
    with pytest.raises(ValueError, match="duplicate"):
        service.verify("instruction", {"instruction": "Q", "output": "A"}, duplicate)


def test_verification_allows_finding_without_exact_support_quote():
    finding = _report()["findings"][0] | {
        "category": "unsupported_claim",
        "evidence": "",
        "explanation": "No supporting quote was found in the supplied knowledge.",
    }
    service = DatasetVerificationService(
        StubProvider(_report(findings=[finding])), "model"
    )

    result = service.verify(
        "instruction",
        {
            "instruction": "Q",
            "output": "They must be exception instances, not exception types.",
        },
        KNOWLEDGE,
    )

    assert result["findings"][0]["evidence"] == ""



def test_verification_rejects_invalid_dataset_type_before_provider_call():
    provider = StubProvider(_report())
    service = DatasetVerificationService(provider, "model")

    with pytest.raises(ValueError, match="Unsupported dataset type"):
        service.verify("unknown", {"question": "Q", "answer": "A"}, KNOWLEDGE)

    assert provider.calls == []


def test_verification_rejects_malformed_unhashable_verdict():
    provider = StubProvider(_report(verdict=["pass"]))
    service = DatasetVerificationService(provider, "model")

    with pytest.raises(ValueError, match="invalid verdict"):
        service.verify("question_answer", {"question": "Q", "answer": "A"}, KNOWLEDGE)



def test_verification_omits_claim_that_is_not_an_exact_answer_excerpt():
    finding = _report()["findings"][0] | {
        "claim": "The source says something else entirely."
    }
    service = DatasetVerificationService(
        StubProvider(_report(findings=[finding])), "model"
    )

    result = service.verify(
        "question_answer",
        {
            "question": "What must nested exceptions be?",
            "answer": "They must be exception instances, not exception types.",
        },
        KNOWLEDGE,
    )

    clean_finding = result["findings"][0]
    assert clean_finding["claim"] == ""
    assert "exact excerpt" in clean_finding["explanation"]
    assert clean_finding["evidence"] == _report()["findings"][0]["evidence"]


def test_batch_verification_continues_after_an_individual_provider_failure():
    class IntermittentProvider:
        def __init__(self):
            self.calls = 0

        def generate_json(self, *, model, system_prompt, user_prompt):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary provider failure")
            return _report(verdict="pass", score=98, findings=[])

    provider = IntermittentProvider()
    service = DatasetVerificationService(provider, "model")
    record = {
        "dataset_type": "question_answer",
        "payload": {
            "question": "What must nested exceptions be?",
            "answer": "They must be exception instances, not exception types.",
        },
        "provenance": KNOWLEDGE,
    }
    progress = []

    result = service.verify_batch(
        [{"id": "record-1", **record}, {"id": "record-2", **record}],
        lambda index, total, record_id: progress.append((index, total, record_id)),
    )

    assert result["total"] == 2
    assert "record-1" in result["errors"]
    assert "temporary provider failure" in result["errors"]["record-1"]
    assert result["reports"]["record-2"]["verdict"] == "pass"
    assert progress == [(1, 2, "record-1"), (2, 2, "record-2")]

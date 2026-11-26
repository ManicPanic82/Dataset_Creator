from dataset_forge.services.dataset_quality import DatasetQualityService


def test_quality_flags_instruction_combining_unrelated_supported_facts():
    report = DatasetQualityService.assess(
        "instruction",
        {
            "instruction": "What are the rules for exceptions nested within an ExceptionGroup?",
            "input": "",
            "output": (
                "Exceptions nested in an exception group must be instances, not types. "
                "The standard traceback rendering displays all notes added to an "
                "exception in the order they were added."
            ),
        },
        [
            {
                "content": (
                    "Exceptions nested within an ExceptionGroup must be instances "
                    "rather than exception types."
                )
            },
            {
                "content": (
                    "Standard traceback rendering displays all notes added to an "
                    "exception in the order they were added."
                )
            },
        ],
    )

    assert report["score"] < 100
    assert report["label"] == "Review carefully"
    assert any(flag["code"] == "possibly_mixed_topics" for flag in report["flags"])
    assert report["method"] == "heuristic"


def test_quality_accepts_focused_grounded_instruction_without_flags():
    report = DatasetQualityService.assess(
        "instruction",
        {
            "instruction": "What must exceptions nested in an ExceptionGroup be?",
            "input": "",
            "output": "They must be exception instances, not exception types.",
        },
        [
            {
                "content": (
                    "Exceptions nested within an ExceptionGroup must be instances "
                    "rather than exception types."
                )
            }
        ],
    )

    assert report["score"] == 100
    assert report["label"] == "Looks consistent"
    assert report["flags"] == []

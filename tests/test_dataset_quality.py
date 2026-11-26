from dataset_forge.services.dataset_quality import DatasetQualityService


def test_quality_flags_instruction_combining_unrelated_supported_facts():
    unrelated_sentence = (
        "The standard traceback rendering displays all notes added to an "
        "exception in the order they were added."
    )
    report = DatasetQualityService.assess(
        "instruction",
        {
            "instruction": "What are the rules for exceptions nested within an ExceptionGroup?",
            "input": "",
            "output": (
                "Exceptions nested in an exception group must be instances, not types. "
                + unrelated_sentence
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
    sentence_flag = next(
        flag for flag in report["flags"]
        if flag["code"] == "off_topic_answer_sentence"
    )
    assert sentence_flag["sentences"] == [unrelated_sentence]
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


def test_quality_flags_sentence_not_supported_by_relevant_knowledge():
    unsupported_sentence = "The traceback also includes notes in insertion order."
    report = DatasetQualityService.assess(
        "question_answer",
        {
            "question": "What must exceptions nested in an ExceptionGroup be?",
            "answer": (
                "They must be exception instances, not exception types. "
                + unsupported_sentence
            ),
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

    sentence_flag = next(
        flag for flag in report["flags"]
        if flag["code"] == "off_topic_answer_sentence"
    )
    assert sentence_flag["sentences"] == [unsupported_sentence]


def test_quality_sentence_screening_handles_conversational_records():
    report = DatasetQualityService.assess(
        "conversational",
        {
            "messages": [
                {"role": "user", "content": "What are syntax errors?"},
                {
                    "role": "assistant",
                    "content": (
                        "Syntax errors occur when code is syntactically incorrect."
                    ),
                },
            ]
        },
        [
            {
                "content": (
                    "Syntax errors, also known as parsing errors, occur when code "
                    "is syntactically incorrect."
                )
            }
        ],
    )

    assert not any(
        flag["code"] == "off_topic_answer_sentence" for flag in report["flags"]
    )

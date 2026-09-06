from __future__ import annotations

import json

from app.generation.answer import answer_question, build_answer_prompt, compact_generation_context


class FakeGeminiClient:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def retrieval_payload(results=None):
    return {
        "query": "Why is English useful?",
        "results": results
        if results is not None
        else [
            {
                "rank": 1,
                "score": 0.9,
                "event": {
                    "id": "event-1",
                    "title": "English as a Global Language",
                    "summary": "English helps people discuss global problems.",
                },
                "evidence_bundle": {
                    "event": {
                        "id": "event-1",
                        "title": "English as a Global Language",
                        "summary": "English helps people discuss global problems.",
                        "source_id": "source-1",
                        "start_time": 209.18,
                        "end_time": 239.18,
                        "entities": ["English"],
                        "confidence": 0.8,
                    },
                    "transcripts": [
                        {
                            "id": "transcript-1",
                            "start_time": 209.18,
                            "end_time": 220.0,
                            "content": "English is useful for solving global problems.",
                            "confidence": None,
                        }
                    ],
                    "frames": [
                        {
                            "id": "frame-uuid-123",
                            "timestamp": 215.0,
                            "path": "/absolute/local/path/frame_215.jpg",
                            "confidence": 1.0,
                        }
                    ],
                    "ocr": [
                        {
                            "id": "ocr-1",
                            "timestamp": 215.0,
                            "text": "United Nations Climate Change Conference",
                            "confidence": 0.8,
                            "metadata": {},
                        }
                    ],
                    "entities": [
                        {
                            "id": "entity-uuid-english",
                            "name": "English",
                            "normalized_name": "english",
                            "type": "language",
                            "confidence": 0.9,
                            "metadata": {},
                        }
                    ],
                    "relationships": [
                        {
                            "source": "raw-uuid-a",
                            "relation": "TEMPORALLY_ALIGNED_WITH",
                            "target": "raw-uuid-b",
                            "confidence": 1.0,
                            "method": "temporal",
                        },
                        {
                            "source": "entity-uuid-english",
                            "relation": "DISCUSSES",
                            "target": "entity-uuid-problems",
                            "confidence": 0.85,
                            "method": "llm",
                        },
                    ],
                },
            },
            {
                "rank": 2,
                "score": 0.5,
                "event": {
                    "id": "event-2",
                    "title": "Other Event",
                    "summary": "Less relevant.",
                },
                "evidence_bundle": {
                    "event": {
                        "id": "event-2",
                        "title": "Other Event",
                        "summary": "Less relevant.",
                        "source_id": "source-1",
                        "start_time": 300.0,
                        "end_time": 310.0,
                        "entities": [],
                        "confidence": 0.5,
                    },
                    "transcripts": [],
                    "frames": [],
                    "ocr": [],
                    "entities": [],
                    "relationships": [],
                },
            },
        ],
    }


def answer_payload() -> str:
    return json.dumps(
        {
            "answer": "The evidence says English is useful for solving global problems.",
            "confidence": 0.01,
            "citations": [
                {
                    "event_id": "event-1",
                    "timestamp_start": 209.18,
                    "timestamp_end": 239.18,
                    "evidence_types": ["transcript", "ocr", "frame"],
                    "support": "The transcript directly says English is useful for solving global problems.",
                }
            ],
            "key_entities": ["English"],
            "used_modalities": ["transcript", "ocr", "frame"],
        }
    )


def test_answer_generation_receives_retrieved_evidence(monkeypatch) -> None:
    fake_client = FakeGeminiClient(answer_payload())
    monkeypatch.setattr("app.generation.answer.retrieve", lambda *args, **kwargs: retrieval_payload())

    result = answer_question("source-1", "Why is English useful?", client=fake_client)

    assert result["answer"].startswith("The evidence says")
    assert "English is useful for solving global problems" in fake_client.prompts[0]
    assert "United Nations Climate Change Conference" in fake_client.prompts[0]


def test_answer_contains_citations(monkeypatch) -> None:
    monkeypatch.setattr("app.generation.answer.retrieve", lambda *args, **kwargs: retrieval_payload())

    result = answer_question("source-1", "Why is English useful?", client=FakeGeminiClient(answer_payload()))

    assert result["citations"][0]["event_id"] == "event-1"
    assert result["citations"][0]["evidence_types"] == ["transcript", "ocr", "frame"]


def test_confidence_is_calculated_locally(monkeypatch) -> None:
    monkeypatch.setattr("app.generation.answer.retrieve", lambda *args, **kwargs: retrieval_payload())

    result = answer_question("source-1", "Why is English useful?", client=FakeGeminiClient(answer_payload()))

    assert result["confidence"] != 0.01
    assert 0.0 < result["confidence"] <= 1.0


def test_no_evidence_returns_insufficient_evidence(monkeypatch) -> None:
    monkeypatch.setattr("app.generation.answer.retrieve", lambda *args, **kwargs: retrieval_payload([]))

    result = answer_question("source-1", "Unknown question", client=FakeGeminiClient(answer_payload()))

    assert result["answer"] == "The retrieved evidence is insufficient to answer this question."
    assert result["confidence"] == 0.0
    assert result["citations"] == []


def test_raw_graph_uuids_are_not_in_generation_prompt() -> None:
    context = compact_generation_context(retrieval_payload())
    prompt = build_answer_prompt("Why is English useful?", context)

    assert "raw-uuid-a" not in prompt
    assert "raw-uuid-b" not in prompt
    assert "TEMPORALLY_ALIGNED_WITH" not in prompt
    assert "/absolute/local/path" not in prompt
    assert "frame-uuid-123" in prompt


def test_gemini_failure_is_handled_safely(monkeypatch) -> None:
    monkeypatch.setattr("app.generation.answer.retrieve", lambda *args, **kwargs: retrieval_payload())

    result = answer_question("source-1", "Why is English useful?", client=FakeGeminiClient(RuntimeError("boom")))

    assert result["answer"] == "The retrieved evidence is insufficient to answer this question."
    assert result["confidence"] == 0.0
    assert "Answer generation failed" in result["error"]

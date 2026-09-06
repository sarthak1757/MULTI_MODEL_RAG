from __future__ import annotations

from pathlib import Path

from app.models import Modality, Observation
from app.processing.aligner import build_temporal_alignment_edges
from app.processing.event_builder import build_event_candidates, format_event_debug, process_source
from app.storage.database import (
    get_event_observations,
    initialize_database,
    insert_observation,
    list_edges,
    list_events_for_source,
)


def make_observation(
    modality: Modality,
    source_id: str = "source-1",
    content: str = "content",
    start_time: float | None = None,
    end_time: float | None = None,
    timestamp: float | None = None,
    metadata: dict | None = None,
) -> Observation:
    return Observation(
        modality=modality,
        content=content,
        source_id=source_id,
        source_path="data/uploads/test.mp4",
        start_time=start_time,
        end_time=end_time,
        timestamp=timestamp,
        metadata=metadata or {},
    )


def test_frame_inside_transcript_interval_has_confidence_one() -> None:
    transcript = make_observation(Modality.TRANSCRIPT, start_time=10.0, end_time=20.0)
    frame = make_observation(Modality.FRAME, timestamp=15.0)

    edges = build_temporal_alignment_edges([transcript], [frame], tolerance_seconds=5.0)

    assert len(edges) == 1
    assert edges[0].confidence == 1.0
    assert edges[0].metadata["temporal_distance_seconds"] == 0.0


def test_frame_near_transcript_interval_has_partial_confidence() -> None:
    transcript = make_observation(Modality.TRANSCRIPT, start_time=10.0, end_time=12.0)
    frame = make_observation(Modality.FRAME, timestamp=14.0)

    edges = build_temporal_alignment_edges([transcript], [frame], tolerance_seconds=5.0)

    assert len(edges) == 1
    assert 0 < edges[0].confidence < 1


def test_frame_outside_tolerance_creates_no_edge() -> None:
    transcript = make_observation(Modality.TRANSCRIPT, start_time=10.0, end_time=12.0)
    frame = make_observation(Modality.FRAME, timestamp=30.0)

    edges = build_temporal_alignment_edges([transcript], [frame], tolerance_seconds=5.0)

    assert edges == []


def test_candidate_event_construction_respects_gap_and_duration() -> None:
    transcripts = [
        make_observation(Modality.TRANSCRIPT, start_time=0.0, end_time=3.0),
        make_observation(Modality.TRANSCRIPT, start_time=6.0, end_time=8.0),
        make_observation(Modality.TRANSCRIPT, start_time=20.0, end_time=22.0),
    ]

    candidates = build_event_candidates(
        transcripts,
        max_gap_seconds=4.0,
        max_event_duration_seconds=30.0,
    )

    assert len(candidates) == 2
    assert candidates[0].transcripts == transcripts[:2]
    assert candidates[1].transcripts == transcripts[2:]


def test_processing_creates_event_membership_and_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    source_id = "source-1"
    initialize_database(db_path)

    transcript = insert_observation(
        make_observation(
            Modality.TRANSCRIPT,
            source_id=source_id,
            content="Redis reduces load on PostgreSQL.",
            start_time=10.0,
            end_time=15.0,
        ),
        db_path,
    )
    frame = insert_observation(
        make_observation(
            Modality.FRAME,
            source_id=source_id,
            content="data/frames/source-1/frame_10.jpg",
            timestamp=10.0,
        ),
        db_path,
    )
    ocr = insert_observation(
        make_observation(
            Modality.OCR,
            source_id=source_id,
            content="Redis",
            timestamp=10.0,
            metadata={"parent_frame_id": frame.id},
        ),
        db_path,
    )

    first_summary = process_source(source_id, db_path=db_path)
    first_edges = list_edges(db_path)
    second_summary = process_source(source_id, db_path=db_path)
    second_edges = list_edges(db_path)

    events = list_events_for_source(source_id, db_path)
    event_observations = get_event_observations(events[0].id, db_path)
    relations = {edge.relation for edge in second_edges}

    assert first_summary["events_created"] == 1
    assert second_summary["events_created"] == 1
    assert len(events) == 1
    assert {observation.id for observation in event_observations} == {
        transcript.id,
        frame.id,
        ocr.id,
    }
    assert {"HAS_TRANSCRIPT", "HAS_FRAME", "HAS_OCR"}.issubset(relations)
    assert len(second_edges) == len(first_edges)


def test_debug_formatter_includes_event_observation_details(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    source_id = "source-1"
    initialize_database(db_path)

    transcript = insert_observation(
        make_observation(
            Modality.TRANSCRIPT,
            source_id=source_id,
            content="Redis reduces load on PostgreSQL.",
            start_time=10.0,
            end_time=15.0,
        ),
        db_path,
    )
    frame = insert_observation(
        make_observation(
            Modality.FRAME,
            source_id=source_id,
            content="data/frames/source-1/frame_10.jpg",
            timestamp=10.0,
        ),
        db_path,
    )
    ocr = insert_observation(
        make_observation(
            Modality.OCR,
            source_id=source_id,
            content="Redis",
            timestamp=10.0,
            metadata={"parent_frame_id": frame.id},
        ),
        db_path,
    )

    process_source(source_id, db_path=db_path)
    event = list_events_for_source(source_id, db_path)[0]
    debug_text = format_event_debug(event, get_event_observations(event.id, db_path), 1)

    assert "EVENT 1" in debug_text
    assert f"ID: {event.id}" in debug_text
    assert "Confidence:" in debug_text
    assert "Counts: transcript=1, frame=1, ocr=1" in debug_text
    assert f"- {frame.timestamp} -> {frame.content}" in debug_text
    assert f"- {ocr.timestamp} -> Redis" in debug_text
    assert transcript.id in debug_text
    assert frame.id in debug_text
    assert ocr.id in debug_text

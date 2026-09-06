from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.config import DATABASE_PATH
from app.models import EvidenceEdge, Modality, Observation, SemanticEvent
from app.processing.aligner import build_alignment_edges, split_observations
from app.processing.graph_builder import build_event_membership_edges
from app.storage.database import (
    get_event,
    get_event_observations,
    initialize_database,
    insert_edge,
    insert_event,
    link_event_observations,
    list_events_for_source,
    list_observations_for_source,
)


@dataclass
class EventCandidate:
    transcripts: list[Observation]
    start_time: float
    end_time: float


def _event_id(source_id: str, start_time: float, end_time: float, transcript_ids: list[str]) -> str:
    key = f"multimodal-rag:event:{source_id}:{start_time:.3f}:{end_time:.3f}:{','.join(transcript_ids)}"
    return str(uuid5(NAMESPACE_URL, key))


def _clean_text(text: str) -> str:
    return " ".join(text.split())


def make_title(text: str, max_length: int = 80) -> str:
    clean = _clean_text(text)
    if not clean:
        return "Untitled event"

    match = re.search(r"(.+?[.!?])(?:\s|$)", clean)
    title = match.group(1) if match else clean
    if len(title) <= max_length:
        return title

    truncated = title[: max_length + 1].rsplit(" ", 1)[0].strip()
    return truncated.rstrip(".,;:") or title[:max_length].strip()


def modality_confidence(observations: list[Observation]) -> float:
    modalities = {observation.modality for observation in observations}
    if {Modality.TRANSCRIPT, Modality.FRAME, Modality.OCR}.issubset(modalities):
        return 0.9
    if {Modality.TRANSCRIPT, Modality.FRAME}.issubset(modalities):
        return 0.75
    if Modality.TRANSCRIPT in modalities:
        return 0.6
    return 0.4


def build_event_candidates(
    transcripts: list[Observation],
    max_gap_seconds: float = 4.0,
    max_event_duration_seconds: float = 30.0,
) -> list[EventCandidate]:
    candidates: list[EventCandidate] = []
    current: list[Observation] = []
    current_start: float | None = None
    current_end: float | None = None

    for transcript in transcripts:
        if transcript.start_time is None or transcript.end_time is None:
            continue

        if not current:
            current = [transcript]
            current_start = transcript.start_time
            current_end = transcript.end_time
            continue

        assert current_start is not None
        assert current_end is not None
        gap = transcript.start_time - current_end
        candidate_duration = transcript.end_time - current_start
        if gap <= max_gap_seconds and candidate_duration <= max_event_duration_seconds:
            current.append(transcript)
            current_end = max(current_end, transcript.end_time)
            continue

        candidates.append(EventCandidate(current, current_start, current_end))
        current = [transcript]
        current_start = transcript.start_time
        current_end = transcript.end_time

    if current and current_start is not None and current_end is not None:
        candidates.append(EventCandidate(current, current_start, current_end))

    return candidates


def collect_event_observations(
    candidate: EventCandidate,
    frames: list[Observation],
    ocr_observations: list[Observation],
) -> list[Observation]:
    event_frames = [
        frame
        for frame in frames
        if frame.timestamp is not None and candidate.start_time <= frame.timestamp <= candidate.end_time
    ]
    frame_ids = {frame.id for frame in event_frames}
    event_ocr = [
        ocr
        for ocr in ocr_observations
        if ocr.metadata.get("parent_frame_id") in frame_ids
    ]
    return candidate.transcripts + event_frames + event_ocr


def build_semantic_event(
    source_id: str,
    candidate: EventCandidate,
    observations: list[Observation],
) -> SemanticEvent:
    transcript_text = " ".join(_clean_text(observation.content) for observation in candidate.transcripts)
    transcript_ids = [observation.id for observation in candidate.transcripts]
    return SemanticEvent(
        id=_event_id(source_id, candidate.start_time, candidate.end_time, transcript_ids),
        title=make_title(candidate.transcripts[0].content),
        summary=transcript_text,
        source_id=source_id,
        start_time=candidate.start_time,
        end_time=candidate.end_time,
        entities=[],
        confidence=modality_confidence(observations),
    )


def create_events_for_source(
    source_id: str,
    observations: list[Observation],
    db_path: Path = DATABASE_PATH,
    max_gap_seconds: float = 4.0,
    max_event_duration_seconds: float = 30.0,
) -> list[tuple[SemanticEvent, list[Observation]]]:
    transcripts, frames, ocr_observations = split_observations(observations)
    candidates = build_event_candidates(
        transcripts,
        max_gap_seconds=max_gap_seconds,
        max_event_duration_seconds=max_event_duration_seconds,
    )

    events: list[tuple[SemanticEvent, list[Observation]]] = []
    for candidate in candidates:
        event_observations = collect_event_observations(candidate, frames, ocr_observations)
        event = build_semantic_event(source_id, candidate, event_observations)
        insert_event(event, db_path)
        link_event_observations(event.id, [observation.id for observation in event_observations], db_path)
        events.append((event, event_observations))
    return events


def _insert_edges(edges: list[EvidenceEdge], db_path: Path) -> int:
    created = 0
    for edge in edges:
        if insert_edge(edge, db_path) == edge:
            created += 1
    return created


def process_source(
    source_id: str,
    db_path: Path = DATABASE_PATH,
    tolerance_seconds: float = 5.0,
    max_gap_seconds: float = 4.0,
    max_event_duration_seconds: float = 30.0,
) -> dict[str, Any]:
    initialize_database(db_path)
    observations = list_observations_for_source(source_id, db_path)
    transcripts, frames, ocr_observations = split_observations(observations)

    alignment_edges = build_alignment_edges(observations, tolerance_seconds=tolerance_seconds)
    _insert_edges(alignment_edges, db_path)

    events = create_events_for_source(
        source_id,
        observations,
        db_path=db_path,
        max_gap_seconds=max_gap_seconds,
        max_event_duration_seconds=max_event_duration_seconds,
    )

    membership_edges: list[EvidenceEdge] = []
    for event, event_observations in events:
        membership_edges.extend(build_event_membership_edges(event, event_observations))
    _insert_edges(membership_edges, db_path)

    multimodal_events = 0
    for event, _event_observations in events:
        modalities = {observation.modality for observation in get_event_observations(event.id, db_path)}
        if len(modalities) > 1:
            multimodal_events += 1

    return {
        "source_id": source_id,
        "transcripts": len(transcripts),
        "frames": len(frames),
        "ocr": len(ocr_observations),
        "temporal_edges": len(alignment_edges),
        "events_created": len(events),
        "multimodal_events": multimodal_events,
    }


def format_event_debug(event: SemanticEvent, observations: list[Observation], number: int) -> str:
    transcripts = sorted(
        [observation for observation in observations if observation.modality == Modality.TRANSCRIPT],
        key=lambda observation: (observation.start_time or 0, observation.end_time or 0),
    )
    frames = sorted(
        [observation for observation in observations if observation.modality == Modality.FRAME],
        key=lambda observation: observation.timestamp or 0,
    )
    ocr_observations = sorted(
        [observation for observation in observations if observation.modality == Modality.OCR],
        key=lambda observation: observation.timestamp or 0,
    )
    modalities = sorted({observation.modality.value for observation in observations})

    lines = [
        f"EVENT {number}",
        f"ID: {event.id}",
        f"Time: {event.start_time} - {event.end_time} sec",
        f"Title: {event.title}",
        f"Confidence: {event.confidence}",
        f"Modalities: {', '.join(modalities)}",
        (
            "Counts: "
            f"transcript={len(transcripts)}, "
            f"frame={len(frames)}, "
            f"ocr={len(ocr_observations)}"
        ),
        "",
        "Transcript:",
        _clean_text(' '.join(observation.content for observation in transcripts)) or "(none)",
        "",
        "Frames:",
    ]
    lines.extend(f"- {frame.timestamp} -> {frame.content}" for frame in frames)
    if not frames:
        lines.append("(none)")

    lines.extend(["", "OCR:"])
    lines.extend(f"- {observation.timestamp} -> {_clean_text(observation.content)}" for observation in ocr_observations)
    if not ocr_observations:
        lines.append("(none)")

    lines.extend(["", "Observation IDs:"])
    lines.extend(f"- {observation.id}" for observation in observations)
    if not observations:
        lines.append("(none)")
    return "\n".join(lines)


def print_events_for_source(source_id: str, db_path: Path = DATABASE_PATH) -> None:
    events = list_events_for_source(source_id, db_path)
    for index, event in enumerate(events, start=1):
        persisted_event = get_event(event.id, db_path) or event
        event_observations = get_event_observations(event.id, db_path)
        print(format_event_debug(persisted_event, event_observations, index))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build temporal alignments and semantic events for a source.")
    parser.add_argument("source_id", help="Source UUID produced by video ingestion.")
    parser.add_argument("--debug", action="store_true", help="Print human-readable event summaries.")
    args = parser.parse_args()

    summary = process_source(args.source_id)
    print(json.dumps(summary, indent=2))
    if args.debug:
        print()
        print_events_for_source(args.source_id)


if __name__ == "__main__":
    main()

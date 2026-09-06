from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.models import EdgeMethod, EvidenceEdge, Modality, Observation

TEMPORAL_ALIGNMENT_RELATION = "TEMPORALLY_ALIGNED_WITH"
CO_OCCURS_RELATION = "CO_OCCURS_WITH"


def _edge_id(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "multimodal-rag:edge:" + ":".join(parts)))


def split_observations(
    observations: list[Observation],
) -> tuple[list[Observation], list[Observation], list[Observation]]:
    transcripts = sorted(
        [observation for observation in observations if observation.modality == Modality.TRANSCRIPT],
        key=lambda observation: (observation.start_time or 0, observation.end_time or 0),
    )
    frames = sorted(
        [observation for observation in observations if observation.modality == Modality.FRAME],
        key=lambda observation: observation.timestamp or 0,
    )
    ocr = sorted(
        [observation for observation in observations if observation.modality == Modality.OCR],
        key=lambda observation: observation.timestamp or 0,
    )
    return transcripts, frames, ocr


def temporal_confidence(
    transcript: Observation,
    frame: Observation,
    tolerance_seconds: float = 5.0,
) -> tuple[float, float] | None:
    if transcript.start_time is None or transcript.end_time is None or frame.timestamp is None:
        return None

    if transcript.start_time <= frame.timestamp <= transcript.end_time:
        return 1.0, 0.0

    transcript_midpoint = (transcript.start_time + transcript.end_time) / 2
    distance = abs(frame.timestamp - transcript_midpoint)
    confidence = max(0.0, 1 - distance / tolerance_seconds)
    if confidence <= 0:
        return None
    return confidence, distance


def build_temporal_alignment_edges(
    transcripts: list[Observation],
    frames: list[Observation],
    tolerance_seconds: float = 5.0,
) -> list[EvidenceEdge]:
    edges: list[EvidenceEdge] = []
    for transcript in transcripts:
        for frame in frames:
            result = temporal_confidence(transcript, frame, tolerance_seconds)
            if result is None:
                continue

            confidence, distance = result
            edges.append(
                EvidenceEdge(
                    id=_edge_id(
                        transcript.id,
                        frame.id,
                        TEMPORAL_ALIGNMENT_RELATION,
                        EdgeMethod.TEMPORAL.value,
                    ),
                    source_node_id=transcript.id,
                    target_node_id=frame.id,
                    relation=TEMPORAL_ALIGNMENT_RELATION,
                    confidence=confidence,
                    method=EdgeMethod.TEMPORAL,
                    evidence_observation_ids=[transcript.id, frame.id],
                    metadata={
                        "temporal_distance_seconds": distance,
                        "transcript_start": transcript.start_time,
                        "transcript_end": transcript.end_time,
                        "frame_timestamp": frame.timestamp,
                    },
                )
            )
    return edges


def build_co_occurrence_edges(
    temporal_edges: list[EvidenceEdge],
    ocr_observations: list[Observation],
) -> list[EvidenceEdge]:
    frame_to_ocr: dict[str, list[Observation]] = {}
    for ocr_observation in ocr_observations:
        parent_frame_id = ocr_observation.metadata.get("parent_frame_id")
        if not parent_frame_id:
            continue
        frame_to_ocr.setdefault(parent_frame_id, []).append(ocr_observation)

    edges: list[EvidenceEdge] = []
    for temporal_edge in temporal_edges:
        transcript_id = temporal_edge.source_node_id
        frame_id = temporal_edge.target_node_id
        for ocr_observation in frame_to_ocr.get(frame_id, []):
            edges.append(
                EvidenceEdge(
                    id=_edge_id(
                        transcript_id,
                        ocr_observation.id,
                        CO_OCCURS_RELATION,
                        EdgeMethod.TEMPORAL.value,
                    ),
                    source_node_id=transcript_id,
                    target_node_id=ocr_observation.id,
                    relation=CO_OCCURS_RELATION,
                    confidence=temporal_edge.confidence,
                    method=EdgeMethod.TEMPORAL,
                    evidence_observation_ids=[transcript_id, frame_id, ocr_observation.id],
                    metadata={
                        "parent_frame_id": frame_id,
                        "temporal_alignment_edge_id": temporal_edge.id,
                    },
                )
            )
    return edges


def build_alignment_edges(
    observations: list[Observation],
    tolerance_seconds: float = 5.0,
) -> list[EvidenceEdge]:
    transcripts, frames, ocr_observations = split_observations(observations)
    temporal_edges = build_temporal_alignment_edges(transcripts, frames, tolerance_seconds)
    co_occurrence_edges = build_co_occurrence_edges(temporal_edges, ocr_observations)
    return temporal_edges + co_occurrence_edges

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.models import EdgeMethod, EvidenceEdge, Modality, Observation, SemanticEvent


def _edge_id(event_id: str, observation_id: str, relation: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"multimodal-rag:event-edge:{event_id}:{observation_id}:{relation}"))


def membership_relation(observation: Observation) -> str:
    if observation.modality == Modality.TRANSCRIPT:
        return "HAS_TRANSCRIPT"
    if observation.modality == Modality.FRAME:
        return "HAS_FRAME"
    if observation.modality == Modality.OCR:
        return "HAS_OCR"
    return f"HAS_{observation.modality.value.upper()}"


def build_event_membership_edges(
    event: SemanticEvent,
    observations: list[Observation],
) -> list[EvidenceEdge]:
    edges: list[EvidenceEdge] = []
    for observation in observations:
        relation = membership_relation(observation)
        edges.append(
            EvidenceEdge(
                id=_edge_id(event.id, observation.id, relation),
                source_node_id=event.id,
                target_node_id=observation.id,
                relation=relation,
                confidence=1.0,
                method=EdgeMethod.PROVENANCE,
                evidence_observation_ids=[observation.id],
                metadata={"source_id": event.source_id},
            )
        )
    return edges

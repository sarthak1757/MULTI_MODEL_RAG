from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import DATABASE_PATH, DEFAULT_FRAME_INTERVAL_SECONDS
from app.ingestion import frames, ocr, transcription, video
from app.models import EdgeMethod, EvidenceEdge
from app.storage.database import initialize_database, insert_edge, insert_observation


def ingest_video(
    video_path: str | Path,
    frame_interval_seconds: float = DEFAULT_FRAME_INTERVAL_SECONDS,
    db_path: Path = DATABASE_PATH,
    source_id: str | None = None,
) -> dict[str, Any]:
    path = video.validate_video_path(video_path)
    source_id = source_id or str(uuid4())
    source_path = str(path)

    initialize_database(db_path)

    transcript_observations = transcription.transcribe_video(path, source_id, source_path)
    frame_observations, duration = frames.extract_frames(
        path,
        source_id,
        source_path,
        interval_seconds=frame_interval_seconds,
    )

    for observation in transcript_observations:
        insert_observation(observation, db_path)

    for observation in frame_observations:
        insert_observation(observation, db_path)

    ocr_observations = ocr.ocr_frames(frame_observations, source_id, source_path)
    for observation in ocr_observations:
        insert_observation(observation, db_path)
        parent_frame_id = observation.metadata["parent_frame_id"]
        insert_edge(
            EvidenceEdge(
                source_node_id=observation.id,
                target_node_id=parent_frame_id,
                relation="EXTRACTED_FROM",
                confidence=1.0,
                method=EdgeMethod.PROVENANCE,
                evidence_observation_ids=[observation.id, parent_frame_id],
                metadata={"source_id": source_id},
            ),
            db_path,
        )

    return {
        "source_id": source_id,
        "transcript_segments": len(transcript_observations),
        "frames": len(frame_observations),
        "ocr_observations": len(ocr_observations),
        "duration": duration,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest an MP4 into timestamped observations.")
    parser.add_argument("video_path", help="Path to a local MP4 file.")
    parser.add_argument(
        "--frame-interval",
        type=float,
        default=DEFAULT_FRAME_INTERVAL_SECONDS,
        help="Seconds between extracted frames. Defaults to FRAME_INTERVAL_SECONDS or 5.",
    )
    args = parser.parse_args()

    summary = ingest_video(args.video_path, frame_interval_seconds=args.frame_interval)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

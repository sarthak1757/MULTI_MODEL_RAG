from pathlib import Path

import pytest

from app.ingestion.pipeline import ingest_video
from app.models import Modality, Observation
from app.storage.database import list_edges, list_observations


def test_ingest_video_requires_existing_file(tmp_path: Path) -> None:
    missing_video = tmp_path / "missing.mp4"

    with pytest.raises(FileNotFoundError, match="Video file does not exist"):
        ingest_video(missing_video, db_path=tmp_path / "test.sqlite3")


def test_ingest_video_persists_observations_and_provenance_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_path = tmp_path / "demo.mp4"
    video_path.write_bytes(b"fake video")
    db_path = tmp_path / "test.sqlite3"

    def fake_transcribe_video(path: Path, source_id: str, source_path: str) -> list[Observation]:
        return [
            Observation(
                modality=Modality.TRANSCRIPT,
                content="Welcome to the demo.",
                source_id=source_id,
                source_path=source_path,
                start_time=0.0,
                end_time=2.0,
            )
        ]

    def fake_extract_frames(
        path: Path,
        source_id: str,
        source_path: str,
        interval_seconds: float,
    ) -> tuple[list[Observation], float]:
        return (
            [
                Observation(
                    modality=Modality.FRAME,
                    content=str(tmp_path / "frame_0.jpg"),
                    source_id=source_id,
                    source_path=source_path,
                    timestamp=0.0,
                )
            ],
            5.0,
        )

    def fake_ocr_frames(
        frame_observations: list[Observation],
        source_id: str,
        source_path: str,
    ) -> list[Observation]:
        frame_observation = frame_observations[0]
        return [
            Observation(
                modality=Modality.OCR,
                content="Redis",
                source_id=source_id,
                source_path=source_path,
                timestamp=frame_observation.timestamp,
                confidence=0.9,
                metadata={"parent_frame_id": frame_observation.id},
            )
        ]

    monkeypatch.setattr("app.ingestion.pipeline.transcription.transcribe_video", fake_transcribe_video)
    monkeypatch.setattr("app.ingestion.pipeline.frames.extract_frames", fake_extract_frames)
    monkeypatch.setattr("app.ingestion.pipeline.ocr.ocr_frames", fake_ocr_frames)

    summary = ingest_video(video_path, db_path=db_path)
    observations = list_observations(db_path)
    edges = list_edges(db_path)

    assert summary["transcript_segments"] == 1
    assert summary["frames"] == 1
    assert summary["ocr_observations"] == 1
    assert summary["duration"] == 5.0
    assert [observation.modality for observation in observations] == [
        Modality.TRANSCRIPT,
        Modality.FRAME,
        Modality.OCR,
    ]
    assert len(edges) == 1
    assert edges[0].relation == "EXTRACTED_FROM"
    assert edges[0].evidence_observation_ids == [
        observations[2].id,
        observations[1].id,
    ]


def test_ingest_video_handles_frames_without_ocr_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_path = tmp_path / "silent.mp4"
    video_path.write_bytes(b"fake video")
    db_path = tmp_path / "test.sqlite3"

    monkeypatch.setattr(
        "app.ingestion.pipeline.transcription.transcribe_video",
        lambda path, source_id, source_path: [],
    )
    monkeypatch.setattr(
        "app.ingestion.pipeline.frames.extract_frames",
        lambda path, source_id, source_path, interval_seconds: (
            [
                Observation(
                    modality=Modality.FRAME,
                    content=str(tmp_path / "frame_0.jpg"),
                    source_id=source_id,
                    source_path=source_path,
                    timestamp=0.0,
                )
            ],
            1.0,
        ),
    )
    monkeypatch.setattr(
        "app.ingestion.pipeline.ocr.ocr_frames",
        lambda frame_observations, source_id, source_path: [],
    )

    summary = ingest_video(video_path, db_path=db_path)

    assert summary["ocr_observations"] == 0
    assert len(list_observations(db_path)) == 1
    assert list_edges(db_path) == []

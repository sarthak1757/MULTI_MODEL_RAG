from __future__ import annotations

from pathlib import Path

from app.config import WHISPER_MODEL_SIZE
from app.models import Modality, Observation


def transcribe_video(
    video_path: str | Path,
    source_id: str,
    source_path: str,
    model_size: str = WHISPER_MODEL_SIZE,
) -> list[Observation]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is required for transcription. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(video_path), vad_filter=True)

    observations: list[Observation] = []
    for segment in segments:
        content = segment.text.strip()
        if not content:
            continue

        confidence = getattr(segment, "confidence", None)
        observations.append(
            Observation(
                modality=Modality.TRANSCRIPT,
                content=content,
                source_id=source_id,
                source_path=source_path,
                start_time=float(segment.start),
                end_time=float(segment.end),
                confidence=confidence,
                metadata={
                    "transcription_engine": "faster-whisper",
                    "model_size": model_size,
                },
            )
        )

    return observations

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.config import EASYOCR_LANGUAGES
from app.models import Modality, Observation

_reader: Any = None


def _get_reader(languages: list[str]) -> Any:
    global _reader
    if _reader is None:
        try:
            import easyocr
        except ImportError as exc:
            raise RuntimeError(
                "EasyOCR is required for OCR. Install dependencies with: "
                "pip install -r requirements.txt"
            ) from exc
        _reader = easyocr.Reader(languages, gpu=False)
    return _reader


def ocr_frame(
    frame_observation: Observation,
    source_id: str,
    source_path: str,
    languages: list[str] = EASYOCR_LANGUAGES,
) -> Optional[Observation]:
    reader = _get_reader(languages)
    results = reader.readtext(str(Path(frame_observation.content)), detail=1, paragraph=False)

    text_parts: list[str] = []
    confidences: list[float] = []
    for result in results:
        if len(result) < 3:
            continue
        _bbox, text, confidence = result
        clean_text = str(text).strip()
        if len(clean_text) < 2:
            continue
        text_parts.append(clean_text)
        confidences.append(float(confidence))

    if not text_parts:
        return None

    combined_text = "\n".join(text_parts)
    confidence = sum(confidences) / len(confidences) if confidences else None

    return Observation(
        modality=Modality.OCR,
        content=combined_text,
        source_id=source_id,
        source_path=source_path,
        timestamp=frame_observation.timestamp,
        confidence=confidence,
        metadata={
            "parent_frame_id": frame_observation.id,
            "parent_frame_path": frame_observation.content,
            "ocr_engine": "easyocr",
            "text_count": len(text_parts),
        },
    )


def ocr_frames(
    frame_observations: list[Observation],
    source_id: str,
    source_path: str,
    languages: list[str] = EASYOCR_LANGUAGES,
) -> list[Observation]:
    observations: list[Observation] = []
    for frame_observation in frame_observations:
        ocr_observation = ocr_frame(frame_observation, source_id, source_path, languages)
        if ocr_observation is not None:
            observations.append(ocr_observation)
    return observations

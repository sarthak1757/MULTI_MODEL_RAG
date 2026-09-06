from __future__ import annotations

from pathlib import Path

from app.config import DEFAULT_FRAME_INTERVAL_SECONDS, FRAMES_DIR
from app.models import Modality, Observation


def _format_timestamp(timestamp: float) -> str:
    formatted = f"{timestamp:.1f}"
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def extract_frames(
    video_path: str | Path,
    source_id: str,
    source_path: str,
    interval_seconds: float = DEFAULT_FRAME_INTERVAL_SECONDS,
    output_root: Path = FRAMES_DIR,
) -> tuple[list[Observation], float]:
    if interval_seconds <= 0:
        raise ValueError("Frame extraction interval must be greater than 0 seconds.")

    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required for frame extraction. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    path = Path(video_path)
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video file for frame extraction: {path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 0
    frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = float(frame_count / fps) if fps > 0 else 0.0

    output_dir = output_root / source_id
    output_dir.mkdir(parents=True, exist_ok=True)

    observations: list[Observation] = []
    timestamp = 0.0
    while timestamp <= duration if duration > 0 else timestamp == 0.0:
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        success, frame = capture.read()
        if not success:
            break

        label = _format_timestamp(timestamp)
        frame_path = output_dir / f"frame_{label}.jpg"
        cv2.imwrite(str(frame_path), frame)

        observations.append(
            Observation(
                modality=Modality.FRAME,
                content=str(frame_path),
                source_id=source_id,
                source_path=source_path,
                timestamp=float(timestamp),
                confidence=1.0,
                metadata={"frame_interval_seconds": interval_seconds},
            )
        )
        timestamp += interval_seconds

    capture.release()
    return observations, duration

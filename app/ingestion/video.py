from __future__ import annotations

from pathlib import Path


def validate_video_path(video_path: str | Path) -> Path:
    path = Path(video_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Video file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Video path is not a file: {path}")
    return path


def get_video_duration(video_path: str | Path) -> float:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required for video metadata. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    path = validate_video_path(video_path)
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video file: {path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 0
    frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    capture.release()

    if fps <= 0:
        return 0.0
    return float(frame_count / fps)

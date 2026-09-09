import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")

APP_DIR = PROJECT_ROOT / "app"
DATA_DIR = PROJECT_ROOT / "data"

UPLOADS_DIR = DATA_DIR / "uploads"
FRAMES_DIR = DATA_DIR / "frames"
PROCESSED_DIR = DATA_DIR / "processed"
INDEXES_DIR = DATA_DIR / "indexes"

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", DATA_DIR / "processed" / "multimodal_rag.sqlite3"))
NEO4J_URI = os.getenv("NEO4J_URI", "").strip()
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j").strip()
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j").strip()
DEFAULT_FRAME_INTERVAL_SECONDS = float(os.getenv("FRAME_INTERVAL_SECONDS", "5"))
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
EASYOCR_LANGUAGES = [
    language.strip()
    for language in os.getenv("EASYOCR_LANGUAGES", "en").split(",")
    if language.strip()
]


def ensure_data_dirs() -> None:
    for path in (UPLOADS_DIR, FRAMES_DIR, PROCESSED_DIR, INDEXES_DIR):
        path.mkdir(parents=True, exist_ok=True)

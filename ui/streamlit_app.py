from __future__ import annotations

from pathlib import Path
import shutil
import sys
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.config import DATABASE_PATH, INDEXES_DIR, UPLOADS_DIR
from app.generation.answer import answer_question
from app.ingestion.image import ingest_image
from app.ingestion.pdf import ingest_pdf
from app.ingestion.pipeline import ingest_video
from app.models import Source, SourceStatus, SourceType
from app.processing.event_builder import process_source
from app.retrieval.vector_store import build_index
from app.semantic.enricher import enrich_source
from app.storage.database import (
    insert_source,
    list_events,
    list_events_for_source,
    list_observations_for_source,
    list_sources,
    update_source_status,
)

DEFAULT_SOURCE_ID = "c178e43b-576b-486b-a310-1c47774c0bf2"
DEFAULT_QUESTION = "Why is English useful for solving global problems?"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PDF_EXTENSIONS = {".pdf"}


def _init_state() -> None:
    st.session_state.setdefault("active_source_id", DEFAULT_SOURCE_ID)
    st.session_state.setdefault("processing_source_id", None)
    st.session_state.setdefault("last_question", DEFAULT_QUESTION)
    st.session_state.setdefault("last_answer", None)
    st.session_state.setdefault("source_manager_view", "existing")


def _index_exists(source_id: str) -> bool:
    return (INDEXES_DIR / source_id / "events.faiss").exists()


def _source_completely_processed(source_id: str) -> bool:
    return (
        bool(list_observations_for_source(source_id, DATABASE_PATH))
        and bool(list_events_for_source(source_id, DATABASE_PATH))
        and _index_exists(source_id)
    )


def _duration_from_events(source_id: str) -> float | None:
    ends = [event.end_time for event in list_events_for_source(source_id, DATABASE_PATH) if event.end_time is not None]
    return max(ends) if ends else None


def _source_type_from_path(path: str) -> SourceType:
    suffix = Path(path).suffix.lower()
    if suffix in PDF_EXTENSIONS:
        return SourceType.PDF
    if suffix in IMAGE_EXTENSIONS:
        return SourceType.IMAGE
    return SourceType.VIDEO


def _fallback_sources() -> list[Source]:
    sources: dict[str, Source] = {}
    for event in list_events(DATABASE_PATH):
        if event.source_id in sources:
            continue
        observations = list_observations_for_source(event.source_id, DATABASE_PATH)
        first_path = observations[0].source_path if observations else event.source_id
        sources[event.source_id] = Source(
            id=event.source_id,
            filename=Path(first_path).name,
            source_type=_source_type_from_path(first_path),
            path=first_path,
            duration=_duration_from_events(event.source_id),
            status=SourceStatus.READY if _source_completely_processed(event.source_id) else SourceStatus.UPLOADED,
        )
    return list(sources.values())


def _available_sources() -> list[Source]:
    try:
        registered = list_sources(DATABASE_PATH)
        known = {source.id: source for source in registered}
        for source in _fallback_sources():
            known.setdefault(source.id, source)
        return list(known.values())
    except Exception:
        return _fallback_sources()


def _format_duration(seconds: float | None) -> str:
    if not seconds:
        return "duration unknown"
    minutes = int(seconds // 60)
    remainder = int(seconds % 60)
    return f"{minutes}m {remainder:02d}s"


def _source_label(source: Source) -> str:
    type_label = source.source_type.value.title()
    return f"{source.filename}\n{type_label} · {_format_duration(source.duration)}\n{source.id[:8]}..."


def _active_source(sources: list[Source]) -> Source | None:
    active_id = st.session_state.active_source_id
    for source in sources:
        if source.id == active_id:
            return source
    return sources[0] if sources else None


def _safe_upload_path(filename: str) -> Path:
    suffix = Path(filename).suffix.lower()
    stem = Path(filename).stem[:80] or "source"
    safe_stem = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in stem)
    return UPLOADS_DIR / f"{safe_stem}_{uuid4().hex[:12]}{suffix}"


def _save_upload(uploaded_file) -> Path:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    destination = _safe_upload_path(uploaded_file.name)
    with destination.open("wb") as file:
        shutil.copyfileobj(uploaded_file, file)
    return destination


def _set_active_source(source_id: str) -> None:
    if st.session_state.active_source_id != source_id:
        st.session_state.last_answer = None
    st.session_state.active_source_id = source_id


def _run_video_pipeline(saved_path: Path, original_filename: str) -> str:
    summary = ingest_video(saved_path, db_path=DATABASE_PATH)
    source_id = summary["source_id"]
    insert_source(
        Source(
            id=source_id,
            filename=original_filename,
            source_type=SourceType.VIDEO,
            path=str(saved_path),
            duration=summary.get("duration"),
            status=SourceStatus.PROCESSING,
            metadata={"uploaded_filename": original_filename},
        ),
        DATABASE_PATH,
    )
    st.write("✓ Video loaded")
    st.write(f"✓ Transcript extracted — {summary['transcript_segments']} segments")
    st.write(f"✓ Frames extracted — {summary['frames']}")
    st.write(f"✓ OCR extracted — {summary['ocr_observations']} observations")

    processing_summary = process_source(source_id, db_path=DATABASE_PATH)
    st.write(f"✓ Temporal graph created — {processing_summary['temporal_edges']} edges")
    st.write(f"✓ Semantic events created — {processing_summary['events_created']}")

    enrichment_summary = enrich_source(source_id, db_path=DATABASE_PATH)
    st.write(f"✓ Events enriched — {enrichment_summary['events_enriched']}")

    index_summary = build_index(source_id, db_path=DATABASE_PATH)
    st.write(f"✓ Vector index built — {index_summary['events_indexed']} events")
    update_source_status(source_id, SourceStatus.READY, DATABASE_PATH, duration=summary.get("duration"))
    return source_id


def _run_document_or_image_pipeline(saved_path: Path, original_filename: str) -> str:
    suffix = saved_path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        summary = ingest_image(saved_path, DATABASE_PATH)
        source_id = summary["source_id"]
        update_source_status(source_id, SourceStatus.PROCESSING, DATABASE_PATH, metadata={"uploaded_filename": original_filename})
        st.write("✓ Image observation created")
        st.write(f"✓ OCR extracted — {summary['ocr_observations']} observations")
        st.write(f"✓ Semantic events created — {summary['events_created']}")
    elif suffix in PDF_EXTENSIONS:
        summary = ingest_pdf(saved_path, DATABASE_PATH)
        source_id = summary["source_id"]
        update_source_status(source_id, SourceStatus.PROCESSING, DATABASE_PATH, metadata={"uploaded_filename": original_filename})
        st.write(f"✓ PDF text extracted — {summary['pages']} pages")
        st.write(f"✓ Semantic events created — {summary['events_created']}")
    else:
        raise ValueError("Unsupported source type.")

    enrichment_summary = enrich_source(source_id, db_path=DATABASE_PATH)
    st.write(f"✓ Events enriched — {enrichment_summary['events_enriched']}")
    index_summary = build_index(source_id, db_path=DATABASE_PATH)
    st.write(f"✓ Vector index built — {index_summary['events_indexed']} events")
    update_source_status(source_id, SourceStatus.READY, DATABASE_PATH)
    return source_id


def _process_upload(uploaded_file) -> None:
    saved_path = _save_upload(uploaded_file)
    try:
        with st.status("Processing source...", expanded=True) as status:
            source_id = (
                _run_video_pipeline(saved_path, uploaded_file.name)
                if saved_path.suffix.lower() in VIDEO_EXTENSIONS
                else _run_document_or_image_pipeline(saved_path, uploaded_file.name)
            )
            status.update(label="Source ready", state="complete")
        _set_active_source(source_id)
        st.session_state.source_manager_view = "existing"
        st.success("Source ready")
        st.rerun()
    except Exception as exc:
        st.error("Processing failed")
        st.caption(str(exc))


def _show_source_manager() -> list[Source]:
    st.sidebar.subheader("SOURCE")
    sources = _available_sources()
    view_to_label = {"existing": "Existing Sources", "upload": "Upload New"}
    label_to_view = {label: view for view, label in view_to_label.items()}
    current_label = view_to_label.get(st.session_state.source_manager_view, "Existing Sources")
    selected_label = st.sidebar.radio(
        "Source workflow",
        ["Existing Sources", "Upload New"],
        index=0 if current_label == "Existing Sources" else 1,
        key="source_manager_selector",
    )
    selected_view = label_to_view[selected_label]
    if selected_view != st.session_state.source_manager_view:
        st.session_state.source_manager_view = selected_view

    mode = st.session_state.source_manager_view

    if mode == "existing":
        if not sources:
            st.sidebar.info("No processed sources yet.")
            return sources
        labels = [_source_label(source) for source in sources]
        active = _active_source(sources)
        index = sources.index(active) if active in sources else 0
        selected_index = st.sidebar.selectbox("Choose source", range(len(sources)), format_func=lambda i: labels[i], index=index)
        selected = sources[selected_index]
        if st.sidebar.button("Change Source"):
            _set_active_source(selected.id)
            st.session_state.source_manager_view = "existing"
            st.rerun()
        if _source_completely_processed(selected.id):
            st.sidebar.success("Already processed ✓")
        else:
            st.sidebar.warning("Processing incomplete")
    else:
        st.sidebar.write("Supported: Video · PDF · Image")
        uploaded = st.sidebar.file_uploader(
            "Upload a source",
            type=["mp4", "mov", "mkv", "pdf", "png", "jpg", "jpeg"],
            accept_multiple_files=False,
        )
        if uploaded is not None:
            st.sidebar.caption(f"{uploaded.name} · {uploaded.size / (1024 * 1024):.1f} MB")
            if st.sidebar.button("Process Source", type="primary"):
                _process_upload(uploaded)
    return _available_sources()


def _show_pipeline_sidebar() -> None:
    st.sidebar.divider()
    st.sidebar.title("Pipeline")
    for stage in [
        "Video ingestion",
        "Transcript",
        "Frames",
        "OCR",
        "Timeline alignment",
        "Semantic events",
        "Evidence graph",
        "FAISS retrieval",
        "Grounded answer",
    ]:
        st.sidebar.write(f"✓ {stage}")
    st.sidebar.divider()
    st.sidebar.write("Vector model: all-MiniLM-L6-v2")
    st.sidebar.write("LLM: Gemini free tier")
    st.sidebar.write("Storage: SQLite + FAISS")


def _pct(value: float | None) -> str:
    return f"{round((value or 0.0) * 100)}%"


def _text_join(items: list[dict[str, Any]], key: str) -> str:
    return "\n\n".join(str(item.get(key) or "").strip() for item in items if item.get(key))


def _modalities(bundle: dict[str, Any]) -> list[str]:
    modalities = []
    if bundle["transcripts"]:
        modalities.append("Transcript")
    if bundle["ocr"]:
        modalities.append("OCR")
    if bundle["frames"] or bundle.get("images"):
        modalities.append("Frames")
    if bundle["relationships"]:
        modalities.append("Evidence graph")
    return modalities


def _select_frames(bundle: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    frames = bundle["frames"] or [
        {"id": image["id"], "timestamp": None, "path": image["path"], "confidence": image["confidence"]}
        for image in bundle.get("images", [])
    ]
    if not frames:
        return []
    event = bundle["event"]
    midpoint = ((event.get("start_time") or 0) + (event.get("end_time") or 0)) / 2
    return sorted(frames, key=lambda frame: abs((frame.get("timestamp") or 0) - midpoint))[:limit]


def _show_frame_evidence(bundle: dict[str, Any]) -> None:
    selected = _select_frames(bundle)
    if not selected:
        st.caption("No frame evidence attached to this event.")
        return
    columns = st.columns(len(selected))
    for column, frame in zip(columns, selected):
        with column:
            path = Path(frame["path"])
            if path.exists():
                st.image(str(path), use_container_width=True)
            else:
                st.info("Frame image unavailable")
            st.caption(f"{frame.get('timestamp')}s" if frame.get("timestamp") is not None else "Image")


def _entity_name_map(bundle: dict[str, Any]) -> dict[str, str]:
    return {entity["id"]: entity["name"] for entity in bundle["entities"]}


def _semantic_relations(bundle: dict[str, Any]) -> list[str]:
    names = _entity_name_map(bundle)
    lines = []
    for relationship in bundle["relationships"]:
        if relationship["method"] != "llm":
            continue
        source = names.get(relationship["source"])
        target = names.get(relationship["target"])
        if source and target:
            lines.append(f"{source} -> {relationship['relation']} -> {target}")
    return lines


def _show_active_source(source: Source | None) -> None:
    st.subheader("Active Source")
    if source is None:
        st.info("No source selected. Upload or select a source to begin.")
        return
    col1, col2, col3 = st.columns([3, 2, 1])
    with col1:
        st.markdown(f"**{source.filename}**")
        st.caption(f"{source.source_type.value.title()} · {_format_duration(source.duration)}")
    with col2:
        status_label = "Ready ✓" if source.status == SourceStatus.READY or _source_completely_processed(source.id) else source.status.value.title()
        st.metric("Status", status_label)
    with col3:
        if st.button("Change Source"):
            st.session_state.source_manager_view = "existing"
            st.session_state.last_answer = None
            st.rerun()


def _show_answer(payload: dict[str, Any]) -> None:
    st.subheader("C. Answer")
    if payload.get("error"):
        st.warning("Answer generation failed, but retrieved evidence is shown below.")
        st.caption(payload["error"])
    st.markdown(payload["answer"])
    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric("Confidence", _pct(payload["confidence"]))
    with col2:
        modalities = payload.get("used_modalities") or sorted(
            {modality for result in payload["retrieval"].get("results", []) for modality in _modalities(result["evidence_bundle"])}
        )
        st.caption("Used evidence: " + (" · ".join(modalities) if modalities else "None"))


def _show_retrieved_evidence(payload: dict[str, Any]) -> None:
    st.subheader("D. Retrieved Evidence")
    results = payload["retrieval"].get("results", [])
    if not results:
        st.info("No retrieved events.")
        return
    for result in results:
        bundle = result["evidence_bundle"]
        event = bundle["event"]
        with st.expander(f"Event {result['rank']} — {event['title']}", expanded=result["rank"] == 1):
            st.caption(f"{event['start_time']}s – {event['end_time']}s · score: {result['score']:.3f}")
            st.markdown("**Transcript**")
            st.write(_text_join(bundle["transcripts"], "content") or "No transcript evidence.")
            if bundle.get("documents"):
                st.markdown("**Document evidence**")
                st.write(_text_join(bundle["documents"], "text") or "No document evidence.")
            st.markdown("**Raw OCR evidence**")
            st.write(_text_join(bundle["ocr"], "text") or "No OCR evidence.")
            st.markdown("**Entities**")
            entities = [entity["name"] for entity in bundle["entities"]]
            st.write(", ".join(entities) if entities else "No entities linked.")
            st.markdown("**Frame evidence**")
            _show_frame_evidence(bundle)


def _show_timeline(payload: dict[str, Any]) -> None:
    st.subheader("E. Event Timeline")
    results = sorted(payload["retrieval"].get("results", []), key=lambda result: result["evidence_bundle"]["event"].get("start_time") or 0)
    if not results:
        st.info("No events to place on the timeline.")
        return
    for result in results:
        event = result["evidence_bundle"]["event"]
        st.markdown(f"`{event['start_time']}s` - `{event['end_time']}s` **{event['title']}** · rank {result['rank']}")


def _show_graph_summary(payload: dict[str, Any]) -> None:
    st.subheader("F. Evidence Graph Summary")
    results = payload["retrieval"].get("results", [])
    if not results:
        st.info("No graph evidence to summarize.")
        return
    top_bundle = results[0]["evidence_bundle"]
    methods = sorted({relationship["method"] for relationship in top_bundle["relationships"]})
    st.markdown("**Event**")
    st.write(top_bundle["event"]["title"])
    st.markdown("**Connected evidence**")
    st.write(f"- {len(top_bundle['transcripts'])} transcript segments")
    st.write(f"- {len(top_bundle['frames']) + len(top_bundle.get('images', []))} frames/images")
    st.write(f"- {len(top_bundle['ocr'])} OCR observations")
    st.write(f"- {len(top_bundle.get('documents', []))} document observations")
    st.write(f"- {len(top_bundle['entities'])} entities")
    st.markdown("**Relationship methods**")
    st.write(", ".join(methods) if methods else "No graph relationships attached.")
    st.markdown("**Semantic relations**")
    semantic_relations = _semantic_relations(top_bundle)
    if semantic_relations:
        for relation in semantic_relations[:8]:
            st.write(f"- {relation}")
    else:
        st.write("No semantic LLM relationships attached to the top event.")


def main() -> None:
    st.set_page_config(page_title="Multimodal Event RAG", layout="wide")
    _init_state()
    sources = _show_source_manager()
    _show_pipeline_sidebar()

    st.title("Multimodal Event RAG")
    st.caption("Event-centric retrieval across transcript, video frames, OCR and evidence relationships.")
    active = _active_source(sources)
    if active is not None:
        _set_active_source(active.id)
    _show_active_source(active)

    st.subheader("B. Ask")
    ready = active is not None and _source_completely_processed(active.id)
    if not ready:
        st.info("Upload or select a ready source before asking.")
    question = st.text_area("Question", value=st.session_state.last_question, height=90, disabled=not ready)
    ask = st.button("Ask", type="primary", disabled=not ready)

    if ask and active is not None:
        st.session_state.last_question = question
        with st.spinner("Retrieving evidence and generating grounded answer..."):
            try:
                st.session_state.last_answer = answer_question(active.id, question.strip())
            except FileNotFoundError:
                st.error("Index not built for this source.")
                st.session_state.last_answer = None
            except Exception as exc:
                st.error(f"Something went wrong: {exc}")
                st.session_state.last_answer = None

    if st.session_state.last_answer:
        _show_answer(st.session_state.last_answer)
        _show_retrieved_evidence(st.session_state.last_answer)
        _show_timeline(st.session_state.last_answer)
        _show_graph_summary(st.session_state.last_answer)


if __name__ == "__main__":
    main()

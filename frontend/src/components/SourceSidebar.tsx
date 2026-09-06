import { useState, type KeyboardEvent, type MouseEvent } from "react";
import { FileText, Image, Plus, RotateCcw, Trash2, Video } from "lucide-react";
import type { Source, SourceStatus } from "../types/api";

interface Props {
  sources: Source[];
  activeSourceId: string | null;
  onSelect: (source: Source) => void;
  onAdd: () => void;
  onRetry: (source: Source) => Promise<void>;
  onDelete: (source: Source) => Promise<void>;
}

function labelType(type: string): string {
  return type.charAt(0).toUpperCase() + type.slice(1);
}

function SourceTypeIcon({ type }: { type: Source["source_type"] }) {
  const props = { size: 14, strokeWidth: 1.8 };
  if (type === "video") return <Video {...props} />;
  if (type === "pdf") return <FileText {...props} />;
  return <Image {...props} />;
}

const FILTERS: Array<"all" | SourceStatus> = ["all", "ready", "processing", "failed", "uploaded"];

export default function SourceSidebar({ sources, activeSourceId, onSelect, onAdd, onRetry, onDelete }: Props) {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [busySourceId, setBusySourceId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ sourceId: string; message: string } | null>(null);
  const [filter, setFilter] = useState<"all" | SourceStatus>("all");

  const filteredSources = filter === "all" ? sources : sources.filter((source) => source.status === filter);
  const counts = sources.reduce<Record<string, number>>(
    (accumulator, source) => {
      accumulator.all += 1;
      accumulator[source.status] += 1;
      return accumulator;
    },
    { all: 0, uploaded: 0, processing: 0, ready: 0, failed: 0 }
  );

  const stopAction = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
  };

  const selectFromKeyboard = (event: KeyboardEvent<HTMLDivElement>, source: Source) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(source);
    }
  };

  const retryFailedSource = async (event: MouseEvent<HTMLButtonElement>, source: Source) => {
    stopAction(event);
    setBusySourceId(source.id);
    setActionError(null);
    setConfirmDeleteId(null);
    try {
      await onRetry(source);
    } catch (err) {
      setActionError({ sourceId: source.id, message: err instanceof Error ? err.message : "Retry failed." });
    } finally {
      setBusySourceId(null);
    }
  };

  const deleteSource = async (event: MouseEvent<HTMLButtonElement>, source: Source) => {
    stopAction(event);
    setBusySourceId(source.id);
    setActionError(null);
    try {
      await onDelete(source);
      setConfirmDeleteId(null);
    } catch (err) {
      setActionError({ sourceId: source.id, message: err instanceof Error ? err.message : "Delete failed." });
    } finally {
      setBusySourceId(null);
    }
  };

  return (
    <aside className="sidebar">
      <div className="sidebarHeader">
        <div>
          <h2>Sources</h2>
          <span className="sidebarCount">{sources.length} total</span>
        </div>
        <button className="ghostButton iconTextButton" onClick={onAdd}><Plus size={14} />Add</button>
      </div>
      <div className="sourceFilters" aria-label="Source filters">
        {FILTERS.map((item) => (
          <button
            key={item}
            className={filter === item ? "active" : ""}
            onClick={() => setFilter(item)}
            type="button"
          >
            <span>{labelType(item)}</span>
            <strong>{counts[item]}</strong>
          </button>
        ))}
      </div>
      <div className="sourceList">
        {sources.length === 0 && <p className="muted">No sources yet.</p>}
        {sources.length > 0 && filteredSources.length === 0 && <p className="muted">No {filter} sources.</p>}
        {filteredSources.map((source) => (
          <div
            key={source.id}
            className={`sourceItem ${source.id === activeSourceId ? "active" : ""} ${source.status}`}
            onClick={() => onSelect(source)}
            onKeyDown={(event) => selectFromKeyboard(event, source)}
            role="button"
            tabIndex={0}
          >
            <span className="sourceTypeIcon"><SourceTypeIcon type={source.source_type} /></span>
            <span className="sourceBody">
              <strong>{source.filename}</strong>
              <small><i className={"sourceDot " + source.status} />{labelType(source.source_type)} · {labelType(source.status)}</small>
              {source.status === "failed" && source.error_message && <small className="sourceError">{source.error_message}</small>}
              {source.status === "failed" && actionError?.sourceId === source.id && (
                <small className="sourceError">{actionError.message}</small>
              )}
              {confirmDeleteId === source.id ? (
                <div className="sourceConfirm" onClick={(event) => event.stopPropagation()}>
                  <small>Delete this source and its index?</small>
                  <div className="sourceActions">
                    <button
                      className="compactButton"
                      disabled={busySourceId === source.id}
                      onClick={(event) => {
                        stopAction(event);
                        setConfirmDeleteId(null);
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      className="compactButton dangerButton"
                      disabled={busySourceId === source.id}
                      onClick={(event) => deleteSource(event, source)}
                    >
                      {busySourceId === source.id ? "Deleting..." : "Confirm Delete"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="sourceActions" onClick={(event) => event.stopPropagation()}>
                  {source.status === "failed" && (
                    <button
                      className="compactButton"
                      disabled={busySourceId === source.id}
                      onClick={(event) => retryFailedSource(event, source)}
                    >
                      <RotateCcw size={12} />{busySourceId === source.id ? "Retrying..." : "Retry"}
                    </button>
                  )}
                  <button
                    className="compactButton dangerButton"
                    disabled={busySourceId === source.id}
                    onClick={(event) => {
                      stopAction(event);
                      setActionError(null);
                      setConfirmDeleteId(source.id);
                    }}
                  >
                    <Trash2 size={12} />Delete
                  </button>
                </div>
              )}
            </span>
          </div>
        ))}
      </div>
      <div className="sidebarMeta">
        <p>Vector model: all-MiniLM-L6-v2</p>
        <p>LLM: Gemini free tier</p>
        <p>Storage: SQLite + FAISS</p>
      </div>
    </aside>
  );
}

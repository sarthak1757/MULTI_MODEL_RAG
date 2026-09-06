import { useState, type KeyboardEvent, type MouseEvent } from "react";
import type { Source } from "../types/api";

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

export default function SourceSidebar({ sources, activeSourceId, onSelect, onAdd, onRetry, onDelete }: Props) {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [busySourceId, setBusySourceId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ sourceId: string; message: string } | null>(null);

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

  const deleteFailedSource = async (event: MouseEvent<HTMLButtonElement>, source: Source) => {
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
        <h2>Sources</h2>
        <button className="ghostButton" onClick={onAdd}>+ Add Source</button>
      </div>
      <div className="sourceList">
        {sources.length === 0 && <p className="muted">No sources yet.</p>}
        {sources.map((source) => (
          <div
            key={source.id}
            className={`sourceItem ${source.id === activeSourceId ? "active" : ""} ${source.status}`}
            onClick={() => onSelect(source)}
            onKeyDown={(event) => selectFromKeyboard(event, source)}
            role="button"
            tabIndex={0}
          >
            <span className="sourceDot" />
            <span className="sourceBody">
              <strong>{source.filename}</strong>
              <small>{labelType(source.source_type)} · {labelType(source.status)}</small>
              {source.status === "failed" && source.error_message && <small className="sourceError">{source.error_message}</small>}
              {source.status === "failed" && actionError?.sourceId === source.id && (
                <small className="sourceError">{actionError.message}</small>
              )}
              {source.status === "failed" && (
                confirmDeleteId === source.id ? (
                  <div className="sourceConfirm" onClick={(event) => event.stopPropagation()}>
                    <small>Delete this failed source?</small>
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
                        onClick={(event) => deleteFailedSource(event, source)}
                      >
                        {busySourceId === source.id ? "Deleting..." : "Confirm Delete"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="sourceActions" onClick={(event) => event.stopPropagation()}>
                    <button
                      className="compactButton"
                      disabled={busySourceId === source.id}
                      onClick={(event) => retryFailedSource(event, source)}
                    >
                      {busySourceId === source.id ? "Retrying..." : "Retry"}
                    </button>
                    <button
                      className="compactButton dangerButton"
                      disabled={busySourceId === source.id}
                      onClick={(event) => {
                        stopAction(event);
                        setActionError(null);
                        setConfirmDeleteId(source.id);
                      }}
                    >
                      Delete
                    </button>
                  </div>
                )
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

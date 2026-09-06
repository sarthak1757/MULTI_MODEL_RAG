import type { Source } from "../types/api";

interface Props {
  source: Source | null;
  onChangeSource: () => void;
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return "duration unknown";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60).toString().padStart(2, "0");
  return `${minutes}m ${remainder}s`;
}

function formatCreatedAt(value: string | undefined): string {
  if (!value) return "created date unknown";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function label(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export default function ActiveSource({ source, onChangeSource }: Props) {
  return (
    <section className="panel activeSource">
      <div>
        <span className="eyebrow">Active Source</span>
        {source ? (
          <>
            <h2>{source.filename}</h2>
            <div className="metadataRow">
              <span>{label(source.source_type)}</span>
              <span>{formatDuration(source.duration)}</span>
              <span>{formatCreatedAt(source.created_at)}</span>
            </div>
            {source.error_message && <p className="sourceError">{source.error_message}</p>}
          </>
        ) : (
          <>
            <h2>No source selected</h2>
            <p>Upload or select a source to begin.</p>
          </>
        )}
      </div>
      <div className="statusBlock">
        <span className={`statusPill ${source?.status ?? "uploaded"}`}>{source ? label(source.status) : "None"}</span>
        <button className="ghostButton" onClick={onChangeSource}>Upload Source</button>
      </div>
    </section>
  );
}

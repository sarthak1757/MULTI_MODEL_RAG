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

export default function ActiveSource({ source, onChangeSource }: Props) {
  return (
    <section className="panel activeSource">
      <div>
        <span className="eyebrow">Active Source</span>
        {source ? (
          <>
            <h2>{source.filename}</h2>
            <p>{source.source_type.toUpperCase()} · {formatDuration(source.duration)}</p>
          </>
        ) : (
          <>
            <h2>No source selected</h2>
            <p>Upload or select a source to begin.</p>
          </>
        )}
      </div>
      <div className="statusBlock">
        <span className={`status ${source?.status ?? "uploaded"}`}>{source?.status === "ready" ? "Ready ✓" : source?.status ?? "None"}</span>
        <button onClick={onChangeSource}>Change Source</button>
      </div>
    </section>
  );
}

import { mediaUrl } from "../api/client";
import type { EvidenceEvent } from "../types/api";

function fmt(seconds: number | null): string {
  if (seconds == null) return "--:--";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

const MAX_DOCUMENT_CHARS = 700;

function clip(text: string): string {
  return text.length > MAX_DOCUMENT_CHARS ? `${text.slice(0, MAX_DOCUMENT_CHARS).trimEnd()}…` : text;
}

export default function EvidenceCard({ event }: { event: EvidenceEvent }) {
  const documents = event.documents ?? [];
  const graphExpanded = event.retrieval_path?.type === "graph_expansion";
  return (
    <article className="evidenceCard">
      <div className="cardHeader">
        <div>
          <h3>{event.title}</h3>
          <p>{fmt(event.start_time)} - {fmt(event.end_time)}</p>
        </div>
        <span className="score">
          {Math.round(event.score * 100)}% match{graphExpanded ? " · via graph" : ""}
        </span>
      </div>
      <div className="evidenceSections">
        {documents.length > 0 ? (
          <section>
            <h4>Document</h4>
            <div className="ocrList">
              {documents.map((doc, index) => (
                <p key={index}><time>{doc.page != null ? `p. ${doc.page}` : ""}</time>{clip(doc.text)}</p>
              ))}
            </div>
          </section>
        ) : (
          <section>
            <h4>Transcript</h4>
            <p>{event.transcript || "No transcript evidence."}</p>
          </section>
        )}
        <section>
          <h4>Raw OCR</h4>
          <div className="ocrList">
            {event.ocr.length ? event.ocr.map((item, index) => (
              <p key={index}><time>{fmt(item.timestamp)}</time>{item.text}</p>
            )) : <p>No OCR evidence.</p>}
          </div>
        </section>
        <section>
          <h4>Entities</h4>
          <div className="chips">
            {event.entities.length ? event.entities.map((entity) => <span key={entity}>{entity}</span>) : <span>None</span>}
          </div>
        </section>
      </div>
      {documents.length === 0 && <h4>Frames</h4>}
      {documents.length === 0 && <div className="frames">
        {event.frames.slice(0, 3).map((frame) => (
          <figure key={frame.observation_id}>
            <img src={mediaUrl(frame.observation_id)} alt={`Frame at ${frame.timestamp ?? "unknown"} seconds`} />
            <figcaption>{fmt(frame.timestamp)}</figcaption>
          </figure>
        ))}
        {event.frames.length === 0 && <p>No frame evidence.</p>}
      </div>}
    </article>
  );
}

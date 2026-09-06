import type { TimelineEvent } from "../types/api";

function fmt(seconds: number | null): string {
  if (seconds == null) return "--:--";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

export default function EventTimeline({ events, highlightedIds }: { events: TimelineEvent[]; highlightedIds: Set<string> }) {
  return (
    <section className="panel">
      <div className="sectionHeader">
        <div>
          <span className="eyebrow">Event Timeline</span>
          <h2>{events.length ? `${events.length} Events` : "No Events Yet"}</h2>
        </div>
        {highlightedIds.size > 0 && <span className="statusPill ready">{highlightedIds.size} cited</span>}
      </div>
      <div className="timeline">
        {events.length === 0 && <p className="muted">Select a ready source to see its event timeline.</p>}
        {events.map((event) => (
          <div key={event.id} className={`timelineItem ${highlightedIds.has(event.id) ? "highlight" : ""}`}>
            <time>{fmt(event.start_time)}</time>
            <div className="timelineBody">
              <strong>{event.title}</strong>
              {event.summary && <p>{event.summary}</p>}
              <div className="chips compactChips">
                {event.modalities.map((modality) => <span key={modality}>{modality}</span>)}
                {event.entities.slice(0, 4).map((entity) => <span key={entity}>{entity}</span>)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

import { useMemo, useState } from "react";
import type { TimelineEvent } from "../types/api";

function fmt(seconds: number | null): string {
  if (seconds == null) return "--:--";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

export default function EventTimeline({ events, highlightedIds }: { events: TimelineEvent[]; highlightedIds: Set<string> }) {
  const [mode, setMode] = useState<"all" | "cited">("all");
  const visibleEvents = useMemo(
    () => mode === "cited" ? events.filter((event) => highlightedIds.has(event.id)) : events,
    [events, highlightedIds, mode]
  );

  return (
    <section className="panel">
      <div className="sectionHeader">
        <div>
          <span className="eyebrow">Event Timeline</span>
          <h2>{events.length ? `${visibleEvents.length} ${mode === "cited" ? "Cited" : "Indexed"} Events` : "No Events Yet"}</h2>
        </div>
        {highlightedIds.size > 0 && (
          <div className="timelineControls">
            <button className={mode === "all" ? "active" : ""} onClick={() => setMode("all")}>All</button>
            <button className={mode === "cited" ? "active" : ""} onClick={() => setMode("cited")}>Cited {highlightedIds.size}</button>
          </div>
        )}
      </div>
      <div className="timeline">
        {events.length === 0 && <p className="muted">Select a ready source to see its event timeline.</p>}
        {events.length > 0 && visibleEvents.length === 0 && <p className="muted">No timeline events are cited by the current answer.</p>}
        {visibleEvents.map((event) => (
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

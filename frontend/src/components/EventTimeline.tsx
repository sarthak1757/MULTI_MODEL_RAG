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
      <span className="eyebrow">Event Timeline</span>
      <div className="timeline">
        {events.map((event) => (
          <div key={event.id} className={`timelineItem ${highlightedIds.has(event.id) ? "highlight" : ""}`}>
            <time>{fmt(event.start_time)}</time>
            <span>{event.title}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

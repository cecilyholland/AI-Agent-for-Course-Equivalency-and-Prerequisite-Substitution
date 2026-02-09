import "./AuditLogTimeline.css";

function formatTimestamp(timestamp) {
  return new Date(timestamp).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function getActorClass(actor) {
  switch (actor) {
    case "STUDENT":
      return "actor-student";
    case "AGENT":
      return "actor-agent";
    case "REVIEWER":
      return "actor-reviewer";
    default:
      return "";
  }
}

export default function AuditLogTimeline({ logs }) {
  if (logs.length === 0) {
    return (
      <section className="audit-log-timeline">
        <h3 className="audit-log-title">Activity Log</h3>
        <p className="audit-log-empty">No activity recorded yet.</p>
      </section>
    );
  }

  const sorted = [...logs].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  return (
    <section className="audit-log-timeline">
      <h3 className="audit-log-title">Activity Log</h3>
      <div className="timeline">
        {sorted.map((entry, index) => (
          <div className="timeline-entry" key={index}>
            <div className={`timeline-dot ${getActorClass(entry.actor)}`} />
            <div className="timeline-content">
              <span className="timeline-timestamp">
                {formatTimestamp(entry.timestamp)}
              </span>
              <span className={`timeline-actor-badge ${getActorClass(entry.actor)}`}>
                {entry.actor}
              </span>
              <span className="timeline-action">{entry.action}</span>
              <p className="timeline-message">{entry.message}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

import CitationBlock from "../components/CitationBlock";
import "./GapList.css";

function GapList({ gaps }) {
  if (gaps.length === 0) {
    return null;
  }

  return (
    <div className="gap-list">
      {gaps.map((gap, index) => (
        <div className="gap-item" key={index}>
          <span className={`gap-severity-badge gap-severity-badge--${gap.severity}`}>
            {gap.severity.replace("_", " ")}
          </span>
          <div className="gap-content">
            <p className="gap-text">{gap.text}</p>
            {gap.citations && gap.citations.length > 0 && (
              <div className="gap-citations">
                <CitationBlock citations={gap.citations} />
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default GapList;

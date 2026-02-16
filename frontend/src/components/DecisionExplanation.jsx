import CitationBlock from "../components/CitationBlock";
import GapList from "../components/GapList";
import "./DecisionExplanation.css";

function DecisionExplanation({
  reasons,
  gaps,
  bridgePlan,
  missingInfoRequests,
}) {
  return (
    <div className="decision-explanation">
      <div className="decision-explanation__section">
        <h3 className="decision-explanation__header">Reasons</h3>
        {reasons.map((reason, index) => (
          <div className="decision-explanation__reason" key={index}>
            <p className="decision-explanation__reason-text">{reason.text}</p>
            {reason.citations && reason.citations.length > 0 && (
              <div className="decision-explanation__reason-citations">
                <CitationBlock citations={reason.citations} />
              </div>
            )}
          </div>
        ))}
      </div>

      {gaps.length > 0 && (
        <div className="decision-explanation__section">
          <h3 className="decision-explanation__header">Identified Gaps</h3>
          <GapList gaps={gaps} />
        </div>
      )}

      {bridgePlan && bridgePlan.length > 0 && (
        <div className="decision-explanation__section">
          <h3 className="decision-explanation__header">Bridge Plan</h3>
          <ol className="decision-explanation__bridge-list">
            {bridgePlan.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        </div>
      )}

      {missingInfoRequests && missingInfoRequests.length > 0 && (
        <div className="decision-explanation__section">
          <div className="decision-explanation__missing-info">
            <h4 className="decision-explanation__missing-info-header">
              Additional Information Needed
            </h4>
            <ul className="decision-explanation__missing-info-list">
              {missingInfoRequests.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

export default DecisionExplanation;

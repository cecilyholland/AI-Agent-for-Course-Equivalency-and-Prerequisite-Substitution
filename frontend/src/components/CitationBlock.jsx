import "./CitationBlock.css";

function CitationBlock({ citations }) {
  if (citations.length === 0) {
    return null;
  }

  return (
    <div className="citation-block">
      {citations.map((citation, index) => (
        <div className="citation-block__item" key={index}>
          <div className="citation-block__meta">
            <span className="citation-block__doc-id">{citation.doc_id}</span>
            {citation.page != null && (
              <span className="citation-block__page">p. {citation.page}</span>
            )}
          </div>
          {citation.snippet && (
            <blockquote className="citation-block__snippet">
              {citation.snippet}
            </blockquote>
          )}
        </div>
      ))}
    </div>
  );
}

export default CitationBlock;

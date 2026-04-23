import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { fetchCommitteeCases, fetchCommitteeInfo } from "../services/api";
import { useAuth } from "../services/auth";
import StatusBadge from "../components/StatusBadge";
import "./ReviewerDashboard.css";
import "./CommitteeDashboard.css";

export default function CommitteeDashboard() {
  const { user } = useAuth();
  const [allCases, setAllCases] = useState([]);
  const [committeeMap, setCommitteeMap] = useState({});
  const [activeFilter, setActiveFilter] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchCommitteeCases(user.reviewerId)
      .then((cases) => {
        setAllCases(cases);
        return Promise.all(
          cases.map((c) =>
            fetchCommitteeInfo(c.id, user.reviewerId).then((info) => [c.id, info])
          )
        );
      })
      .then((entries) => {
        setCommitteeMap(Object.fromEntries(entries));
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const filteredCases = allCases.filter((c) => {
    const info = committeeMap[c.id];
    const myVote = info?.myVote;
    if (activeFilter === "NEEDS_VOTE") return !myVote;
    if (activeFilter === "VOTED") return !!myVote;
    return true;
  });

  if (loading) return <div className="reviewer-dashboard"><p>Loading...</p></div>;
  if (error) return <div className="reviewer-dashboard"><p>Error: {error}. Is the backend running?</p></div>;

  return (
    <div className="reviewer-dashboard">
      <h1>Committee Cases</h1>

      <div className="filter-bar">
        <button
          className={`filter-btn${activeFilter === "ALL" ? " filter-btn--active" : ""}`}
          onClick={() => setActiveFilter("ALL")}
        >
          All
        </button>
        <button
          className={`filter-btn${activeFilter === "NEEDS_VOTE" ? " filter-btn--active" : ""}`}
          onClick={() => setActiveFilter("NEEDS_VOTE")}
        >
          Needs My Vote
        </button>
        <button
          className={`filter-btn${activeFilter === "VOTED" ? " filter-btn--active" : ""}`}
          onClick={() => setActiveFilter("VOTED")}
        >
          Voted
        </button>
      </div>

      {filteredCases.length === 0 ? (
        <div className="no-cases-message">No cases match this filter.</div>
      ) : (
        <table className="cases-table">
          <thead>
            <tr>
              <th>Case ID</th>
              <th>Student Name</th>
              <th>Course Requested</th>
              <th>Status</th>
              <th>My Vote</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredCases.map((c) => {
              const info = committeeMap[c.id];
              const myVote = info?.myVote;
              return (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>{c.studentName}</td>
                  <td>{c.courseRequested}</td>
                  <td><StatusBadge status={c.status} /></td>
                  <td>
                    <span className={`committee-vote-badge${myVote ? " committee-vote-badge--voted" : " committee-vote-badge--pending"}`}>
                      {myVote ? "Voted" : "Pending"}
                    </span>
                  </td>
                  <td>
                    <Link to={`/reviewer/committee/case/${c.id}`} className="review-link">
                      Vote
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { fetchAllCases } from "../services/api";
import StatusBadge from "../components/StatusBadge";
import "./ReviewerDashboard.css";

const PENDING_STATUSES = ["REVIEW_PENDING", "AI_RECOMMENDATION"];

export default function ReviewerDashboard() {
  const [activeFilter, setActiveFilter] = useState("ALL");
  const [allCases, setAllCases] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAllCases().then((data) => {
      setAllCases(data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="reviewer-dashboard"><h1>Reviewer Dashboard</h1><p>Loading...</p></div>;

  const filteredCases = allCases.filter((c) => {
    if (activeFilter === "PENDING") {
      return PENDING_STATUSES.includes(c.status);
    }
    if (activeFilter === "REVIEWED") {
      return c.status === "REVIEWED";
    }
    return true;
  });

  return (
    <div className="reviewer-dashboard">
      <h1>Reviewer Dashboard</h1>

      <div className="filter-bar">
        <button
          className={`filter-btn${activeFilter === "ALL" ? " filter-btn--active" : ""}`}
          onClick={() => setActiveFilter("ALL")}
        >
          All Cases
        </button>
        <button
          className={`filter-btn${activeFilter === "PENDING" ? " filter-btn--active" : ""}`}
          onClick={() => setActiveFilter("PENDING")}
        >
          Pending Review
        </button>
        <button
          className={`filter-btn${activeFilter === "REVIEWED" ? " filter-btn--active" : ""}`}
          onClick={() => setActiveFilter("REVIEWED")}
        >
          Reviewed
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
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredCases.map((c) => (
              <tr key={c.id}>
                <td>{c.id}</td>
                <td>{c.studentName}</td>
                <td>{c.courseRequested}</td>
                <td>
                  <StatusBadge status={c.status} />
                </td>
                <td>
                  <Link to={`/reviewer/case/${c.id}`} className="review-link">
                    Review
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

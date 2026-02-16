import { Link, useParams } from "react-router-dom";
import { fetchStudentCases } from "../services/api";
import StatusBadge from "../components/StatusBadge";
import "./StudentDashboard.css";

export default function StudentDashboard() {
  const { studentId } = useParams();

  const cases = fetchStudentCases(studentId);

  return (
    <div className="student-dashboard">
      <div className="student-dashboard__header">
        <div>
          <h1 className="student-dashboard__title">My Cases</h1>
          <p className="student-dashboard__subtitle">
            Logged in as <strong>{studentId}</strong> &mdash; Track your course
            equivalency requests and their status.
          </p>
        </div>
        <Link
          to={`/student/${studentId}/new`}
          className="student-dashboard__new-btn"
        >
          + New Request
        </Link>
      </div>

      {cases.length === 0 ? (
        <div className="student-dashboard__empty">
          <p>You have no cases yet.</p>
          <Link to={`/student/${studentId}/new`}>
            Submit your first equivalency request
          </Link>
        </div>
      ) : (
        <div className="student-dashboard__list">
          {cases.map((c) => (
            <Link
              key={c.id}
              to={`/student/${studentId}/case/${c.id}`}
              className="student-dashboard__card"
            >
              <div className="student-dashboard__card-top">
                <span className="student-dashboard__card-id">{c.id}</span>
                <StatusBadge status={c.status} />
              </div>
              <h3 className="student-dashboard__card-course">
                {c.course_requested}
              </h3>
              <div className="student-dashboard__card-meta">
                <span>
                  {c.documents.length} document
                  {c.documents.length !== 1 && "s"}
                </span>
                <span>
                  Submitted{" "}
                  {new Date(c.documents[0]?.uploaded_at).toLocaleDateString()}
                </span>
              </div>
              {c.decision_result && (
                <div className="student-dashboard__card-decision">
                  <span
                    className={`student-dashboard__decision-tag student-dashboard__decision-tag--${c.decision_result.decision}`}
                  >
                    {c.decision_result.decision.replace(/_/g, " ")}
                  </span>
                  <span className="student-dashboard__score">
                    Score: {c.decision_result.equivalency_score}/100
                  </span>
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../services/auth";
import "./LoginPage.css";

const UTCID_REGEX = /^[a-zA-Z]{3}[0-9]{3}$/;

// hardcoded for now
const VALID_STUDENTS = ["alj001", "bom002", "cad003", "dak004"];
const VALID_REVIEWERS = ["rev001", "rev002"];

export default function LoginPage() {
  const navigate = useNavigate();
  const { loginAsStudent, loginAsReviewer } = useAuth();
  const [utcId, setUtcId] = useState("");
  const [role, setRole] = useState("student");
  const [error, setError] = useState("");

  const handleLogin = () => {
    const trimmed = utcId.trim().toLowerCase();
    if (!UTCID_REGEX.test(trimmed)) {
      setError("UTCID must be 3 letters followed by 3 numbers (e.g. yyc478).");
      return;
    }
    if (role === "student" && !VALID_STUDENTS.includes(trimmed)) {
      setError("Unrecognized student UTCID. Try: alj001, bom002, cad003, or dak004.");
      return;
    }
    if (role === "reviewer" && !VALID_REVIEWERS.includes(trimmed)) {
      setError("Unrecognized reviewer UTCID. Try: rev001 or rev002.");
      return;
    }
    setError("");
    if (role === "student") {
      loginAsStudent(trimmed);
      navigate(`/student/${trimmed}`);
    } else {
      loginAsReviewer(trimmed);
      navigate("/reviewer");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      handleLogin();
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-utc-header">
          <img src="/utc-logo.svg" alt="The University of Tennessee at Chattanooga" className="login-utc-logo" />
        </div>

        <h1 className="login-title">CourseEQ</h1>
        <p className="login-subtitle">
          AI-Powered Course Equivalency &amp; Prerequisite Substitution
        </p>

        <div className="login-role-toggle">
          <button
            className={`login-role-tab ${role === "student" ? "login-role-tab--active" : ""}`}
            onClick={() => setRole("student")}
          >
            Student
          </button>
          <button
            className={`login-role-tab ${role === "reviewer" ? "login-role-tab--active" : ""}`}
            onClick={() => setRole("reviewer")}
          >
            Reviewer
          </button>
        </div>

        <div className="login-form">
          <label className="login-label" htmlFor="utcid">
            UTCID: *
          </label>
          <input
            id="utcid"
            className="login-input"
            type="text"
            placeholder={role === "student" ? "e.g. alj001" : "e.g. rev001"}
            maxLength={6}
            value={utcId}
            onChange={(e) => {
              setUtcId(e.target.value);
              if (error) setError("");
            }}
            onKeyDown={handleKeyDown}
          />
          {error && <p className="login-error">{error}</p>}
          <p className="login-format-hint">* Indicates required fields</p>

          <button className="login-btn" onClick={handleLogin}>
            LOGIN
          </button>

          {role === "student" ? (
            <p className="login-demo-ids">
              Demo IDs: <code>alj001</code>, <code>bom002</code>,{" "}
              <code>cad003</code>, <code>dak004</code>
            </p>
          ) : (
            <p className="login-demo-ids">
              Demo IDs: <code>rev001</code>, <code>rev002</code>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

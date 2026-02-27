import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../services/auth";
import "./LoginPage.css";

export default function LoginPage() {
  const navigate = useNavigate();
  const { loginAsStudent, loginAsReviewer } = useAuth();
  const [utcId, setUtcId] = useState("");
  const [role, setRole] = useState("student");
  const [error, setError] = useState("");

  const handleLogin = (e) => {
    e.preventDefault();
    const trimmed = utcId.trim();
    if (!trimmed) {
      setError("Please enter your UTC ID.");
      return;
    }
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
      handleLogin(e);
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

        <form className="login-form" onSubmit={handleLogin}>
          <label className="login-label" htmlFor="utcid">
            UTCID: *
          </label>
          <input
            id="utcid"
            className="login-input"
            type="text"
            placeholder="Enter your UTC ID"
            value={utcId}
            onChange={(e) => {
              setUtcId(e.target.value);
              if (error) setError("");
            }}
            onKeyDown={handleKeyDown}
          />
          {error && <p className="login-error">{error}</p>}
          <p className="login-format-hint">* Indicates required fields</p>

          <button className="login-btn" type="submit">
            LOGIN
          </button>
        </form>
      </div>
    </div>
  );
}

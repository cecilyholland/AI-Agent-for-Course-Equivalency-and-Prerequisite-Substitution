import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../services/auth";
import { loginReviewer } from "../services/api";
import "./LoginPage.css";

export default function LoginPage() {
  const navigate = useNavigate();
  const { loginAsStudent, loginAsReviewer } = useAuth();
  const [utcId, setUtcId] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("student");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
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
      setLoading(true);
      try {
        const data = await loginReviewer(trimmed, password);
        // Admins can choose which dashboard via tab; non-admins are blocked from admin tab
        if (role === "admin" && data.role !== "admin") {
          setError("This account does not have admin access.");
          return;
        }
        // Admin users route based on selected tab (admin or reviewer)
        const effectiveRole = data.role === "admin" ? role : "reviewer";
        loginAsReviewer(data.utcId, data.reviewerId, effectiveRole);
        if (effectiveRole === "admin") navigate("/admin");
        else navigate("/reviewer");
      } catch (err) {
        setError(err.message === "Invalid credentials" ? "Invalid ID or password." : "Could not connect. Is the backend running?");
      } finally {
        setLoading(false);
      }
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
            onClick={() => { setRole("student"); setError(""); setPassword(""); }}
          >
            Student
          </button>
          <button
            className={`login-role-tab ${role === "reviewer" ? "login-role-tab--active" : ""}`}
            onClick={() => { setRole("reviewer"); setError(""); setPassword(""); }}
          >
            Reviewer
          </button>
          <button
            className={`login-role-tab ${role === "admin" ? "login-role-tab--active" : ""}`}
            onClick={() => { setRole("admin"); setError(""); setPassword(""); }}
          >
            Admin
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
            onChange={(e) => { setUtcId(e.target.value); if (error) setError(""); }}
          />

          {(role === "reviewer" || role === "admin") && (
            <>
              <label className="login-label" htmlFor="password" style={{ marginTop: "14px" }}>
                Password: *
              </label>
              <input
                id="password"
                className="login-input"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => { setPassword(e.target.value); if (error) setError(""); }}
              />
            </>
          )}

          {error && <p className="login-error">{error}</p>}
          <p className="login-format-hint">* Indicates required fields</p>

          <button className="login-btn" type="submit" disabled={loading}>
            {loading ? "Verifying..." : "LOGIN"}
          </button>
        </form>
      </div>
    </div>
  );
}

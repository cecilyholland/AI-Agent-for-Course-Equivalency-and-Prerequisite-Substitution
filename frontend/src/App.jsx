import { useState, useEffect } from "react";
import { Routes, Route, Link, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./services/auth";
import LoginPage from "./pages/LoginPage";
import StudentDashboard from "./pages/StudentDashboard";
import StudentCaseView from "./pages/StudentCaseView";
import StudentNewCase from "./pages/StudentNewCase";
import ReviewerDashboard from "./pages/ReviewerDashboard";
import ReviewerCaseReview from "./pages/ReviewerCaseReview";
import CommitteeDashboard from "./pages/CommitteeDashboard";
import CommitteeCaseReview from "./pages/CommitteeCaseReview";
import AdminDashboard from "./pages/AdminDashboard";
import "./App.css";

function RequireAuth({ role, children }) {
  const { user } = useAuth();
  const location = useLocation();

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  const allowed = Array.isArray(role) ? role : [role];
  if (role && !allowed.includes(user.role)) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function NavBar({ theme, toggleTheme }) {
  const { user, logout } = useAuth();

  return (
    <nav className="app-nav">
      <Link to="/" className="app-nav-brand">
        CourseEQ
      </Link>
      <div className="app-nav-links">
        {!user && <Link to="/login">Login</Link>}

        {user && user.role === "student" && (
          <Link to={`/student/${user.studentId}`}>My Cases</Link>
        )}

        {user && user.role === "reviewer" && (
          <>
            <Link to="/reviewer">Dashboard</Link>
            <Link to="/reviewer/committee">Committee Cases</Link>
          </>
        )}

        {user && user.role === "admin" && (
          <Link to="/admin">Admin Dashboard</Link>
        )}

        {user && (
          <>
            <span className="app-nav-user">
              {user.utcId}
            </span>
            <button className="app-nav-logout" onClick={logout}>
              Logout
            </button>
          </>
        )}

        <button
          className="app-nav-theme-toggle"
          onClick={toggleTheme}
          aria-label="Toggle dark mode"
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? "☀" : "☾"}
        </button>
      </div>
    </nav>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route path="/login" element={<LoginPage />} />

      {/* student routes */}
      <Route
        path="/student/:studentId"
        element={
          <RequireAuth role="student">
            <StudentDashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/student/:studentId/case/:id"
        element={
          <RequireAuth role="student">
            <StudentCaseView />
          </RequireAuth>
        }
      />
      <Route
        path="/student/:studentId/new"
        element={
          <RequireAuth role="student">
            <StudentNewCase />
          </RequireAuth>
        }
      />

      {/* reviewer routes */}
      <Route
        path="/reviewer"
        element={
          <RequireAuth role="reviewer">
            <ReviewerDashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/reviewer/case/:id"
        element={
          <RequireAuth role="reviewer">
            <ReviewerCaseReview />
          </RequireAuth>
        }
      />

      <Route
        path="/admin"
        element={
          <RequireAuth role="admin">
            <AdminDashboard />
          </RequireAuth>
        }
      />

      <Route
        path="/reviewer/committee"
        element={
          <RequireAuth role="reviewer">
            <CommitteeDashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/reviewer/committee/case/:id"
        element={
          <RequireAuth role="reviewer">
            <CommitteeCaseReview />
          </RequireAuth>
        }
      />

      <Route
        path="*"
        element={
          <div className="app-not-found">
            <h1>404 &mdash; Page not found</h1>
            <p>
              The page you are looking for does not exist.{" "}
              <Link to="/">Go back home</Link>.
            </p>
          </div>
        }
      />
    </Routes>
  );
}

export default function App() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("theme") || "light"
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme((t) => (t === "light" ? "dark" : "light"));

  return (
    <AuthProvider>
      <div className="app">
        <NavBar theme={theme} toggleTheme={toggleTheme} />
        <main className="app-main">
          <AppRoutes />
        </main>
      </div>
    </AuthProvider>
  );
}

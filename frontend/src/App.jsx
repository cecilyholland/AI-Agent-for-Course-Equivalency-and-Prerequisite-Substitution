import { Routes, Route, Link, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./services/auth";
import LoginPage from "./pages/LoginPage";
import StudentDashboard from "./pages/StudentDashboard";
import StudentCaseView from "./pages/StudentCaseView";
import StudentNewCase from "./pages/StudentNewCase";
import ReviewerDashboard from "./pages/ReviewerDashboard";
import ReviewerCaseReview from "./pages/ReviewerCaseReview";
import "./App.css";

function RequireAuth({ role, children }) {
  const { user } = useAuth();
  const location = useLocation();

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (role && user.role !== role) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function NavBar() {
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
          <Link to="/reviewer">Dashboard</Link>
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
  return (
    <AuthProvider>
      <div className="app">
        <NavBar />
        <main className="app-main">
          <AppRoutes />
        </main>
      </div>
    </AuthProvider>
  );
}

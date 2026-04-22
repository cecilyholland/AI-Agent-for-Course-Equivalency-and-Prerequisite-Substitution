import { createContext, useContext, useState } from "react";

const AuthContext = createContext(null);

const STORAGE_KEY = "courseq_user";

function loadUser() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveUser(user) {
  if (user) localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  else localStorage.removeItem(STORAGE_KEY);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(loadUser);

  const loginAsStudent = (utcId) => {
    const u = { role: "student", studentId: utcId, utcId };
    setUser(u);
    saveUser(u);
  };

  const loginAsReviewer = (utcId, reviewerId, role = "reviewer") => {
    const u = { role, studentId: null, utcId, reviewerId };
    setUser(u);
    saveUser(u);
  };

  const logout = () => {
    setUser(null);
    saveUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loginAsStudent, loginAsReviewer, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

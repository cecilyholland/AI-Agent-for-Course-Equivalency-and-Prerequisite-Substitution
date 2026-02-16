import { createContext, useContext, useState } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  const loginAsStudent = (utcId) => {
    setUser({ role: "student", studentId: utcId, utcId });
  };

  const loginAsReviewer = (utcId) => {
    setUser({ role: "reviewer", studentId: null, utcId });
  };

  const logout = () => {
    setUser(null);
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

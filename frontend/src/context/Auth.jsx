import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const Ctx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [company, setCompany] = useState(null);

  const refresh = useCallback(async () => {
    if (!localStorage.getItem("token")) return setUser(false);
    try {
      const { data } = await api.get("/auth/me");
      setUser(data.user);
      if (data.user.role === "super_admin") {
        if (localStorage.getItem("company_ctx")) {
          const c = await api.get("/company").catch(() => null);
          setCompany(c?.data || null);
        } else setCompany(null);
      } else setCompany(data.company);
    } catch {
      localStorage.removeItem("token");
      setUser(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("token", data.token);
    localStorage.removeItem("company_ctx");
    await refresh();
    return data.user;
  };
  const setToken = async (token) => { localStorage.setItem("token", token); await refresh(); };
  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("company_ctx");
    setUser(false);
    setCompany(null);
  };
  const enterCompany = async (id) => {
    if (id) localStorage.setItem("company_ctx", id);
    else localStorage.removeItem("company_ctx");
    await refresh();
  };
  const has = (mod) => (company?.enabled_modules || []).includes(mod);

  return (
    <Ctx.Provider value={{ user, company, login, logout, refresh, enterCompany, setToken, has }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);

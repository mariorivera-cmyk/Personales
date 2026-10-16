import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

const Ctx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [company, setCompany] = useState(null);
  const [setup, setSetup] = useState(null);

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
    } catch (e) {
      if (e.response?.status === 403) toast.error(e.response.data?.detail || "Acceso bloqueado", { id: "blocked" });
      localStorage.removeItem("token");
      setUser(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("token", data.token);
    localStorage.removeItem("company_ctx");
    setSetup(null);
    await refresh();
    return data.user;
  };
  const setToken = async (token) => { localStorage.setItem("token", token); await refresh(); };
  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("company_ctx");
    setUser(false);
    setCompany(null);
    setSetup(null);
  };
  const enterCompany = async (id) => {
    if (id) localStorage.setItem("company_ctx", id);
    else localStorage.removeItem("company_ctx");
    await refresh();
  };
  const checkSetup = useCallback(async () => {
    if (!company || company.setup_complete) return;
    const r = await api.get("/onboarding").catch(() => null);
    if (!r) return;
    setSetup(r.data);
    if (r.data.setup_complete) { toast.success("¡Su salón está configurado! Ya tiene acceso a todas las opciones.", { id: "setup-done" }); await refresh(); }
    else if (setup && setup.current !== r.data.current) toast.success("¡Paso completado! Ya puede continuar con el siguiente.", { id: `step-${r.data.current}` });
  }, [company, setup, refresh]);
  useEffect(() => { checkSetup(); }, [company?.id, company?.setup_complete]); // eslint-disable-line
  const has = (mod) => (company?.enabled_modules || []).includes(mod);

  return (
    <Ctx.Provider value={{ user, company, login, logout, refresh, enterCompany, setToken, has, checkSetup, setup }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);

import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const api = axios.create({ baseURL: API });

api.interceptors.request.use((c) => {
  const t = localStorage.getItem("token");
  if (t) c.headers.Authorization = `Bearer ${t}`;
  const cid = localStorage.getItem("company_ctx");
  if (cid) c.headers["X-Company-Id"] = cid;
  return c;
});

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (d == null) return e?.message || "Ocurrió un error";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  if (d.message) return d.message;
  return JSON.stringify(d);
}

export const money = (v, cur = "GTQ") =>
  `${cur === "USD" ? "$" : "Q"}${Number(v || 0).toLocaleString("es-GT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const STATUS = {
  pending: "Pendiente", confirmed: "Confirmada", in_progress: "En curso", completed: "Completada",
  cancelled: "Cancelada", no_show: "No asistió",
};
export const STATUS_CLS = {
  pending: "bg-amber-100 text-amber-800 border-amber-300",
  confirmed: "bg-emerald-100 text-emerald-800 border-emerald-300",
  in_progress: "bg-sky-100 text-sky-800 border-sky-300",
  completed: "bg-violet-100 text-violet-800 border-violet-300",
  cancelled: "bg-rose-100 text-rose-800 border-rose-300",
  no_show: "bg-slate-200 text-slate-700 border-slate-300",
};
export const CO_STATUS = {
  trial: "Prueba", active: "Activa", past_due: "Morosa", suspended_partial: "Suspensión parcial",
  suspended: "Suspendida", cancelled: "Cancelada",
};
export const CO_CLS = {
  trial: "bg-sky-100 text-sky-800", active: "bg-emerald-100 text-emerald-800", past_due: "bg-amber-100 text-amber-800",
  suspended_partial: "bg-orange-100 text-orange-800", suspended: "bg-rose-100 text-rose-800", cancelled: "bg-slate-200 text-slate-700",
};
export const ROLES = {
  super_admin: "Super Administrador", company_admin: "Administrador de Empresa", branch_manager: "Gerente de Sucursal",
  receptionist: "Recepcionista", stylist: "Estilista",
};
export const DAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
export const todayStr = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/Guatemala" });
export const addDays = (d, n) => {
  const x = new Date(d + "T12:00:00");
  x.setDate(x.getDate() + n);
  return x.toISOString().slice(0, 10);
};

export async function download(path, filename) {
  const res = await api.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

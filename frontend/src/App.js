import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/Auth";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Signup from "@/pages/SignupSimple";
import PublicBooking from "@/pages/portal/Portal";
import ReviewPage from "@/pages/portal/ReviewPage";
import { CashClose, Commissions } from "@/pages/CashCommissions";
import { Inventory, ReviewsGallery } from "@/pages/InventoryReviews";
import Dashboard from "@/pages/Dashboard";
import Agenda from "@/pages/Agenda";
import Clients from "@/pages/Clients";
import ClientDetail from "@/pages/ClientDetail";
import WhatsApp from "@/pages/WhatsApp";
import { Services, Branches, Stylists, Blocks, Waitlist, UpsellRules } from "@/pages/Resources";
import Loyalty from "@/pages/Loyalty";
import Marketing from "@/pages/Marketing";
import Reports from "@/pages/Reports";
import CompanySettings from "@/pages/CompanySettings";
import Billing from "@/pages/Billing";
import AdminDashboard from "@/pages/admin/AdminDashboard";
import AdminCompanies from "@/pages/admin/AdminCompanies";
import AdminCatalog from "@/pages/admin/AdminCatalog";
import AdminPayments from "@/pages/admin/AdminPayments";

function Home() {
  const { user, company } = useAuth();
  if (user === null) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "super_admin" && !company) return <Navigate to="/admin" replace />;
  if (user.role === "stylist") return <Navigate to="/app/agenda" replace />;
  return <Navigate to="/app" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/b/:slug" element={<PublicBooking />} />
          <Route path="/b/:slug/resena/:token" element={<ReviewPage />} />
          <Route element={<Layout />}>
            <Route path="/app" element={<Dashboard />} />
            <Route path="/app/agenda" element={<Agenda />} />
            <Route path="/app/clientes" element={<Clients />} />
            <Route path="/app/clientes/:id" element={<ClientDetail />} />
            <Route path="/app/whatsapp" element={<WhatsApp />} />
            <Route path="/app/espera" element={<Waitlist />} />
            <Route path="/app/servicios" element={<Services />} />
            <Route path="/app/sucursales" element={<Branches />} />
            <Route path="/app/estilistas" element={<Stylists />} />
            <Route path="/app/bloqueos" element={<Blocks />} />
            <Route path="/app/fidelizacion" element={<Loyalty />} />
            <Route path="/app/ventas" element={<UpsellRules />} />
            <Route path="/app/marketing" element={<Marketing />} />
            <Route path="/app/reportes" element={<Reports />} />
            <Route path="/app/config" element={<CompanySettings />} />
            <Route path="/app/facturacion" element={<Billing />} />
            <Route path="/app/caja" element={<CashClose />} />
            <Route path="/app/comisiones" element={<Commissions />} />
            <Route path="/app/inventario" element={<Inventory />} />
            <Route path="/app/resenas" element={<ReviewsGallery />} />
            <Route path="/admin" element={<AdminDashboard />} />
            <Route path="/admin/empresas" element={<AdminCompanies />} />
            <Route path="/admin/catalogo" element={<AdminCatalog />} />
            <Route path="/admin/pagos" element={<AdminPayments />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster richColors position="top-right" />
    </AuthProvider>
  );
}

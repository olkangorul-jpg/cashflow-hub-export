import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import ProtectedRoute from "@/components/ProtectedRoute";
import AppLayout from "@/components/AppLayout";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import Dashboard from "@/pages/Dashboard";
import BankAccounts from "@/pages/BankAccounts";
import Checks from "@/pages/Checks";
import PromissoryNotes from "@/pages/PromissoryNotes";
import Expenses from "@/pages/Expenses";
import Incomes from "@/pages/Incomes";
import UpcomingPayments from "@/pages/UpcomingPayments";
import Settings from "@/pages/Settings";
import Team from "@/pages/Team";
import TaxReport from "@/pages/TaxReport";
import Backups from "@/pages/Backups";

function AppRouter() {
  const location = useLocation();
  // Handle OAuth redirect before ProtectedRoute runs
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/upcoming" element={<UpcomingPayments />} />
        <Route path="/bank-accounts" element={<BankAccounts />} />
        <Route path="/checks" element={<Checks />} />
        <Route path="/notes" element={<PromissoryNotes />} />
        <Route path="/expenses" element={<Expenses />} />
        <Route path="/incomes" element={<Incomes />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/team" element={<Team />} />
        <Route path="/tax-report" element={<TaxReport />} />
        <Route path="/backups" element={<Backups />} />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <AppRouter />
          <Toaster position="top-right" richColors />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;

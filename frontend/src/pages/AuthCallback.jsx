import { useEffect, useRef } from "react";
import { api } from "@/lib/api";

export default function AuthCallback() {
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) {
      window.location.replace("/login");
      return;
    }
    const session_id = match[1];

    (async () => {
      try {
        await api.post("/auth/session", { session_id });
        // Full page reload so AuthContext re-mounts with fresh cookie state
        window.location.replace("/dashboard");
      } catch (e) {
        window.location.replace("/login");
      }
    })();
  }, []);

  return (
    <div className="min-h-screen bg-[#F8F9FA] flex items-center justify-center">
      <div className="text-center">
        <div className="h-8 w-8 border-2 border-slate-300 border-t-slate-900 rounded-full animate-spin mx-auto" />
        <p className="mt-4 text-sm text-slate-600 font-body">Giriş yapılıyor...</p>
      </div>
    </div>
  );
}

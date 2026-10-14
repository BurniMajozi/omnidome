"use client";
import HomeDome from "@/components/home-dome";
import { technicianApi } from "@/lib/api/client";
import { useAuthStore } from "@/lib/stores/auth-store";
const request = (path: string, init?: RequestInit) => technicianApi.homeDomeRequest(path, init);
export default function HomeDomeWorkspace() {
  const token = useAuthStore(state => state.accessToken);
  if (!token) return <p className="p-4 text-sm text-slate-300">Sign in to request customer HomeDome access.</p>;
  return <HomeDome key={token} request={request} />;
}

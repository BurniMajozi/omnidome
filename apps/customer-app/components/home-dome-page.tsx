"use client";
import HomeDome from "@/components/home-dome";
import { api } from "@/lib/api/client";
import { useAuthStore } from "@/lib/stores/auth-store";

const request = (path: string, init?: RequestInit) => api.homeDomeRequest(path, init);
export default function HomeDomePage() {
  const token = useAuthStore(state => state.accessToken);
  if (!token) return <div className="p-6"><h1 className="text-2xl font-semibold">HomeDome</h1><p className="mt-3">Sign in with your verified customer account to view your home.</p><a className="mt-3 inline-block underline" href="/login">Sign in</a></div>;
  return <div className="space-y-4 p-4"><p className="rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">HomeDome is part of your OmniDome customer app. Your rooms, devices and energy readings come from your connected home gateway. Use Advanced home settings for pairing devices; manage your home and support access here.</p><HomeDome key={token} request={request} /></div>;
}

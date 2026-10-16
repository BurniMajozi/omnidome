"use client";
import HomeDome from "@/components/home-dome";
import { api } from "@/lib/api/client";
import { useAuthStore } from "@/lib/stores/auth-store";

const request = (path: string, init?: RequestInit) => api.homeDomeRequest(path, init);
export default function HomeDomePage() {
  const token = useAuthStore(state => state.accessToken);
  if (!token) return <div className="p-6"><h1 className="text-2xl font-semibold">HomeDome</h1><p className="mt-3">Sign in with your verified customer account to view your home.</p><a className="mt-3 inline-block underline" href="/login">Sign in</a></div>;
  return <div className="space-y-4 p-4"><p className="rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">HomeDome is part of your OmniDome customer app. Your rooms, devices and energy readings come from your home gateway, which runs inside OmniDome. Activate it, add cameras and other devices, and manage support access right here: there is nothing else to open or sign in to.</p><HomeDome key={token} request={request} /></div>;
}

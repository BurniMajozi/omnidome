"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Wifi, Eye, EyeOff, Loader2 } from "lucide-react";
import { useAuthStore } from "@/lib/stores/auth-store";
import { api } from "@/lib/api/client";
import brandConfig from "@/config/brand.json";

export default function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");

  const handlePasswordReset = async () => {
    setError(""); setNotice("");
    if (!email.trim()) { setError("Enter your invited email address first."); return; }
    setLoading(true);
    try {
      await api.requestPasswordReset(email);
      setNotice("If this address has an account, check its inbox for password reset instructions. Then return here to sign in.");
    } catch (err) { setError(err instanceof Error ? err.message : "Password reset failed"); }
    finally { setLoading(false); }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);
    try {
      await useAuthStore.getState().login(email, password);
      const res = useAuthStore.getState();
      // ApiClient.login() returns camelCase tokens (accessToken/refreshToken)
      const accessMaxAge = 3600;
      document.cookie = `access_token=${res.accessToken}; path=/; max-age=${accessMaxAge}`;
      document.cookie = `refresh_token=${res.refreshToken}; path=/; max-age=2592000`;
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-sm">
      <div className="text-center mb-8">
        <Link href="/" className="inline-flex items-center gap-2 mb-4">
          <Wifi size={32} className="text-blue-600" />
          <span className="text-2xl font-bold">{brandConfig.appName}</span>
        </Link>
        <h1 className="text-xl font-semibold">Welcome back</h1>
        <p className="text-sm text-gray-500 mt-1">Sign in to your account</p>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-6 space-y-4 shadow-sm">
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-600">{error}</div>
        )}
        {notice && <p role="status" className="rounded-lg bg-blue-50 p-3 text-sm text-blue-700">{notice}</p>}

        <div>
          <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">Email</label>
          <input id="email" type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2.5 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="you@example.com" />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">Password</label>
          <div className="relative">
            <input id="password" type={showPassword ? "text" : "password"} required autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2.5 pr-10 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="••••••••" />
            <button type="button" onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>

        <button type="submit" disabled={loading}
          className="w-full py-2.5 rounded-lg bg-blue-600 text-white font-medium text-sm hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
          {loading && <Loader2 size={16} className="animate-spin" />}
          {loading ? "Signing in..." : "Sign in"}
        </button>

        <button type="button" disabled={loading} onClick={() => void handlePasswordReset()} className="w-full text-center text-sm font-medium text-blue-600 hover:underline">Forgot password?</button>
        <p className="text-center text-sm text-gray-500">Your ISP provides your customer account. Your Home Assistant account is separate.</p>
      </form>
    </div>
  );
}

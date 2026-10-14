"use client";
import Link from "next/link";

export default function SupportError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <section className="m-6 rounded-xl border bg-white p-6" role="alert">
    <h1 className="text-xl font-semibold">Support could not load</h1>
    <p className="my-3 text-gray-600">Your customer account is still available. Retry support or return to your home.</p>
    <button className="rounded-lg bg-blue-600 px-4 py-2 text-white" onClick={reset}>Retry support</button>
    <Link className="ml-4 text-blue-600 underline" href="/home">Return to HomeDome</Link>
  </section>;
}

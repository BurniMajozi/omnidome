import Link from "next/link";
import { ThemeToggle } from "@/components/ui/theme-toggle";

export default function TermsOfService() {
  return (
    <>
      <header className="w-full border-b border-border bg-background/80 sticky top-0 z-30 backdrop-blur flex items-center justify-between px-4 sm:px-8 py-4">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2 group">
            <img src="/logo-new.svg" alt="OmniDome Logo" className="h-10 w-10" />
            <span className="font-bold text-xl text-foreground group-hover:text-primary transition-colors">OmniDome</span>
          </Link>
        </div>
        <div className="flex items-center gap-4">
          <ThemeToggle />
          <Link href="/" className="ml-2 px-4 py-2 rounded-md bg-primary text-primary-foreground font-semibold shadow hover:bg-primary/90 transition-all">Back Home</Link>
        </div>
      </header>
      <main className="max-w-3xl mx-auto py-20 px-4 sm:px-6 lg:px-8 text-foreground">
        <h1 className="text-4xl font-black mb-6">Terms of Service</h1>
        <p className="mb-6 text-lg text-muted-foreground">Last updated: 25 January 2026</p>
        <p className="mb-6">These Terms of Service (&quot;Terms&quot;) govern your use of the OmniDome platform and services. By accessing or using our services, you agree to be bound by these Terms and all applicable laws of South Africa.</p>
        <h2 className="text-2xl font-bold mt-10 mb-4">1. Use of Services</h2>
        <ul className="list-disc pl-6 mb-6">
          <li>You must be at least 18 years old to use our services.</li>
          <li>You agree to use our services only for lawful purposes and in accordance with these Terms.</li>
        </ul>
        <h2 className="text-2xl font-bold mt-10 mb-4">2. User Accounts</h2>
        <ul className="list-disc pl-6 mb-6">
          <li>You are responsible for maintaining the confidentiality of your account credentials.</li>
          <li>You agree to notify us immediately of any unauthorized use of your account.</li>
        </ul>
        <h2 className="text-2xl font-bold mt-10 mb-4">3. Intellectual Property</h2>
        <ul className="list-disc pl-6 mb-6">
          <li>All content, trademarks, and technology on the OmniDome platform are owned by us or our licensors.</li>
          <li>You may not copy, modify, or distribute any part of our services without our written consent.</li>
        </ul>
        <h2 className="text-2xl font-bold mt-10 mb-4">4. Termination</h2>
        <ul className="list-disc pl-6 mb-6">
          <li>We may suspend or terminate your access to our services at any time for violation of these Terms or applicable law.</li>
        </ul>
        <h2 className="text-2xl font-bold mt-10 mb-4">5. Disclaimers & Limitation of Liability</h2>
        <ul className="list-disc pl-6 mb-6">
          <li>Our services are provided &quot;as is&quot; without warranties of any kind.</li>
          <li>We are not liable for any indirect, incidental, or consequential damages arising from your use of our services.</li>
        </ul>
        <h2 className="text-2xl font-bold mt-10 mb-4">6. Governing Law</h2>
        <p className="mb-6">These Terms are governed by the laws of South Africa. Any disputes will be resolved in the courts of South Africa.</p>
        <h2 className="text-2xl font-bold mt-10 mb-4">7. Changes to Terms</h2>
        <p className="mb-6">We may update these Terms from time to time. Continued use of our services constitutes acceptance of the revised Terms.</p>
        <h2 className="text-2xl font-bold mt-10 mb-4">8. Contact Us</h2>
        <p>If you have any questions about these Terms, contact us at <a href="mailto:legal@omnidome.co.za" className="text-primary underline">legal@omnidome.co.za</a>.</p>
      </main>
    </>
  );
}

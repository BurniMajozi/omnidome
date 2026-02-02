
import Link from "next/link";
import { ThemeToggle } from "@/components/ui/theme-toggle";

export default function PrivacyPolicy() {
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
        <h1 className="text-4xl font-black mb-6">Privacy Policy</h1>
        <p className="mb-6 text-lg text-muted-foreground">Last updated: 25 January 2026</p>
        <p className="mb-6">This Privacy Policy describes how OmniDome ("we", "us", or "our") collects, uses, discloses, and protects your information when you use our products and services in South Africa. We are committed to safeguarding your privacy and ensuring that your personal information is protected in accordance with the Protection of Personal Information Act (POPIA) and other applicable South African laws.</p>

      <h2 className="text-2xl font-bold mt-10 mb-4">1. Information We Collect</h2>
      <ul className="list-disc pl-6 mb-6">
        <li><b>Personal Information:</b> Name, contact details, company information, and other identifiers you provide when registering or using our services.</li>
        <li><b>Usage Data:</b> Information about how you interact with our platform, including log data, device information, and IP address.</li>
        <li><b>Cookies & Tracking:</b> We use cookies and similar technologies to enhance your experience and analyze usage.</li>
      </ul>

      <h2 className="text-2xl font-bold mt-10 mb-4">2. How We Use Your Information</h2>
      <ul className="list-disc pl-6 mb-6">
        <li>To provide, operate, and maintain our products and services.</li>
        <li>To communicate with you regarding updates, support, and marketing (with your consent).</li>
        <li>To improve and personalize your experience.</li>
        <li>To comply with legal obligations and protect our rights.</li>
      </ul>

      <h2 className="text-2xl font-bold mt-10 mb-4">3. Sharing Your Information</h2>
      <ul className="list-disc pl-6 mb-6">
        <li>We do not sell your personal information.</li>
        <li>We may share your information with trusted third-party service providers who assist us in delivering our services, subject to strict confidentiality agreements.</li>
        <li>We may disclose information if required by law or to protect our legal rights.</li>
      </ul>

      <h2 className="text-2xl font-bold mt-10 mb-4">4. Data Security</h2>
      <p className="mb-6">We implement appropriate technical and organizational measures to protect your personal information from unauthorized access, loss, or misuse. However, no system is completely secure, and we cannot guarantee absolute security.</p>

      <h2 className="text-2xl font-bold mt-10 mb-4">5. Your Rights</h2>
      <ul className="list-disc pl-6 mb-6">
        <li>You have the right to access, correct, or delete your personal information held by us.</li>
        <li>You may object to or restrict certain processing of your data.</li>
        <li>You may withdraw your consent for marketing communications at any time.</li>
        <li>To exercise your rights, contact us at <a href="mailto:privacy@omnidome.co.za" className="text-primary underline">privacy@omnidome.co.za</a>.</li>
      </ul>

      <h2 className="text-2xl font-bold mt-10 mb-4">6. International Data Transfers</h2>
      <p className="mb-6">If we transfer your personal information outside South Africa, we will ensure adequate protection in line with POPIA and other applicable laws.</p>

      <h2 className="text-2xl font-bold mt-10 mb-4">7. Children's Privacy</h2>
      <p className="mb-6">Our services are not intended for children under 18. We do not knowingly collect personal information from children.</p>

      <h2 className="text-2xl font-bold mt-10 mb-4">8. Changes to This Policy</h2>
      <p className="mb-6">We may update this Privacy Policy from time to time. We will notify you of any significant changes by posting the new policy on our website.</p>

      <h2 className="text-2xl font-bold mt-10 mb-4">9. Contact Us</h2>
      <p>If you have any questions or concerns about this Privacy Policy or our data practices, please contact us at <a href="mailto:privacy@omnidome.co.za" className="text-primary underline">privacy@omnidome.co.za</a>.</p>
      </main>
    </>
  );
}

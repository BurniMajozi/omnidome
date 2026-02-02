import Link from "next/link";
import { ThemeToggle } from "@/components/ui/theme-toggle";

export default function PoPIACompliance() {
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
        <h1 className="text-4xl font-black mb-6">POPIA Compliance</h1>
        <p className="mb-6 text-lg text-muted-foreground">Last updated: 25 January 2026</p>
        <p className="mb-6">OmniDome is committed to protecting your personal information in accordance with the Protection of Personal Information Act (POPIA) of South Africa. This page outlines our approach to POPIA compliance and your rights as a data subject.</p>
        <h2 className="text-2xl font-bold mt-10 mb-4">1. Lawful Processing</h2>
        <ul className="list-disc pl-6 mb-6">
          <li>We only collect and process personal information for legitimate business purposes and with your consent where required.</li>
        </ul>
        <h2 className="text-2xl font-bold mt-10 mb-4">2. Data Subject Rights</h2>
        <ul className="list-disc pl-6 mb-6">
          <li>You have the right to access, correct, or delete your personal information held by us.</li>
          <li>You may object to or restrict certain processing of your data.</li>
          <li>You may withdraw your consent for marketing communications at any time.</li>
        </ul>
        <h2 className="text-2xl font-bold mt-10 mb-4">3. Security Safeguards</h2>
        <ul className="list-disc pl-6 mb-6">
          <li>We implement appropriate technical and organizational measures to protect your data from unauthorized access, loss, or misuse.</li>
        </ul>
        <h2 className="text-2xl font-bold mt-10 mb-4">4. Information Officer</h2>
        <p className="mb-6">Our appointed Information Officer oversees POPIA compliance. Contact: <a href="mailto:privacy@omnidome.co.za" className="text-primary underline">privacy@omnidome.co.za</a></p>
        <h2 className="text-2xl font-bold mt-10 mb-4">5. Complaints</h2>
        <p className="mb-6">If you believe your data rights have been infringed, you may lodge a complaint with the Information Regulator (South Africa): <a href="https://www.justice.gov.za/inforeg/" className="text-primary underline" target="_blank" rel="noopener noreferrer">justice.gov.za/inforeg</a></p>
        <h2 className="text-2xl font-bold mt-10 mb-4">6. Updates</h2>
        <p className="mb-6">We may update this POPIA Compliance page as our practices evolve or as required by law.</p>
      </main>
    </>
  );
}

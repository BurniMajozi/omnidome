"use client";

/**
 * /assistant → /support redirect.
 *
 * The assistant page is now merged into the support page.
 * This file redirects any direct links to /assistant.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AssistantRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/support"); }, [router]);
  return null;
}

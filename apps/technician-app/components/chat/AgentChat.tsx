"use client";

/**
 * Technician app — AgentChat wrapper.
 * Injects auth from the technician auth store and delegates to the
 * shared @omnidome/agent-chat package. Dark theme by default.
 */

import { AgentChat as BaseAgentChat, type AgentChatProps } from "@omnidome/agent-chat";
import { useAuthStore } from "@/lib/stores/auth-store";

export function AgentChat(props: Omit<AgentChatProps, "auth" | "target" | "theme">) {
  const accessToken = useAuthStore((s) => s.accessToken ?? undefined);

  return (
    <BaseAgentChat
      theme="dark"
      target="mobile"
      auth={{ accessToken }}
      {...props}
    />
  );
}

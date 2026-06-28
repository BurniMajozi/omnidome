"use client";

/**
 * Customer app — AgentChat wrapper.
 *
 * Thin wrapper around @omnidome/agent-chat that:
 *  - Uses the light theme
 *  - Injects customer context from the auth store
 *  - Upgrades to AG-UI streaming (the customer portal previously used sync invoke)
 *
 * Note: The customer auth store keeps the JWT inside the ApiClient singleton
 * rather than in Zustand state. A follow-up task should expose `accessToken`
 * in AuthState so it can be forwarded here via auth={{ accessToken }}.
 * For now, the orchestrator uses tenant context from the request body.
 */

import { AgentChat as BaseAgentChat, type AgentChatProps } from "@omnidome/agent-chat";
import { useAuthStore } from "@/lib/stores/auth-store";

export function AgentChat(props: Omit<AgentChatProps, "target" | "theme">) {
  const { customer, accessToken } = useAuthStore((s) => ({
    customer: s.customer,
    accessToken: s.accessToken,
  }));

  return (
    <BaseAgentChat
      theme="light"
      target="mobile"
      auth={{ accessToken: accessToken ?? undefined }}
      context={{
        customer_id: customer?.id ?? "",
        account_number: (customer as Record<string, unknown>)?.accountNumber ?? "",
      }}
      {...props}
    />
  );
}

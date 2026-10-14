"use client";

/**
 * Customer app — AgentChat wrapper.
 *
 * Thin wrapper around @omnidome/agent-chat that:
 *  - Uses the light theme
 *  - Injects customer context from the auth store
 *  - Upgrades to AG-UI streaming (the customer portal previously used sync invoke)
 *
 * Customer identity is verified by the same-origin support proxy; browser
 * context never determines which customer's records the agent may access.
 */

import { AgentChat as BaseAgentChat, type AgentChatProps } from "@omnidome/agent-chat";
import { useAuthStore } from "@/lib/stores/auth-store";

export function AgentChat(props: Omit<AgentChatProps, "target" | "theme">) {
  const customer = useAuthStore(s => s.customer);
  const accessToken = useAuthStore(s => s.accessToken);

  return (
    <BaseAgentChat
      theme="light"
      target="web"
      auth={{ accessToken: accessToken ?? undefined }}
      context={{
        customer_id: customer?.id ?? "",
        account_number: customer?.accountNumber ?? "",
      }}
      {...props}
    />
  );
}

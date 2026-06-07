"use client";

import { useAuthStore } from "@/lib/stores/auth-store";
import { AgentChat } from "@/components/chat/AgentChat";

export default function AssistantPage() {
  const customer = useAuthStore((s) => s.customer);

  return (
    <div className="h-[calc(100vh-3.5rem)] lg:h-[calc(100vh-3.5rem)]">
      <AgentChat
        initialAgent="customer_facing"
        theme="light"
        context={{
          customer_id: customer?.id || "",
          account_number: customer?.accountNumber || "",
        }}
      />
    </div>
  );
}

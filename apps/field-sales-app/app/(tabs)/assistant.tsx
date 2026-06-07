"use client";

import { AgentChat } from "@/components/chat/AgentChat";

export default function AssistantPage() {
  return (
    <div className="h-full">
      <AgentChat
        initialAgent="provisioning"
        theme="dark"
        context={{
          source: "field-sales-app",
        }}
      />
    </div>
  );
}

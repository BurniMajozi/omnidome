"use client";

import { AgentChat } from "@/components/chat/AgentChat";

export default function AssistantPage() {
  return (
    <div className="h-full">
      <AgentChat
        initialAgent="support"
        context={{
          source: "technician-app",
        }}
      />
    </div>
  );
}

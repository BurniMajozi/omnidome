"use client"

// Entry point used by ag-ui-chat.tsx. Logic lives in lib/agent-activity.ts; UI in ./activity/*.
import { ActivityPanel } from "@/components/chat/activity/activity-panel"
import { QuestionCard } from "@/components/chat/activity/question-card"
import { ApprovalCard } from "@/components/chat/activity/approval-card"
import { reduceActivity, type Activity } from "@/lib/agent-activity"

export { emptyActivity, finishActivity, type Activity } from "@/lib/agent-activity"

/** Fold a CUSTOM stream event into the activity (unknown events are ignored). */
export function activityEvent(activity: Activity, name: unknown, value: unknown): Activity {
  return reduceActivity(activity, name, value)
}

export function AgentActivity({ activity, streaming }: { activity: Activity; streaming: boolean }) {
  const hasContent = streaming || activity.hasCustom
  if (!hasContent) return null
  return (
    <div className="mb-2 space-y-2">
      <ActivityPanel activity={activity} streaming={streaming} />
      {activity.questions.map((q) => <QuestionCard key={q.question_id} question={q} streaming={streaming} />)}
      {activity.approvals.map((a) => <ApprovalCard key={a.approval_id} approval={a} streaming={streaming} />)}
    </div>
  )
}

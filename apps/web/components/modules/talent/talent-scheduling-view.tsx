"use client"

import React from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { NoDataYet } from "@/components/ui/not-connected"
import { Calendar, Users } from "lucide-react"
import type { Employee, Schedule } from "@/lib/hr-api"

interface TalentSchedulingViewProps {
  employees: Employee[]
  schedules: Schedule[]
  onRefresh: () => void
}

/**
 * Roster of REAL schedule rows. There is no demand curve here: hourly
 * required/scheduled headcount has no connected source, so none is drawn.
 */
export function TalentSchedulingView({ employees, schedules }: TalentSchedulingViewProps) {
  const nameById = new Map(employees.map((e) => [e.id, e.full_name]))
  return (
    <div className="space-y-6">
      <Card className="border-border">
        <CardHeader className="pb-3 border-b border-border/60">
          <CardTitle className="text-base flex items-center gap-2">
            <Calendar className="h-4 w-4 text-cyan-400" />
            Hourly Demand
          </CardTitle>
          <CardDescription className="text-xs">Required vs scheduled headcount per hour.</CardDescription>
        </CardHeader>
        <CardContent className="p-4">
          <NoDataYet message="Not connected: no hourly demand source is available, so no demand curve is shown." />
        </CardContent>
      </Card>

      <Card className="border-border">
        <CardHeader className="pb-3 border-b border-border/60">
          <CardTitle className="text-base flex items-center gap-2">
            <Users className="h-4 w-4 text-emerald-400" />
            Scheduled Shifts
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {schedules.length === 0 ? (
            <div className="p-4">
              <NoDataYet message="No shifts scheduled yet." />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                    <th className="py-2.5 px-4 font-medium">Employee</th>
                    <th className="py-2.5 px-4 font-medium">Department</th>
                    <th className="py-2.5 px-4 font-medium">Date</th>
                    <th className="py-2.5 px-4 font-medium">Shift</th>
                    <th className="py-2.5 px-4 font-medium text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {schedules.map((s) => (
                    <tr key={s.id} className="hover:bg-muted/30">
                      <td className="py-3 px-4 font-semibold text-foreground">{nameById.get(s.employee_id) ?? "Unknown employee"}</td>
                      <td className="py-3 px-4 text-muted-foreground">{s.department}</td>
                      <td className="py-3 px-4 text-muted-foreground">{s.schedule_date}</td>
                      <td className="py-3 px-4 font-mono text-foreground">
                        {s.shift_start} - {s.shift_end}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <Badge variant="outline" className="border-primary/40 text-primary">
                          {s.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

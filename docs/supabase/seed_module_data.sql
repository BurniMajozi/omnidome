-- Seed module_data with default dashboard/module data.
-- Run after schema.sql in Supabase SQL editor.

insert into module_data (module_id, data)
values (
  'sales',
  $$
  {
    "salesData": [
      { "month": "Jan", "revenue": 450000, "deals": 12 },
      { "month": "Feb", "revenue": 520000, "deals": 15 },
      { "month": "Mar", "revenue": 480000, "deals": 14 },
      { "month": "Apr", "revenue": 610000, "deals": 18 },
      { "month": "May", "revenue": 580000, "deals": 16 },
      { "month": "Jun", "revenue": 720000, "deals": 21 }
    ],
    "pipelineData": [
      { "name": "Prospecting", "value": 45, "fill": "#4ade80" },
      { "name": "Negotiation", "value": 35, "fill": "#60a5fa" },
      { "name": "Closed Won", "value": 20, "fill": "#a855f7" }
    ],
    "topProducts": [
      { "name": "Business Fiber", "value": 42 },
      { "name": "Home Broadband", "value": 28 },
      { "name": "VoIP Bundle", "value": 18 },
      { "name": "Cloud Services", "value": 12 }
    ],
    "flashcardKPIs": [
      {
        "id": "1",
        "title": "Monthly Revenue",
        "value": "R 2,840,000",
        "change": "+18.5%",
        "changeType": "positive",
        "iconKey": "revenue",
        "backTitle": "Revenue Breakdown",
        "backDetails": [
          { "label": "New Business", "value": "R 1,420,000" },
          { "label": "Renewals", "value": "R 980,000" },
          { "label": "Upsells", "value": "R 440,000" }
        ],
        "backInsight": "New business revenue up 24% this quarter"
      },
      {
        "id": "2",
        "title": "Total Deals",
        "value": "47",
        "change": "+12.2%",
        "changeType": "positive",
        "iconKey": "deals",
        "backTitle": "Deal Analysis",
        "backDetails": [
          { "label": "Won", "value": "32" },
          { "label": "Lost", "value": "8" },
          { "label": "Pending", "value": "7" }
        ],
        "backInsight": "Win rate improved to 80% from 72%"
      },
      {
        "id": "3",
        "title": "Pipeline Value",
        "value": "R 18,000,000",
        "change": "+8.3%",
        "changeType": "positive",
        "iconKey": "pipeline",
        "backTitle": "Pipeline Stages",
        "backDetails": [
          { "label": "Prospecting", "value": "R 8,100,000" },
          { "label": "Negotiation", "value": "R 6,300,000" },
          { "label": "Closing", "value": "R 3,600,000" }
        ],
        "backInsight": "45% of pipeline in late stages"
      },
      {
        "id": "4",
        "title": "Avg Deal Size",
        "value": "R 384,000",
        "change": "+5.1%",
        "changeType": "positive",
        "iconKey": "avgDeal",
        "backTitle": "Deal Size Distribution",
        "backDetails": [
          { "label": "Enterprise", "value": "R 850,000" },
          { "label": "SMB", "value": "R 280,000" },
          { "label": "Residential", "value": "R 45,000" }
        ],
        "backInsight": "Enterprise deals growing fastest at 32%"
      }
    ],
    "activities": [
      { "id": "1", "user": "John Smith", "action": "closed deal with", "target": "Telkom SA", "time": "2 minutes ago", "type": "create" },
      { "id": "2", "user": "Sarah Jones", "action": "updated proposal for", "target": "MTN Group", "time": "15 minutes ago", "type": "update" },
      { "id": "3", "user": "Mike Brown", "action": "scheduled meeting with", "target": "Vodacom", "time": "1 hour ago", "type": "create" },
      { "id": "4", "user": "Lisa Chen", "action": "sent contract to", "target": "Dimension Data", "time": "2 hours ago", "type": "create" },
      { "id": "5", "user": "David Wilson", "action": "added notes to", "target": "Cell C deal", "time": "3 hours ago", "type": "comment" }
    ],
    "issues": [
      { "id": "1", "title": "Quote approval delayed for MTN deal", "severity": "high", "status": "open", "assignee": "Sarah Jones", "time": "2 hours ago" },
      { "id": "2", "title": "Pricing discrepancy in Vodacom proposal", "severity": "medium", "status": "in-progress", "assignee": "Mike Brown", "time": "4 hours ago" },
      { "id": "3", "title": "Contract terms need legal review", "severity": "high", "status": "open", "assignee": "John Smith", "time": "Yesterday" },
      { "id": "4", "title": "Customer credit check pending", "severity": "low", "status": "resolved", "assignee": "Lisa Chen", "time": "2 days ago" }
    ],
    "summary": "This month's sales performance shows strong growth with R2.84M in revenue, an 18.5% increase from last month. The team closed 47 deals with an average deal size of R384K. The pipeline is healthy at R18M with 45% of opportunities in late stages. Key wins include contracts with Telkom SA and Dimension Data. Focus areas for next month include improving conversion rates in the negotiation stage and expanding enterprise segment penetration.",
    "tasks": [
      { "id": "1", "title": "Follow up on MTN proposal", "priority": "urgent", "status": "todo", "dueDate": "Today", "assignee": "Sarah Jones" },
      { "id": "2", "title": "Prepare Q2 sales forecast", "priority": "high", "status": "in-progress", "dueDate": "Tomorrow", "assignee": "John Smith" },
      { "id": "3", "title": "Update CRM with new leads", "priority": "normal", "status": "todo", "dueDate": "This week", "assignee": "Mike Brown" },
      { "id": "4", "title": "Complete sales training module", "priority": "low", "status": "done", "dueDate": "Completed", "assignee": "Lisa Chen" }
    ],
    "aiRecommendations": [
      { "id": "1", "title": "Prioritize Vodacom Deal", "description": "Based on engagement patterns, Vodacom is 85% likely to close this week. Schedule a final call.", "impact": "high", "category": "Sales" },
      { "id": "2", "title": "Upsell Opportunity", "description": "3 existing customers show interest in VoIP bundles based on usage patterns.", "impact": "medium", "category": "Upsell" },
      { "id": "3", "title": "At-Risk Deal Alert", "description": "Cell C deal has been stagnant for 2 weeks. Consider offering incentive.", "impact": "high", "category": "Risk" },
      { "id": "4", "title": "Optimize Pricing", "description": "Competitors reduced fiber pricing by 8%. Review pricing strategy.", "impact": "medium", "category": "Strategy" }
    ],
    "tableData": [
      { "id": "1", "deal": "Telkom SA - Fiber Upgrade", "value": "R 850,000", "stage": "Closed Won", "probability": "100%", "closeDate": "2024-01-10", "owner": "John Smith" },
      { "id": "2", "deal": "MTN Group - Enterprise Package", "value": "R 1,200,000", "stage": "Negotiation", "probability": "75%", "closeDate": "2024-01-20", "owner": "Sarah Jones" },
      { "id": "3", "deal": "Vodacom - Data Center", "value": "R 2,400,000", "stage": "Proposal", "probability": "60%", "closeDate": "2024-02-01", "owner": "Mike Brown" },
      { "id": "4", "deal": "Dimension Data - Cloud", "value": "R 680,000", "stage": "Closed Won", "probability": "100%", "closeDate": "2024-01-08", "owner": "Lisa Chen" },
      { "id": "5", "deal": "Cell C - Network Services", "value": "R 450,000", "stage": "Discovery", "probability": "30%", "closeDate": "2024-02-15", "owner": "David Wilson" }
    ],
    "tableColumns": [
      { "key": "deal", "label": "Deal Name" },
      { "key": "value", "label": "Value" },
      { "key": "stage", "label": "Stage" },
      { "key": "probability", "label": "Probability" },
      { "key": "closeDate", "label": "Close Date" },
      { "key": "owner", "label": "Owner" }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'crm',
  $$
  {
    "customerData": [
      { "month": "Jan", "customers": 10200, "churn": 45 },
      { "month": "Feb", "customers": 10850, "churn": 38 },
      { "month": "Mar", "customers": 11200, "churn": 42 },
      { "month": "Apr", "customers": 11950, "churn": 35 },
      { "month": "May", "customers": 12400, "churn": 32 },
      { "month": "Jun", "customers": 12847, "churn": 28 }
    ],
    "leadData": [
      { "week": "Week 1", "leads": 85, "converted": 12 },
      { "week": "Week 2", "leads": 92, "converted": 16 },
      { "week": "Week 3", "leads": 78, "converted": 11 },
      { "week": "Week 4", "leads": 105, "converted": 18 }
    ],
    "flashcardKPIs": [
      {
        "id": "1",
        "title": "Total Customers",
        "value": "12,847",
        "change": "+5.2%",
        "changeType": "positive",
        "iconKey": "customers",
        "backTitle": "Customer Segments",
        "backDetails": [
          { "label": "Enterprise", "value": "1,245" },
          { "label": "SMB", "value": "4,892" },
          { "label": "Residential", "value": "6,710" }
        ],
        "backInsight": "Enterprise segment growing 15% faster"
      },
      {
        "id": "2",
        "title": "Active Leads",
        "value": "342",
        "change": "+14.8%",
        "changeType": "positive",
        "iconKey": "leads",
        "backTitle": "Lead Sources",
        "backDetails": [
          { "label": "Website", "value": "142" },
          { "label": "Referrals", "value": "98" },
          { "label": "Field Sales", "value": "102" }
        ],
        "backInsight": "Referrals have highest conversion at 32%"
      },
      {
        "id": "3",
        "title": "Conversion Rate",
        "value": "15.7%",
        "change": "+2.3%",
        "changeType": "positive",
        "iconKey": "conversion",
        "backTitle": "Conversion by Channel",
        "backDetails": [
          { "label": "Direct Sales", "value": "24.5%" },
          { "label": "Online", "value": "12.8%" },
          { "label": "Partners", "value": "18.2%" }
        ],
        "backInsight": "Direct sales conversion up 5% this month"
      },
      {
        "id": "4",
        "title": "Customer Lifetime Value",
        "value": "R 42,500",
        "change": "+8.9%",
        "changeType": "positive",
        "iconKey": "clv",
        "backTitle": "CLV by Segment",
        "backDetails": [
          { "label": "Enterprise", "value": "R 185,000" },
          { "label": "SMB", "value": "R 48,000" },
          { "label": "Residential", "value": "R 12,500" }
        ],
        "backInsight": "Enterprise CLV increased 12% YoY"
      }
    ],
    "activities": [
      { "id": "1", "user": "Emily Davis", "action": "converted lead", "target": "Acme Corp", "time": "5 minutes ago", "type": "create" },
      { "id": "2", "user": "James Wilson", "action": "updated profile for", "target": "John Doe", "time": "20 minutes ago", "type": "update" },
      { "id": "3", "user": "Maria Garcia", "action": "logged call with", "target": "Tech Solutions", "time": "1 hour ago", "type": "comment" },
      { "id": "4", "user": "Robert Lee", "action": "assigned lead to", "target": "Sales Team A", "time": "2 hours ago", "type": "assign" },
      { "id": "5", "user": "Anna Kim", "action": "sent campaign to", "target": "Q1 Prospects", "time": "3 hours ago", "type": "create" }
    ],
    "issues": [
      { "id": "1", "title": "Duplicate customer records detected", "severity": "high", "status": "open", "assignee": "Emily Davis", "time": "1 hour ago" },
      { "id": "2", "title": "Email bounce rate increased", "severity": "medium", "status": "in-progress", "assignee": "James Wilson", "time": "3 hours ago" },
      { "id": "3", "title": "Customer data sync failed", "severity": "critical", "status": "open", "assignee": "IT Support", "time": "4 hours ago" },
      { "id": "4", "title": "Lead scoring model needs update", "severity": "low", "status": "resolved", "assignee": "Maria Garcia", "time": "Yesterday" }
    ],
    "summary": "Customer base has grown to 12,847 with a healthy 5.2% increase this month. The churn rate has decreased to 2.1%, our lowest in 6 months. Lead generation is strong with 342 active leads and a 15.7% conversion rate. The enterprise segment shows the highest growth potential with 15% faster acquisition. Customer satisfaction scores remain high at 4.6/5, with residential customers showing the most improvement. Focus areas include reducing duplicate records and improving email deliverability.",
    "tasks": [
      { "id": "1", "title": "Clean up duplicate records", "priority": "urgent", "status": "in-progress", "dueDate": "Today", "assignee": "Emily Davis" },
      { "id": "2", "title": "Update customer segmentation", "priority": "high", "status": "todo", "dueDate": "Tomorrow", "assignee": "James Wilson" },
      { "id": "3", "title": "Review lead scoring criteria", "priority": "normal", "status": "todo", "dueDate": "This week", "assignee": "Maria Garcia" },
      { "id": "4", "title": "Send Q1 customer survey", "priority": "normal", "status": "done", "dueDate": "Completed", "assignee": "Anna Kim" }
    ],
    "aiRecommendations": [
      { "id": "1", "title": "High Churn Risk Alert", "description": "15 enterprise customers show reduced engagement. Initiate retention campaigns.", "impact": "high", "category": "Retention" },
      { "id": "2", "title": "Upsell Opportunity", "description": "87 SMB customers match enterprise upgrade criteria based on usage.", "impact": "high", "category": "Growth" },
      { "id": "3", "title": "Lead Prioritization", "description": "Focus on website leads this week - they show 40% higher intent signals.", "impact": "medium", "category": "Sales" },
      { "id": "4", "title": "Data Quality", "description": "Run deduplication process - estimated 3% duplicate rate affecting metrics.", "impact": "medium", "category": "Operations" }
    ],
    "tableData": [
      { "id": "1", "customer": "Telkom SA", "type": "Enterprise", "status": "Active", "revenue": "R 2,400,000", "since": "2019-03-15", "health": "Excellent" },
      { "id": "2", "customer": "MTN Group", "type": "Enterprise", "status": "Active", "revenue": "R 1,850,000", "since": "2020-06-22", "health": "Good" },
      { "id": "3", "customer": "Shoprite Holdings", "type": "Enterprise", "status": "Active", "revenue": "R 980,000", "since": "2021-01-10", "health": "At Risk" },
      { "id": "4", "customer": "Pick n Pay", "type": "SMB", "status": "Active", "revenue": "R 450,000", "since": "2022-04-18", "health": "Good" },
      { "id": "5", "customer": "Woolworths", "type": "Enterprise", "status": "Active", "revenue": "R 1,200,000", "since": "2020-11-05", "health": "Excellent" }
    ],
    "tableColumns": [
      { "key": "customer", "label": "Customer Name" },
      { "key": "type", "label": "Type" },
      { "key": "status", "label": "Status" },
      { "key": "revenue", "label": "Annual Revenue" },
      { "key": "since", "label": "Customer Since" },
      { "key": "health", "label": "Health Score" }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'service',
  $$
  {
    "ticketTrend": [
      { "day": "Mon", "open": 28, "resolved": 32 },
      { "day": "Tue", "open": 35, "resolved": 28 },
      { "day": "Wed", "open": 42, "resolved": 35 },
      { "day": "Thu", "open": 38, "resolved": 40 },
      { "day": "Fri", "open": 28, "resolved": 45 },
      { "day": "Sat", "open": 15, "resolved": 18 },
      { "day": "Sun", "open": 12, "resolved": 14 }
    ],
    "ticketsByPriority": [
      { "name": "Critical", "value": 8, "fill": "#ef4444" },
      { "name": "High", "value": 32, "fill": "#f97316" },
      { "name": "Medium", "value": 52, "fill": "#eab308" },
      { "name": "Low", "value": 36, "fill": "#4ade80" }
    ],
    "resolutionTime": [
      { "priority": "Critical", "time": 1.2 },
      { "priority": "High", "time": 2.8 },
      { "priority": "Medium", "time": 4.5 },
      { "priority": "Low", "time": 8.3 }
    ],
    "flashcardKPIs": [
      {
        "id": "1",
        "title": "Open Tickets",
        "value": "128",
        "change": "-24%",
        "changeType": "positive",
        "iconKey": "open",
        "backTitle": "Ticket Breakdown",
        "backDetails": [
          { "label": "Critical", "value": "8" },
          { "label": "High", "value": "32" },
          { "label": "Medium/Low", "value": "88" }
        ],
        "backInsight": "Critical tickets down 40% from last week"
      },
      {
        "id": "2",
        "title": "Avg Resolution Time",
        "value": "4.2h",
        "change": "-15%",
        "changeType": "positive",
        "iconKey": "resolution",
        "backTitle": "Resolution by Priority",
        "backDetails": [
          { "label": "Critical", "value": "1.2h" },
          { "label": "High", "value": "2.8h" },
          { "label": "Medium/Low", "value": "6.4h" }
        ],
        "backInsight": "SLA compliance at 98.5%"
      },
      {
        "id": "3",
        "title": "CSAT Score",
        "value": "4.6/5",
        "change": "+0.3",
        "changeType": "positive",
        "iconKey": "csat",
        "backTitle": "Satisfaction Breakdown",
        "backDetails": [
          { "label": "5 Stars", "value": "68%" },
          { "label": "4 Stars", "value": "24%" },
          { "label": "1-3 Stars", "value": "8%" }
        ],
        "backInsight": "Highest score in 12 months"
      },
      {
        "id": "4",
        "title": "SLA Compliance",
        "value": "98.5%",
        "change": "+1.2%",
        "changeType": "positive",
        "iconKey": "sla",
        "backTitle": "SLA by Category",
        "backDetails": [
          { "label": "Response Time", "value": "99.2%" },
          { "label": "Resolution Time", "value": "97.8%" },
          { "label": "First Contact", "value": "98.5%" }
        ],
        "backInsight": "Only 2 SLA breaches this month"
      }
    ],
    "activities": [
      { "id": "1", "user": "Tech Support", "action": "resolved ticket", "target": "TKT-4521", "time": "3 minutes ago", "type": "update" },
      { "id": "2", "user": "John Nkosi", "action": "escalated ticket", "target": "TKT-4518", "time": "15 minutes ago", "type": "assign" },
      { "id": "3", "user": "Sarah Mbeki", "action": "updated status of", "target": "TKT-4515", "time": "30 minutes ago", "type": "update" },
      { "id": "4", "user": "Field Team", "action": "dispatched for", "target": "TKT-4512", "time": "1 hour ago", "type": "create" },
      { "id": "5", "user": "Customer", "action": "rated service", "target": "5 stars", "time": "2 hours ago", "type": "comment" }
    ],
    "issues": [
      { "id": "1", "title": "Network outage in Johannesburg North", "severity": "critical", "status": "in-progress", "assignee": "Network Team", "time": "30 min ago" },
      { "id": "2", "title": "Billing system slow response", "severity": "high", "status": "open", "assignee": "IT Support", "time": "1 hour ago" },
      { "id": "3", "title": "Customer portal login issues", "severity": "medium", "status": "in-progress", "assignee": "Dev Team", "time": "2 hours ago" },
      { "id": "4", "title": "Email notifications delayed", "severity": "low", "status": "resolved", "assignee": "IT Support", "time": "Yesterday" }
    ],
    "summary": "Service desk performance is strong with 128 open tickets, down 24% from last week. Average resolution time improved to 4.2 hours, a 15% reduction. CSAT score reached 4.6/5, our highest in 12 months. SLA compliance is at 98.5% with only 2 breaches this month. The team resolved 212 tickets this week, with the network outage in Johannesburg North being the most significant ongoing issue. Focus areas include reducing critical ticket volume and maintaining the improved resolution times.",
    "tasks": [
      { "id": "1", "title": "Resolve Johannesburg network outage", "priority": "urgent", "status": "in-progress", "dueDate": "Today", "assignee": "Network Team" },
      { "id": "2", "title": "Update knowledge base articles", "priority": "high", "status": "todo", "dueDate": "Tomorrow", "assignee": "Sarah Mbeki" },
      { "id": "3", "title": "Review escalation procedures", "priority": "normal", "status": "todo", "dueDate": "This week", "assignee": "John Nkosi" },
      { "id": "4", "title": "Complete Q1 service report", "priority": "normal", "status": "done", "dueDate": "Completed", "assignee": "Manager" }
    ],
    "aiRecommendations": [
      { "id": "1", "title": "Pattern Detected", "description": "20% of tickets relate to router firmware. Consider proactive firmware update campaign.", "impact": "high", "category": "Prevention" },
      { "id": "2", "title": "Resource Optimization", "description": "Tuesday/Wednesday have 40% more tickets. Adjust staffing accordingly.", "impact": "medium", "category": "Staffing" },
      { "id": "3", "title": "Knowledge Gap", "description": "VoIP setup queries increased 60%. Create video tutorial for self-service.", "impact": "medium", "category": "Self-Service" },
      { "id": "4", "title": "Escalation Alert", "description": "3 tickets approaching SLA breach in next 2 hours. Prioritize immediately.", "impact": "high", "category": "SLA" }
    ],
    "tableData": [
      { "id": "1", "ticket": "TKT-4521", "customer": "Thabo Mokoena", "issue": "No internet connection", "priority": "High", "status": "Resolved", "created": "2024-01-12", "agent": "Tech Support" },
      { "id": "2", "ticket": "TKT-4520", "customer": "Sipho Ndlovu", "issue": "Slow speeds", "priority": "Medium", "status": "In Progress", "created": "2024-01-12", "agent": "Sarah Mbeki" },
      { "id": "3", "ticket": "TKT-4519", "customer": "Nomvula Dlamini", "issue": "Billing query", "priority": "Low", "status": "Open", "created": "2024-01-12", "agent": "Unassigned" },
      { "id": "4", "ticket": "TKT-4518", "customer": "Johan van der Merwe", "issue": "VoIP not working", "priority": "Critical", "status": "Escalated", "created": "2024-01-12", "agent": "John Nkosi" },
      { "id": "5", "ticket": "TKT-4517", "customer": "Lerato Molefe", "issue": "Router replacement", "priority": "Medium", "status": "Pending", "created": "2024-01-11", "agent": "Field Team" }
    ],
    "tableColumns": [
      { "key": "ticket", "label": "Ticket ID" },
      { "key": "customer", "label": "Customer" },
      { "key": "issue", "label": "Issue" },
      { "key": "priority", "label": "Priority" },
      { "key": "status", "label": "Status" },
      { "key": "created", "label": "Created" },
      { "key": "agent", "label": "Agent" }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'retention',
  $$
  {
    "churnTrendData": [
      { "month": "Jul", "churnRate": 3.2, "predictions": 3.5, "retained": 96.8 },
      { "month": "Aug", "churnRate": 2.9, "predictions": 3.1, "retained": 97.1 },
      { "month": "Sep", "churnRate": 3.1, "predictions": 2.9, "retained": 96.9 },
      { "month": "Oct", "churnRate": 2.7, "predictions": 2.8, "retained": 97.3 },
      { "month": "Nov", "churnRate": 2.4, "predictions": 2.5, "retained": 97.6 },
      { "month": "Dec", "churnRate": 2.1, "predictions": 2.2, "retained": 97.9 }
    ],
    "churnRiskSegments": [
      { "name": "High Risk", "value": 847, "fill": "#ef4444" },
      { "name": "Medium Risk", "value": 2134, "fill": "#f97316" },
      { "name": "Low Risk", "value": 8521, "fill": "#eab308" },
      { "name": "Loyal", "value": 13345, "fill": "#4ade80" }
    ],
    "churnReasons": [
      { "reason": "Price Sensitivity", "count": 342, "percentage": 32 },
      { "reason": "Service Issues", "count": 267, "percentage": 25 },
      { "reason": "Competitor Offers", "count": 192, "percentage": 18 },
      { "reason": "Relocation", "count": 139, "percentage": 13 },
      { "reason": "No Longer Needed", "count": 128, "percentage": 12 }
    ],
    "clvBySegment": [
      { "segment": "Enterprise", "clv": 48500, "retentionRate": 94.2 },
      { "segment": "Business", "clv": 24800, "retentionRate": 91.5 },
      { "segment": "Premium", "clv": 12400, "retentionRate": 88.7 },
      { "segment": "Standard", "clv": 6200, "retentionRate": 85.3 },
      { "segment": "Basic", "clv": 2400, "retentionRate": 79.8 }
    ],
    "campaignPerformance": [
      { "campaign": "Win-Back Email", "saved": 142, "cost": 2840, "roi": 312 },
      { "campaign": "Loyalty Discount", "saved": 89, "cost": 8900, "roi": 156 },
      { "campaign": "Personal Outreach", "saved": 67, "cost": 3350, "roi": 248 },
      { "campaign": "Upgrade Offer", "saved": 45, "cost": 1800, "roi": 412 }
    ],
    "flashcardKPIs": [
      {
        "id": "1",
        "title": "Monthly Churn Rate",
        "value": "2.1%",
        "change": "-0.3%",
        "changeType": "positive",
        "iconKey": "churn",
        "backTitle": "Churn Breakdown",
        "backDetails": [
          { "label": "Voluntary Churn", "value": "1.4%" },
          { "label": "Involuntary Churn", "value": "0.7%" },
          { "label": "Target", "value": "< 2.5%" }
        ],
        "backInsight": "Lowest churn rate in 18 months"
      },
      {
        "id": "2",
        "title": "At-Risk Customers",
        "value": "847",
        "change": "-12%",
        "changeType": "positive",
        "iconKey": "risk",
        "backTitle": "Risk Distribution",
        "backDetails": [
          { "label": "Critical (90%+)", "value": "124" },
          { "label": "High (70-89%)", "value": "298" },
          { "label": "Elevated (50-69%)", "value": "425" }
        ],
        "backInsight": "AI model 87% accurate on predictions"
      },
      {
        "id": "3",
        "title": "Retention Rate",
        "value": "97.9%",
        "change": "+0.3%",
        "changeType": "positive",
        "iconKey": "retention",
        "backTitle": "Retention by Tenure",
        "backDetails": [
          { "label": "0-6 months", "value": "92.4%" },
          { "label": "6-24 months", "value": "96.8%" },
          { "label": "24+ months", "value": "99.2%" }
        ],
        "backInsight": "Long-term customers most stable"
      },
      {
        "id": "4",
        "title": "Customers Saved",
        "value": "343",
        "change": "+28%",
        "changeType": "positive",
        "iconKey": "saved",
        "backTitle": "Save Methods",
        "backDetails": [
          { "label": "Discount Offers", "value": "142" },
          { "label": "Service Recovery", "value": "108" },
          { "label": "Personal Outreach", "value": "93" }
        ],
        "backInsight": "R 2.1M revenue preserved this month"
      }
    ],
    "activities": [
      { "id": "1", "user": "AI System", "action": "flagged high-risk customer", "target": "ACC-78421", "time": "5 minutes ago", "type": "assign" },
      { "id": "2", "user": "Retention Team", "action": "saved customer with", "target": "loyalty discount", "time": "22 minutes ago", "type": "update" },
      { "id": "3", "user": "Win-Back Campaign", "action": "re-activated", "target": "12 customers", "time": "1 hour ago", "type": "create" },
      { "id": "4", "user": "Thabo Ndlovu", "action": "completed outreach for", "target": "ACC-65892", "time": "2 hours ago", "type": "comment" },
      { "id": "5", "user": "Churn Model", "action": "updated predictions for", "target": "2,847 accounts", "time": "3 hours ago", "type": "update" }
    ],
    "issues": [
      { "id": "1", "title": "124 customers with 90%+ churn probability", "severity": "critical", "status": "in-progress", "assignee": "Retention Team", "time": "Active" },
      { "id": "2", "title": "Spike in service-related churn in Cape Town", "severity": "high", "status": "open", "assignee": "Regional Manager", "time": "2 hours ago" },
      { "id": "3", "title": "Competitor campaign detected - MTN promo", "severity": "high", "status": "in-progress", "assignee": "Marketing", "time": "Yesterday" },
      { "id": "4", "title": "Win-back email campaign below target", "severity": "medium", "status": "open", "assignee": "Campaign Manager", "time": "2 days ago" }
    ],
    "summary": "Retention performance shows strong improvement with the monthly churn rate dropping to 2.1%, the lowest in 18 months. The AI-powered churn prediction model has identified 847 at-risk customers with 87% prediction accuracy. This month, the retention team saved 343 customers, preserving R 2.1M in annual revenue. Key focus areas: 124 customers are in critical risk zone (90%+ churn probability), a service-related churn spike was detected in Cape Town requiring immediate attention, and competitor MTN is running an aggressive promotional campaign that may impact retention in budget segments.",
    "tasks": [
      { "id": "1", "title": "Contact 124 critical-risk customers", "priority": "urgent", "status": "in-progress", "dueDate": "Today", "assignee": "Retention Team" },
      { "id": "2", "title": "Launch counter-offer for MTN campaign", "priority": "high", "status": "todo", "dueDate": "Tomorrow", "assignee": "Marketing" },
      { "id": "3", "title": "Investigate Cape Town service issues", "priority": "high", "status": "in-progress", "dueDate": "Today", "assignee": "Service Manager" },
      { "id": "4", "title": "Update churn prediction model", "priority": "normal", "status": "todo", "dueDate": "This week", "assignee": "Data Science" }
    ],
    "aiRecommendations": [
      { "id": "1", "title": "Proactive Outreach Required", "description": "48 customers show declining usage patterns similar to previous churners. Initiate engagement now.", "impact": "high", "category": "Prevention" },
      { "id": "2", "title": "Price Sensitivity Cluster", "description": "215 customers comparing competitors. Consider targeted retention offer with 15% discount.", "impact": "high", "category": "Pricing" },
      { "id": "3", "title": "Service Recovery Opportunity", "description": "67 customers had recent negative support experiences. Personal apology call recommended.", "impact": "medium", "category": "Recovery" },
      { "id": "4", "title": "Loyalty Program Gap", "description": "Long-term customers (3+ years) showing signs of disengagement. Launch appreciation campaign.", "impact": "medium", "category": "Loyalty" }
    ],
    "tableData": [
      { "id": "1", "account": "ACC-78421", "customer": "Lerato Mbeki", "segment": "Premium", "riskScore": "94%", "tenure": "8 months", "reason": "Service Issues", "status": "Contacted", "lastAction": "Today" },
      { "id": "2", "account": "ACC-65892", "customer": "Johan Pretorius", "segment": "Business", "riskScore": "87%", "tenure": "14 months", "reason": "Price Sensitive", "status": "Offer Sent", "lastAction": "Yesterday" },
      { "id": "3", "account": "ACC-91234", "customer": "Nomvula Dlamini", "segment": "Standard", "riskScore": "82%", "tenure": "3 months", "reason": "Competitor Offer", "status": "Pending", "lastAction": "2 days ago" },
      { "id": "4", "account": "ACC-45678", "customer": "David Smith", "segment": "Enterprise", "riskScore": "76%", "tenure": "26 months", "reason": "Service Issues", "status": "Escalated", "lastAction": "Today" },
      { "id": "5", "account": "ACC-23456", "customer": "Sipho Nkosi", "segment": "Premium", "riskScore": "71%", "tenure": "11 months", "reason": "No Engagement", "status": "Scheduled", "lastAction": "Tomorrow" }
    ],
    "tableColumns": [
      { "key": "account", "label": "Account" },
      { "key": "customer", "label": "Customer" },
      { "key": "segment", "label": "Segment" },
      { "key": "riskScore", "label": "Risk Score" },
      { "key": "tenure", "label": "Tenure" },
      { "key": "reason", "label": "Risk Reason" },
      { "key": "status", "label": "Status" },
      { "key": "lastAction", "label": "Last Action" }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'network',
  $$
  {
    "networkMetrics": [
      { "time": "00:00", "bandwidth": 65, "latency": 2.1 },
      { "time": "04:00", "bandwidth": 52, "latency": 1.8 },
      { "time": "08:00", "bandwidth": 78, "latency": 2.4 },
      { "time": "12:00", "bandwidth": 88, "latency": 2.8 },
      { "time": "16:00", "bandwidth": 92, "latency": 3.2 },
      { "time": "20:00", "bandwidth": 85, "latency": 2.9 },
      { "time": "24:00", "bandwidth": 70, "latency": 2.3 }
    ],
    "nodeStatus": [
      { "node": "North Zone", "status": 287, "utilization": 72 },
      { "node": "South Zone", "status": 264, "utilization": 68 },
      { "node": "East Zone", "status": 298, "utilization": 75 },
      { "node": "West Zone", "status": 271, "utilization": 70 },
      { "node": "Central Hub", "status": 127, "utilization": 82 }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'call-center',
  $$
  {
    "callData": [
      { "hour": "08:00", "inbound": 45, "outbound": 32 },
      { "hour": "10:00", "inbound": 52, "outbound": 38 },
      { "hour": "12:00", "inbound": 68, "outbound": 42 },
      { "hour": "14:00", "inbound": 75, "outbound": 45 },
      { "hour": "16:00", "inbound": 58, "outbound": 40 },
      { "hour": "18:00", "inbound": 42, "outbound": 28 }
    ],
    "agentPerformance": [
      { "name": "Agent A", "calls": 124, "satisfaction": 4.8 },
      { "name": "Agent B", "calls": 118, "satisfaction": 4.6 },
      { "name": "Agent C", "calls": 135, "satisfaction": 4.7 },
      { "name": "Agent D", "calls": 112, "satisfaction": 4.5 },
      { "name": "Agent E", "calls": 128, "satisfaction": 4.9 }
    ],
    "callType": [
      { "name": "Support", "value": 52, "fill": "#4ade80" },
      { "name": "Sales", "value": 28, "fill": "#60a5fa" },
      { "name": "Billing", "value": 15, "fill": "#f59e0b" },
      { "name": "Complaint", "value": 5, "fill": "#ef4444" }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'marketing',
  $$
  {
    "campaignPerformance": [
      { "month": "Jan", "impressions": 45000, "clicks": 2800, "conversions": 280 },
      { "month": "Feb", "impressions": 52000, "clicks": 3200, "conversions": 340 },
      { "month": "Mar", "impressions": 48000, "clicks": 3100, "conversions": 310 },
      { "month": "Apr", "impressions": 61000, "clicks": 4100, "conversions": 450 },
      { "month": "May", "impressions": 58000, "clicks": 3900, "conversions": 420 },
      { "month": "Jun", "impressions": 72000, "clicks": 5200, "conversions": 620 }
    ],
    "channelData": [
      { "name": "Email", "value": 32, "fill": "#4ade80" },
      { "name": "Social Media", "value": 28, "fill": "#60a5fa" },
      { "name": "Search", "value": 22, "fill": "#a855f7" },
      { "name": "Display", "value": 18, "fill": "#f59e0b" }
    ],
    "campaignROI": [
      { "campaign": "Summer Promo", "roi": 3.2 },
      { "campaign": "Back to School", "roi": 2.8 },
      { "campaign": "Holiday Sale", "roi": 4.1 },
      { "campaign": "Black Friday", "roi": 5.2 },
      { "campaign": "New Year", "roi": 2.4 }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'compliance',
  $$
  {
    "complianceScore": [
      { "month": "Jan", "score": 88 },
      { "month": "Feb", "score": 90 },
      { "month": "Mar", "score": 91 },
      { "month": "Apr", "score": 93 },
      { "month": "May", "score": 94 },
      { "month": "Jun", "score": 94 }
    ],
    "riskAssessment": [
      { "name": "Critical", "value": 1, "fill": "#ef4444" },
      { "name": "High", "value": 3, "fill": "#f97316" },
      { "name": "Medium", "value": 6, "fill": "#eab308" },
      { "name": "Low", "value": 15, "fill": "#4ade80" }
    ],
    "complianceFramework": [
      { "framework": "GDPR", "compliance": 95 },
      { "framework": "CCPA", "compliance": 92 },
      { "framework": "HIPAA", "compliance": 89 },
      { "framework": "SOC 2", "compliance": 96 },
      { "framework": "ISO 27001", "compliance": 90 }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'talent',
  $$
  {
    "employeeGrowth": [
      { "month": "Jan", "employees": 215, "hired": 8, "separated": 2 },
      { "month": "Feb", "employees": 220, "hired": 6, "separated": 1 },
      { "month": "Mar", "employees": 225, "hired": 7, "separated": 2 },
      { "month": "Apr", "employees": 232, "hired": 9, "separated": 2 },
      { "month": "May", "employees": 240, "hired": 10, "separated": 2 },
      { "month": "Jun", "employees": 248, "hired": 12, "separated": 4 }
    ],
    "departmentStaff": [
      { "department": "Sales", "count": 48 },
      { "department": "Service", "count": 52 },
      { "department": "Network", "count": 38 },
      { "department": "Marketing", "count": 22 },
      { "department": "HR", "count": 18 },
      { "department": "Admin", "count": 70 }
    ],
    "turnoverData": [
      { "name": "Sales", "value": 8, "fill": "#ef4444" },
      { "name": "Service", "value": 5, "fill": "#f97316" },
      { "name": "Network", "value": 3, "fill": "#eab308" },
      { "name": "Admin", "value": 4, "fill": "#4ade80" }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'billing',
  $$
  {
    "revenueData": [
      { "month": "Jul", "collected": 2400000, "outstanding": 180000, "overdue": 45000 },
      { "month": "Aug", "collected": 2650000, "outstanding": 195000, "overdue": 52000 },
      { "month": "Sep", "collected": 2800000, "outstanding": 210000, "overdue": 48000 },
      { "month": "Oct", "collected": 3100000, "outstanding": 175000, "overdue": 38000 },
      { "month": "Nov", "collected": 3350000, "outstanding": 220000, "overdue": 55000 },
      { "month": "Dec", "collected": 3600000, "outstanding": 190000, "overdue": 42000 }
    ],
    "paymentMethodData": [
      { "name": "Debit Order", "value": 58, "color": "#10b981" },
      { "name": "EFT", "value": 22, "color": "#3b82f6" },
      { "name": "Card", "value": 12, "color": "#f59e0b" },
      { "name": "Cash", "value": 8, "color": "#8b5cf6" }
    ],
    "agingData": [
      { "range": "Current", "amount": 2850000, "customers": 12450 },
      { "range": "30 Days", "amount": 420000, "customers": 1850 },
      { "range": "60 Days", "amount": 185000, "customers": 720 },
      { "range": "90 Days", "amount": 95000, "customers": 380 },
      { "range": "120+ Days", "amount": 62000, "customers": 245 }
    ],
    "invoices": [
      { "id": "INV-2024-0012", "customer": "Thabo Mokoena", "amount": 899, "status": "paid", "date": "2024-01-10", "method": "Debit Order" },
      { "id": "INV-2024-0013", "customer": "Sipho Ndlovu", "amount": 1299, "status": "pending", "date": "2024-01-11", "method": "EFT" },
      { "id": "INV-2024-0014", "customer": "Nomvula Dlamini", "amount": 599, "status": "overdue", "date": "2024-01-05", "method": "Card" },
      { "id": "INV-2024-0015", "customer": "Johan van der Merwe", "amount": 1899, "status": "paid", "date": "2024-01-12", "method": "Debit Order" },
      { "id": "INV-2024-0016", "customer": "Lerato Molefe", "amount": 799, "status": "pending", "date": "2024-01-13", "method": "EFT" },
      { "id": "INV-2024-0017", "customer": "Pieter Botha", "amount": 2499, "status": "overdue", "date": "2024-01-02", "method": "Card" }
    ],
    "collections": [
      { "id": 1, "customer": "Ayanda Zulu", "amount": 2850, "daysPastDue": 45, "lastContact": "2024-01-08", "status": "in-progress", "phone": "082 555 1234" },
      { "id": 2, "customer": "David Smith", "amount": 1650, "daysPastDue": 32, "lastContact": "2024-01-10", "status": "promise-to-pay", "phone": "083 666 5678" },
      { "id": 3, "customer": "Fatima Patel", "amount": 4200, "daysPastDue": 68, "lastContact": "2024-01-05", "status": "escalated", "phone": "084 777 9012" },
      { "id": 4, "customer": "Kagiso Mabaso", "amount": 980, "daysPastDue": 21, "lastContact": "2024-01-12", "status": "new", "phone": "085 888 3456" },
      { "id": 5, "customer": "Linda Nkosi", "amount": 3500, "daysPastDue": 95, "lastContact": "2024-01-01", "status": "legal", "phone": "086 999 7890" }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'products',
  $$
  {
    "subscriptionTrend": [
      { "month": "Jul", "fibre": 8500, "lte": 3200, "voip": 1800, "tv": 2400 },
      { "month": "Aug", "fibre": 9100, "lte": 3400, "voip": 1950, "tv": 2600 },
      { "month": "Sep", "fibre": 9800, "lte": 3550, "voip": 2100, "tv": 2850 },
      { "month": "Oct", "fibre": 10500, "lte": 3700, "voip": 2250, "tv": 3100 },
      { "month": "Nov", "fibre": 11200, "lte": 3900, "voip": 2400, "tv": 3350 },
      { "month": "Dec", "fibre": 12000, "lte": 4100, "voip": 2550, "tv": 3600 }
    ],
    "productMixData": [
      { "name": "Fibre", "value": 54, "color": "#10b981" },
      { "name": "LTE", "value": 18, "color": "#3b82f6" },
      { "name": "VoIP", "value": 12, "color": "#f59e0b" },
      { "name": "TV", "value": 16, "color": "#8b5cf6" }
    ],
    "products": [
      { "id": 1, "name": "Fibre 50Mbps", "category": "Fibre", "price": 699, "subscribers": 4250, "status": "active", "mrr": 2970750 },
      { "id": 2, "name": "Fibre 100Mbps", "category": "Fibre", "price": 899, "subscribers": 3850, "status": "active", "mrr": 3461150 },
      { "id": 3, "name": "Fibre 200Mbps", "category": "Fibre", "price": 1199, "subscribers": 2100, "status": "active", "mrr": 2517900 },
      { "id": 4, "name": "LTE Uncapped", "category": "LTE", "price": 599, "subscribers": 2450, "status": "active", "mrr": 1467550 },
      { "id": 5, "name": "LTE 100GB", "category": "LTE", "price": 399, "subscribers": 1650, "status": "active", "mrr": 658350 },
      { "id": 6, "name": "VoIP Basic", "category": "VoIP", "price": 149, "subscribers": 1800, "status": "active", "mrr": 268200 },
      { "id": 7, "name": "TV Premium", "category": "TV", "price": 299, "subscribers": 2100, "status": "active", "mrr": 627900 },
      { "id": 8, "name": "Fibre 500Mbps", "category": "Fibre", "price": 1599, "status": "draft", "subscribers": 0, "mrr": 0 }
    ],
    "bundles": [
      { "id": 1, "name": "Home Essential", "products": ["Fibre 50Mbps", "VoIP Basic"], "price": 799, "subscribers": 1250, "discount": "6%" },
      { "id": 2, "name": "Home Premium", "products": ["Fibre 100Mbps", "TV Premium", "VoIP Basic"], "price": 1249, "subscribers": 850, "discount": "8%" },
      { "id": 3, "name": "Business Starter", "products": ["Fibre 100Mbps", "VoIP Basic"], "price": 999, "subscribers": 420, "discount": "5%" },
      { "id": 4, "name": "Ultimate Bundle", "products": ["Fibre 200Mbps", "TV Premium", "VoIP Basic"], "price": 1549, "subscribers": 380, "discount": "10%" }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'portal',
  $$
  {
    "visitorData": [
      { "day": "Mon", "website": 2400, "customerPortal": 1800, "fieldApp": 450, "techApp": 320 },
      { "day": "Tue", "website": 2100, "customerPortal": 1650, "fieldApp": 480, "techApp": 340 },
      { "day": "Wed", "website": 2800, "customerPortal": 2100, "fieldApp": 520, "techApp": 380 },
      { "day": "Thu", "website": 3200, "customerPortal": 2400, "fieldApp": 490, "techApp": 350 },
      { "day": "Fri", "website": 2900, "customerPortal": 2200, "fieldApp": 510, "techApp": 370 },
      { "day": "Sat", "website": 1800, "customerPortal": 1400, "fieldApp": 280, "techApp": 150 },
      { "day": "Sun", "website": 1500, "customerPortal": 1100, "fieldApp": 220, "techApp": 120 }
    ],
    "landingPages": [
      { "id": 1, "name": "Fibre Promo Q1", "url": "/promo/fibre-q1", "status": "published", "views": 12450, "conversions": 342, "rate": "2.7%" },
      { "id": 2, "name": "Business Solutions", "url": "/business", "status": "published", "views": 8920, "conversions": 156, "rate": "1.7%" },
      { "id": 3, "name": "LTE Uncapped Launch", "url": "/lte-launch", "status": "draft", "views": 0, "conversions": 0, "rate": "-" },
      { "id": 4, "name": "Referral Program", "url": "/refer", "status": "published", "views": 5640, "conversions": 89, "rate": "1.6%" }
    ],
    "aiAgents": [
      { "id": 1, "name": "Customer Support Bot", "status": "active", "conversations": 4250, "resolution": "78%", "avgTime": "2.3 min" },
      { "id": 2, "name": "Sales Assistant", "status": "active", "conversations": 1820, "resolution": "65%", "avgTime": "4.1 min" },
      { "id": 3, "name": "Technical Help Bot", "status": "active", "conversations": 2340, "resolution": "82%", "avgTime": "3.5 min" },
      { "id": 4, "name": "Billing Inquiries", "status": "paused", "conversations": 890, "resolution": "71%", "avgTime": "2.8 min" }
    ],
    "fieldSalesStats": {
      "activeAgents": 45,
      "visitsToday": 128,
      "leadsGenerated": 34,
      "dealsWon": 12
    },
    "technicianStats": {
      "activeTechs": 38,
      "jobsCompleted": 86,
      "avgJobTime": "42 min",
      "customerRating": 4.7
    }
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

insert into module_data (module_id, data)
values (
  'dashboard',
  $$
  {
    "stats": [
      { "id": "revenue", "title": "Total Revenue", "value": "R22.5M", "change": "+12.5%", "changeType": "positive", "iconKey": "revenue", "description": "vs last month" },
      { "id": "subscribers", "title": "Active Subscribers", "value": "24,847", "change": "+8.2%", "changeType": "positive", "iconKey": "subscribers", "description": "vs last month" },
      { "id": "tickets", "title": "Open Tickets", "value": "128", "change": "-24%", "changeType": "positive", "iconKey": "tickets", "description": "vs last week" },
      { "id": "uptime", "title": "Network Uptime", "value": "99.97%", "change": "+0.02%", "changeType": "positive", "iconKey": "uptime", "description": "this month" }
    ],
    "modules": [
      {
        "title": "Sales",
        "description": "Track deals, manage pipeline and forecast revenue",
        "iconKey": "sales",
        "stats": [
          { "label": "Monthly Revenue", "value": "$284K" },
          { "label": "New Deals", "value": "47" }
        ],
        "features": ["Lead tracking", "Quote generation", "Commission reports"]
      },
      {
        "title": "CRM",
        "description": "Manage customer relationships and interactions",
        "iconKey": "crm",
        "stats": [
          { "label": "Total Customers", "value": "12,847" },
          { "label": "Active Leads", "value": "342" }
        ],
        "features": ["Contact management", "Customer timeline", "Segmentation"]
      },
      {
        "title": "Service",
        "description": "Handle support tickets and service requests",
        "iconKey": "service",
        "stats": [
          { "label": "Open Tickets", "value": "128" },
          { "label": "Avg Resolution", "value": "4.2h" }
        ],
        "features": ["Ticket queue", "SLA tracking", "Knowledge base"]
      },
      {
        "title": "Network",
        "description": "Monitor infrastructure and network performance",
        "iconKey": "network",
        "stats": [
          { "label": "Uptime", "value": "99.97%" },
          { "label": "Active Nodes", "value": "1,247" }
        ],
        "features": ["Real-time monitoring", "Outage alerts", "Capacity planning"]
      },
      {
        "title": "Call Center",
        "description": "Manage inbound and outbound call operations",
        "iconKey": "call-center",
        "stats": [
          { "label": "Calls Today", "value": "1,847" },
          { "label": "Avg Wait Time", "value": "42s" }
        ],
        "features": ["Call routing", "Agent performance", "Call recording"]
      },
      {
        "title": "Marketing",
        "description": "Run campaigns and track marketing performance",
        "iconKey": "marketing",
        "stats": [
          { "label": "Active Campaigns", "value": "12" },
          { "label": "Conversion Rate", "value": "3.2%" }
        ],
        "features": ["Email campaigns", "Analytics", "A/B testing"]
      },
      {
        "title": "Compliance",
        "description": "Ensure regulatory compliance and data security",
        "iconKey": "compliance",
        "stats": [
          { "label": "Compliance Score", "value": "94%" },
          { "label": "Open Issues", "value": "7" }
        ],
        "features": ["Audit trails", "Policy management", "Risk assessment"]
      },
      {
        "title": "Talent",
        "description": "Manage HR, recruitment and employee performance",
        "iconKey": "talent",
        "stats": [
          { "label": "Total Employees", "value": "248" },
          { "label": "Open Positions", "value": "14" }
        ],
        "features": ["Recruitment", "Performance reviews", "Training"]
      }
    ]
  }
  $$::jsonb
)
on conflict (module_id) do update set data = excluded.data;

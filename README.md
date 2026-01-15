# CoreConnect: The Premier ISP Operating System (SA Edition) 🚀🏜️🇿🇦

CoreConnect is a carrier-grade, microservice-based operations platform designed specifically for South African ISPs. It unifies CRM, Sales, Marketing, Billing, Network provisioning, and FNO automation into a single, high-performance ecosystem.

## 🏗️ Core Connect Modules

### 1. Sales Connect & CRM Connect (`/services/sales`, `/services/crm`)
*   **Lead Management**: Track and convert prospects through a visual pipeline.
*   **Coverage Qualification**: Integrated maps for all major service providers.
*   **Subscriber 360**: Full CRM with RICA verification status.

### 2. Marketing Connect (`/services/marketing`)
*   **AI Content Studio**: Automated content generation for social and email.
*   **Campaign Management**: Multi-channel lead nurturing.

### 3. Billing Connect (`/services/billing`)
*   **Automated Invoicing**: Generation of invoices in ZAR.
*   **Paystack Integration**: Built-in logic for SA's leading payment gateway.
*   **Auto-Suspension**: Logic-based service control based on payment status.

### 4. Network Connect & IoT Connect (`/services/network`, `/services/iot`)
*   **RADIUS Management**: Full FreeRADIUS SQL integration with real-time monitoring.
*   **Hardware Control**: Proactive performance monitoring for CPEs and ONTs.
*   **FNO Master Portal**: Seamless activations for Vumatel, Openserve, Frogfoot, etc.

### 5. Support Connect (`/services/support`)
*   **Rapid Ticketing**: SLA-driven ticket management.
*   **Remote Diagnosis**: One-click ONT health checks and diagnostics.

### 6. Call Center Connect (`/services/call_center`)
*   **Sentiment AI**: Real-time analysis of agent-customer interactions.
*   **Agent Whisperer**: AI-driven prompts during live calls.

### 7. Talent Connect (`/services/staff`)
*   **Performance Tracking**: Individual and team KPI monitoring.
*   **Staff Sentiment**: AI-driven morale and burnout analysis.

---

## 🛠️ Stack
*   **Backend**: Python 3.10+ (FastAPI)
*   **Database**: PostgreSQL with PostGIS (Coverage mapping)
*   **Frontend**: Vanilla HTML/CSS/JS (Modern Dashboard UI)
*   **Automation**: Playwright (Browser-based FNO adapters)

## 📡 FNO Proactive Intelligence Layer
Unlike traditional systems, CoreConnect uses a multi-vector listener to track FNO health:
1. **APIs**: Direct B2B hooks.
2. **Scrapers**: Real-time keyword monitoring of FNO status pages.
3. **Email Parsers**: Automatically ingests and maps NOC notifications to affected customer IDs.

---
Created by Antigravity AI for BurniWorld.

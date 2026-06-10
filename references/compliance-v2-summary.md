# Compliance Service v2 — Summary

## Overview
Comprehensive compliance management service for South African telecom operators.
Replaces v1 (11 tables, 29 routes) with v2 (53 ORM classes, 105 routes, 5 route modules).

## Database (53 classes | 22 tables)

### Core
- **Contract** — Central entity for all contracts (FNO, supplier, customer, employee, partner, SLA, interconnect, infrastructure, maintenance)
- **ContractSLA** + **SlaMeasurement** — Auto-breach detection with severity classification
- **ContractAuditLog** — Full audit trail

### Tax Compliance
- **TaxRegistration** — VAT, PAYE, UIF, SDL, income tax, provisional tax, customs, excise
- **TaxReturn** — Filing tracking with SARS references, assessment dates, payment tracking

### Health & Safety
- **HsRiskAssessment** — Risk scoring with findings and recommendations
- **HsIncident** — COIDA reporting, root cause analysis, corrective/preventive actions

### Corporate
- **CipcFiling** — Annual returns, financial statements, fee tracking
- **BylawObligation** — Municipal bylaw tracking per municipality

### BBBEE
- **BbbeeScorecard** — Amended Codes 2023 calculator (ownership, MCD, SD, ESD, SED)
- Auto level calculation (Level 1–8, non-compliant) with certificate tracking

### HR Operations
- **LeaveApplication** + **LeaveBalance** — Full leave workflow (annual, sick, family responsibility, maternity, parental, study, unpaid)
- **VehicleRegistration** — Fleet management with license, roadworthy, insurance tracking
- **ForeignWorkerPermit** — DHA permits (general work, critical skills, intra-company, etc.)
- **TravelReadiness** — Visa tracking, passport, insurance, vaccination, risk assessment

### DR/BCP
- **DrBcpPlan** — Full DR/BCP plans with RTO/RPO, testing, review cycles
- **DrBcpAssessment** — Readiness scoring (infrastructure, data protection, communication, staff awareness, vendor)

### Scoring & Obligations
- **ComplianceScore** — Per-category scoring (0–100) with auto-calculation
- **ComplianceObligation** — Regulatory obligation tracking with evidence requirements

### e-Services Gateway
- **EserviceSubmission** — Form submission hub for SARS, CIPC, DTI, DHA, NaTIS, DoL, BBBEE Commission, municipal portals

### Documents & Financial
- **ComplianceDocument** — OCR processing, extracted data, financial summary extraction
- **FinancialScenario** — Best/worst/base/stress case planning with funding matching

### Regulatory
- **IcasaSubmission** + **IcasaScrapeJob** + **IcasaRegulationChange** — ICASA lodgments + web scraping
- **PopiDataAccessRequest** + **PopiAnonymizationLog** + **PopiConsentRecord** — Full POPI Act compliance
- **RicaVerification** — SHA-256 hashed ID storage (no direct RICA DB use)
- **BreachRegister** — With ICASA + POPI Commission notification tracking
- **FundingOpportunity** — Matched by compliance score and BBBEE level

## Route Modules (105 endpoints)

| Module | Routes | Coverage |
|--------|--------|----------|
| contracts.py | 11 | Contract CRUD, SLAs, measurements, expiry dashboard |
| regulatory.py | 22 | Tax, H&S, CIPC, Bylaw, BBBEE scorecard calculator |
| hr_operations.py | 21 | Leave, vehicles, foreign workers, travel readiness |
| operations.py | 24 | DR/BCP, scoring, e-SERVICES, documents, financial scenarios |
| compliance.py | 27 | ICASA, POPI, RICA, breaches, funding opportunities |

## Key Features
- **SHA-256 hashed RICA IDs** — Never stores raw ID numbers (POPI compliant)
- **Auto DSAR 30-day deadlines** — POPI compliance built in
- **BBBEE calculator** — Amended Codes 2023 weights, auto level determination
- **Funding matcher** — Matches opportunities by compliance score + BBBEE level
- **ICASA scraper** — Background scrape jobs for regulatory change detection
- **e-Services gateway** — Single hub for all government form submissions
- **Financial scenario planning** — Compliance cost impact + funding eligibility
- **Document understanding** — OCR + structured data + financial extraction

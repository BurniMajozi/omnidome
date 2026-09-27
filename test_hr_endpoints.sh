#!/usr/bin/env bash
set -e
echo "Testing Payslip Preview with tenant header:"
curl -s -X POST -H "x-tenant-id: 00000000-0000-0000-0000-000000000001" \
  -H "Content-Type: application/json" \
  -d '{"gross_salary": 35000, "allowances": 2500, "medical_aid_members": 2}' \
  "http://127.0.0.1:8009/payroll/calculate-preview"
echo ""

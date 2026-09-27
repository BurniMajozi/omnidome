INSERT INTO onboarding_tasks (tenant_id, employee_id, task_name, description, owner_department, due_date, status, sort_order)
VALUES
('00000000-0000-0000-0000-000000000001', '6feea72a-5bae-41ab-b4d8-37ab77644cf4', 'Issue Laptop & FTTH Splicer Tools', 'Assign standard ThinkPad T14 and Fujikura 90S fusion splicer kit', 'IT & Field Ops', CURRENT_DATE + 3, 'PENDING', 1),
('00000000-0000-0000-0000-000000000001', '6feea72a-5bae-41ab-b4d8-37ab77644cf4', 'Submit SARS Tax Number & Bank Confirmation', 'Obtain signed SARS eFiling confirmation & stamped bank statement', 'Payroll', CURRENT_DATE + 5, 'DONE', 2),
('00000000-0000-0000-0000-000000000001', 'd106f655-4904-47f1-b379-a9efc841321c', 'PSIRA Registration Verification', 'Verify Grade C Security Officer registration with Private Security Industry Regulatory Authority', 'Compliance', CURRENT_DATE + 2, 'PENDING', 3),
('00000000-0000-0000-0000-000000000001', '80082856-2502-4d28-85ec-33338386b048', 'OmniDome CRM & VoIP Softphone Setup', 'Provision HubSpot CRM seats, sales pipeline access, and WebRTC extension', 'IT Support', CURRENT_DATE + 4, 'PENDING', 4);

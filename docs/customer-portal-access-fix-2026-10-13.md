# Customer portal access fix — 13 October 2026

The existing `test@omnidome.local` login is now linked to existing CRM account **ACC-0000-8E607CBD** in the same tenant, following your instruction to choose any customer. Its customer profile returns HTTP 200 without a HomeDome property. No new customer, home or fabricated usage was created.

## Finish signing in

1. Open the one-use password-recovery browser tab queued in **Codex** for this chat. Choose your new password in OmniDome's existing reset form. No recovery email was sent, because `.local` addresses cannot receive ordinary email. Your password was not changed by the agent and was never requested in chat.
2. Refresh [the customer portal login](http://localhost:3001/login).
3. Sign in as `test@omnidome.local` with the password you chose. This is the same OmniDome identity used by the platform; the Home Assistant account uses its own credentials.

The recovery URL contains a one-use credential and is not stored in this document or the repository. If it expires before use, an operator can prepare a replacement with `deploy/commercial/prepare-test-portal-recovery.py` inside the admin container and open its result privately for you.

## What changed

- The original account exists and is confirmed in Supabase. The customer build's Supabase URL and public key match the live platform. The screenshot's error came from authentication, before customer lookup.
- I removed the HomeDome requirement I had introduced into portal sign-in. An explicit `customer_portal_accounts` association now identifies the customer, with the existing home association supported for compatibility.
- Profile access requires an active verified platform user and a customer in the same tenant. Account linking requires an administrator; customer callers cannot link themselves to arbitrary CRM records. Existing links cannot be silently reassigned.
- The profile and account-link routes do not require an IoT subscription. Device access and customer support consent retain their existing HomeDome gates.
- The login page trims the email, explains incorrect credentials, distinguishes Home Assistant credentials, offers password recovery and removes the non-working registration link. Real customer accounts are provided by the ISP.
- New tables are created by the service's existing startup migration. No existing account password or roles were changed.

## Verification

- **63 IoT tests passed**, including portal access without a home, cross-tenant isolation, conflicting customer associations and rejected customer self-linking.
- **11 PostgreSQL checks passed** with all probe rows rolled back.
- Customer production build and type checking passed. The customer app was restarted on port 3001.
- The selected test account's profile returned HTTP 200 after the association was committed.
- The login page returned HTTP 200, rendered “Forgot password?” and no longer rendered the broken registration link.
- The backend deployment completed with rollback image stamp `20261013161039`. The web and workflow images were retained.

Completing password reset and a full browser sign-in still require your input. These changes are deployed locally but are not yet committed or pushed.

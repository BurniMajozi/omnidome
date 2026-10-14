# Customer portal sign-in check — 14 October 2026

The screenshot uses `bunibraai@gmail.com`. The registered account is **burnibraai@gmail.com**, with an **r**. The misspelled address has no authentication or platform account; no new account was created for it.

Both `burnibraai@gmail.com` and `test@omnidome.local` are active, confirmed Supabase accounts. Email/password sign-in is enabled. The registered Gmail account also has a Google identity, but Google sign-in is currently disabled in the project's authentication settings.

The registered Gmail account is now associated with the same existing tenant-scoped pilot customer as the test account: **ACC-0000-8E607CBD**. Passwords, roles and Home Assistant assignments were not changed.

For each account, an operator diagnostic generated a one-use sign-in proof for the existing identity without sending email, verified it with Supabase, and called the real customer portal proxy using the resulting bearer token. Both Supabase sign-in and the authenticated customer profile returned **HTTP 200**. Each probe session was signed out with local scope, leaving other sessions alone. No credential values were printed or saved by that diagnostic.

The previous reset browser tab was queued in Codex rather than confirmed available to the user. The replacement handoff is a private HTML file in the user's local Temp directory, outside the repository, containing directly clickable one-use password reset links and the correct customer login address. It should be opened in the user's browser, kept private, and deleted after use. Actual reset credentials are intentionally omitted from this report.

The user must choose their password in the reset form, then sign in at `http://localhost:3001/login` with the corresponding account. A full password-based browser sign-in cannot be verified without that user step. No queued tab is reported as a completed password reset.

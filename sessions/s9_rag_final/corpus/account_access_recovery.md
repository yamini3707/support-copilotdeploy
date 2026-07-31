---
doc_id: account_access_recovery
title: Account Access & Recovery
category: account
---

# Account Access & Recovery

## Password reset

Users reset their own password via **Sign in → Forgot password**. A reset link is emailed and
is valid for 60 minutes. Support cannot set or view passwords.

## Multi-factor authentication (MFA) lockout

If a user loses their MFA device, an **organization admin** can reset that user's MFA under
**Admin → Members → (user) → Reset MFA**. If the locked-out user *is* the only admin, support
must verify ownership of the account before assisting, then escalate to the account-recovery
team — support does not disable MFA directly for security reasons.

## Locked accounts

Accounts lock after 10 failed sign-in attempts and auto-unlock after 30 minutes. An admin can
unlock sooner from the member list.

## Seat management

Admins add or remove seats under **Admin → Members**. Adding a seat beyond the plan's seat
limit requires an upgrade:

- Free: 3 seats · Pro: 25 · Business: 100 · Enterprise: unlimited.

Removing a seat frees it immediately; billing is prorated as account credit on the next invoice.

## SSO and access

On Business/Enterprise, if SSO is enforced, users sign in through the IdP and cannot use a
password. If SSO is misconfigured or an SSO incident is active, admins can temporarily allow
password fallback from **Admin → Security → SSO**.

## What support must not do

Do not reset MFA or passwords on behalf of a user without verifying account ownership. Do not
disclose whether a specific email has an account (account-enumeration protection).

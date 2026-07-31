---
doc_id: data_retention_policy
title: Data Retention & Deletion
category: account
---

# Data Retention & Deletion

## Retention windows by plan

Deleted projects, docs, and activity data are recoverable for a limited window that depends
on the plan:

| Plan | Retention |
|---|---|
| Free | 30 days |
| Pro | 1 year |
| Business | 3 years |
| Enterprise | Custom (default 10 years) |

After the retention window, data is permanently purged and cannot be recovered.

## Recovering deleted data

Within the retention window, an admin can restore deleted projects from **Admin → Trash**.
Beyond the window, recovery is not possible — support cannot retrieve purged data, and should
not imply otherwise.

## GDPR / right-to-erasure requests

Customers in the EU (and others) may request permanent deletion of personal data. These are
handled as **verified data-subject requests** and must be **escalated to the privacy team** —
support agents should not action erasure directly. Confirm the requester's identity and the
scope, then escalate.

## Export before deletion

We recommend exporting data before deleting. See the export troubleshooting guide if exports
fail. Exports respect the same plan retention limits.

## What support must not do

Do not promise recovery of data past the retention window. Do not action GDPR erasure directly.
Do not disclose another customer's data or retention configuration.

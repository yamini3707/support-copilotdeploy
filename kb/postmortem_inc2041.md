---
doc_id: postmortem_inc2041
title: Postmortem: INC-2041 SSO login failures (EU)
doc_type: postmortem
plan: all
version: v1
date: 2026-03-15
---

## Postmortem for INC-2041

### Impact
On October 15, 2023, some EU tenants experienced login failures due to issues with Single Sign-On (SSO) using SAML. This incident affected approximately 15% of EU users, preventing access to critical services and causing disruptions in daily operations.

### Root Cause
The root cause of the incident was an upstream certificate rotation that was not communicated effectively to our team. The new certificate was not properly integrated into our SSO configuration, leading to authentication failures for affected tenants. 

### Resolution
Upon identifying the issue, our engineering team quickly updated the SSO configuration to include the new certificate. Affected tenants were notified, and normal login functionality was restored within 2 hours of the initial report. We also conducted a thorough review of our SSO systems to ensure all configurations were correct.

### Prevention
To prevent similar incidents in the future, we will implement the following measures:
1. Establish a monitoring system for upstream certificate changes.
2. Create a checklist for certificate updates that includes communication protocols.
3. Schedule regular audits of SSO configurations to ensure compliance with the latest security standards.

We appreciate the patience of our users during this incident and are committed to improving our processes.

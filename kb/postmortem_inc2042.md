---
doc_id: postmortem_inc2042
title: Postmortem: INC-2042 elevated API 5xx/429
doc_type: postmortem
plan: all
version: v1
date: 2026-03-15
---

# Postmortem for INC-2042

## Impact
On October 15, 2023, users on the Business and Enterprise tiers experienced elevated 5xx and 429 status codes when accessing the public API. This disruption affected approximately 30% of requests, leading to service degradation and user frustration. The incident lasted for 4 hours, from 10:00 AM to 2:00 PM UTC, impacting critical business operations for several clients.

## Root Cause
The root cause was identified as a misconfiguration in the rate-limiting settings for the Business and Enterprise tiers. An unexpected surge in API calls, driven by a recent marketing campaign, exceeded the configured limits, triggering excessive 429 responses. Additionally, certain backend services experienced failures, resulting in 5xx errors.

## Resolution
The incident was resolved by adjusting the rate-limiting parameters to accommodate the increased traffic and by implementing a temporary scaling of backend services. The team monitored the API closely after the changes, ensuring that the system stabilized and returned to normal operational levels by 2:00 PM UTC.

## Prevention
To prevent recurrence, we will implement the following measures:
1. Review and adjust rate-limiting configurations for all tiers.
2. Enhance monitoring and alerting for traffic spikes.
3. Conduct a post-incident review to refine our scaling strategies for backend services.

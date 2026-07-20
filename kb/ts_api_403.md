---
doc_id: ts_api_403
title: API write requests return 403 Forbidden
doc_type: troubleshooting
plan: all
version: v1
date: 2026-03-15
---

# Troubleshooting: API Write Requests Return 403 Forbidden

If you encounter a `403 Forbidden` error when attempting to make write requests to the CloudDesk API, it typically indicates that your current API plan does not allow write operations. 

The Pro plan offers read-only access, which means you can retrieve data but cannot modify or create new entries. To perform write operations, you need to upgrade to the Business plan or higher, which includes full read and write capabilities.

To resolve the `403` error, verify your API plan by checking your account settings. If you are on the Pro plan and require write access, consider upgrading to the Business plan or a higher tier that meets your needs.

Once you have the appropriate plan, your write requests should function correctly without returning a `403 Forbidden` error. If issues persist after upgrading, ensure that your API keys are correctly configured and that you are using the correct endpoints for write operations.

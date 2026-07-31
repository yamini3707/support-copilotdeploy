---
doc_id: ts_webhook_retry
title: Webhooks not delivered (WEBHOOK_RETRY_EXHAUSTED)
doc_type: troubleshooting
plan: all
version: v1
date: 2026-03-15
---

### Troubleshooting Webhooks Not Delivered (WEBHOOK_RETRY_EXHAUSTED)

If you encounter the error `WEBHOOK_RETRY_EXHAUSTED`, it indicates that CloudDesk has attempted to deliver a webhook multiple times but received non-2xx HTTP responses each time. CloudDesk retries webhook delivery a limited number of times (typically 24 hours) before marking the delivery as failed.

To resolve this issue, follow these steps:

1. **Check Your Endpoint**: Ensure that your webhook endpoint is correctly configured and accessible. It should return a 200 HTTP status code upon successful processing of the webhook.

2. **Review Logs**: Examine your server logs to identify the responses sent back to CloudDesk. Look for any error messages or status codes that are not in the 2xx range.

3. **Test Your Endpoint**: Use tools like Postman or cURL to manually send requests to your endpoint and verify that it responds correctly.

By ensuring your endpoint returns a 200 status code, you can prevent the `WEBHOOK_RETRY_EXHAUSTED` error from occurring.

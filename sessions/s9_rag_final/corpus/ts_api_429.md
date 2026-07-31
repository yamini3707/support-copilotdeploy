---
doc_id: ts_api_429
title: Resolving HTTP 429 (Too Many Requests)
doc_type: troubleshooting
plan: all
version: v1
date: 2026-03-15
---

# Resolving HTTP 429 (Too Many Requests)

If you encounter an HTTP 429 error, it indicates that your plan's API rate limit has been exceeded. This is a protective measure to ensure fair usage and system stability. Here’s how to resolve this issue:

1. **Check the Response Header**: When you receive a 429 error, look for the `Retry-After` header in the response. This header specifies how long you should wait before making another request. Always respect this value to avoid further penalties.

2. **Implement Exponential Backoff**: If you continue to receive 429 errors, implement an exponential backoff strategy. This means you should increase the wait time between requests after each 429 response. For example, if you receive a 429 error, wait for the `Retry-After` duration, then double the wait time for subsequent requests.

3. **Consider Upgrading Your Plan**: If you consistently receive 429 errors despite following the above steps, it may indicate that your current plan does not meet your usage needs. Consider upgrading to a higher plan that offers a more generous API rate limit.

By following these steps, you can effectively manage and resolve HTTP 429 errors.

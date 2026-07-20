---
doc_id: dist_api_error_categories
title: Common API error categories
doc_type: faq
plan: all
version: v1
date: 2026-03-15
---

## Common API Error Categories

When working with APIs, errors are typically categorized into two main groups: client errors (4xx) and server errors (5xx).

**Client Errors (4xx)**: These errors indicate that the request made by the client is incorrect or cannot be processed. This could be due to issues like malformed requests, unauthorized access, or missing parameters. In these cases, the client should review the request and make necessary adjustments.

**Server Errors (5xx)**: These errors suggest that the server encountered an issue while processing a valid request. This could be due to server overload, internal malfunctions, or other unexpected conditions. Clients should not retry immediately, as the problem lies with the server.

**Retries**: For client errors, retries are generally not recommended, while for server errors, it's often beneficial to implement a retry mechanism with exponential backoff.

**Reading Error Responses**: Always check the error response details for guidance on what went wrong and how to resolve it. This information can help you understand the nature of the error and take appropriate action.

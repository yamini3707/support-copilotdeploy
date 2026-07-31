---
doc_id: handbook_api
title: CloudDesk API Guide
doc_type: handbook
plan: all
version: v1
date: 2026-03-15
---

# CloudDesk API Guide

## Authentication

To access the CloudDesk API, you must authenticate using an API key. This key is provided upon registration and should be included in the headers of your requests. The header format is as follows:

```
Authorization: Bearer YOUR_API_KEY
```

Ensure that you keep your API key secure and do not expose it in client-side code or public repositories. If you suspect that your API key has been compromised, you should regenerate it immediately from your CloudDesk account settings.

## Rate Limits

CloudDesk enforces rate limits to ensure fair usage and maintain service quality. The limits vary based on your subscription plan:

- **Pro Plan**: 60 requests per minute
- **Business Plan**: 600 requests per minute
- **Enterprise Plan**: 6000 requests per minute

If you exceed your plan's rate limit, the API will respond with a `429 Too Many Requests` status code. The response will also include a `Retry-After` header, indicating the time in seconds you should wait before making additional requests.

## Pagination

When retrieving lists of resources, the CloudDesk API supports pagination to help manage large datasets. The API uses a combination of `page` and `per_page` query parameters to control the pagination of results.

- `page`: Specifies the page number to retrieve (starting from 1).
- `per_page`: Specifies the number of items to return per page (maximum of 100).

For example, to retrieve the second page of results with 50 items per page, your request would look like this:

```
GET /api/v1/resources?page=2&per_page=50
```

The response will include metadata about the pagination, such as the total number of items and the number of pages available.

## Webhooks

CloudDesk supports webhooks to allow your application to receive real-time notifications about specific events. To set up a webhook, you need to provide a URL endpoint where the notifications will be sent. You can configure webhooks in your CloudDesk account settings.

When an event occurs, CloudDesk will send a POST request to your specified URL with a JSON payload containing details about the event. Ensure that your endpoint can handle incoming requests and respond with a `200 OK` status to acknowledge receipt.

Common events that can trigger webhooks include:

- Resource creation
- Resource updates
- Resource deletions

## Errors

When interacting with the CloudDesk API, you may encounter various error responses. Each error response will include a relevant HTTP status code and a JSON payload with details about the error.

Common HTTP status codes include:

- **400 Bad Request**: The request was invalid or malformed.
- **401 Unauthorized**: Authentication failed or the API key is missing.
- **403 Forbidden**: You do not have permission to access the requested resource.
- **404 Not Found**: The requested resource could not be found.
- **429 Too Many Requests**: Rate limit exceeded (see Rate Limits section).
- **500 Internal Server Error**: An unexpected error occurred on the server.

In the event of an error, review the response payload for additional information and take appropriate action based on the error type.

---
doc_id: ts_export_timeout
title: Export job times out with EXPORT_TIMEOUT
doc_type: troubleshooting
plan: all
version: v1
date: 2026-03-15
---

# Troubleshooting Export Timeout in CloudDesk

If you encounter the error message `EXPORT_TIMEOUT` while attempting to export data from CloudDesk, it typically indicates that the export process is taking too long to complete. Large exports can exceed the time limits set by the system, leading to this timeout error.

To resolve this issue, consider the following solutions:

1. **Split Exports by Project**: Instead of exporting all data at once, divide your export into smaller chunks based on specific projects. This reduces the volume of data processed in a single export, minimizing the risk of a timeout.

2. **Use Date Ranges**: If applicable, filter your export by date range. Exporting data for shorter time periods can significantly decrease the amount of data handled at once, helping to avoid the `EXPORT_TIMEOUT` error.

3. **API Streaming**: For more advanced users, consider utilizing the CloudDesk API to stream data exports. This method allows for more control over the export process and can help bypass timeout issues by processing data in smaller increments.

By implementing these strategies, you can effectively manage large exports and reduce the likelihood of encountering `EXPORT_TIMEOUT`.

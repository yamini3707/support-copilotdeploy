---
doc_id: troubleshooting_exports
title: Troubleshooting Project & Doc Exports
category: technical
---

# Troubleshooting Exports

CloudDesk lets admins export projects and docs from **Admin → Data → Export**. Exports run as
background jobs; large workspaces are emailed a download link when ready.

## Common causes of export failures

1. **Large workspace timeout.** Very large exports can time out. Split the export by project or
   date range, or use the API to stream results (Business/Enterprise).
2. **Expired download link.** Export links expire after 72 hours. Re-run the export to get a
   fresh link.
3. **Insufficient permissions.** Only admins can run full-workspace exports. Members can export
   only projects they own.
4. **Active incident.** If the export-service has an active incident, exports may fail platform-side.
   Check the status page before assuming a customer-side problem.
5. **Retention limits.** You can only export data still within your plan's retention window;
   purged data is not exportable.

## Recommended steps for a failing export

1. Confirm the user has the Admin role.
2. Check the status page / incident tool for an active export-service incident.
3. If no incident, retry with a **narrower scope** (single project or shorter date range).
4. If it still fails on a small scope with no active incident, gather the workspace ID and
   escalate to the platform team.

## What not to promise

Do not promise export of data outside the retention window, and do not promise instant delivery
for very large workspaces — those are queued.

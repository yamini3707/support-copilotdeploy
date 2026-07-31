---
doc_id: plan_changes_and_upgrades
title: Plan Changes, Upgrades & Downgrades
category: account
---

# Plan Changes, Upgrades & Downgrades

Admins change plans under **Admin → Billing → Plan**.

## Upgrades

Upgrades take effect **immediately**. You are charged a **prorated** amount for the remainder of
the current billing period at the new rate. Upgrading unlocks the new tier's features right away:

- Upgrade to **Business** to unlock SSO and the full (read+write) API at 600 req/min.
- Upgrade to **Enterprise** to additionally unlock **audit logs**, 6000 req/min, unlimited seats,
  and custom retention.

Upgrading is the correct path when a customer wants a feature their current plan does not include
(SSO on Pro, audit logs on Business, API on Free). Features are tied to tiers and cannot be added
as standalone add-ons.

## Downgrades

Downgrades take effect at the **end of the current billing period** to avoid mid-cycle feature
loss. Unused value is issued as **account credit**, not a cash refund. After a downgrade, features
not included in the lower tier are disabled, and seat counts above the new limit must be reduced
first.

## Seat changes

Adding seats prorates an immediate charge; removing seats issues account credit at the next
renewal. You cannot exceed a plan's seat cap without upgrading.

## Cancellation

Canceling stops future renewals; access continues until the end of the paid period. A refund of
the most recent charge is available only if requested within the 14-day refund window (see the
refund policy).

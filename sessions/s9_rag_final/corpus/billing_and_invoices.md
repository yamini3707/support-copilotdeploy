---
doc_id: billing_and_invoices
title: Billing & Invoices
category: billing
---

# Billing & Invoices

## Accessing invoices

Admins can view and download invoices under **Admin → Billing → Invoices**. Each invoice shows
the billing period, seat count, plan, amount, and payment status (`paid`, `open`, `past_due`).

## Payment methods

We accept major credit cards and, for Business/Enterprise, ACH / wire and annual invoicing.
Update the card on file under **Admin → Billing → Payment Method**.

## How charges are calculated

Monthly charge = **price per seat × seats purchased**. Changing seat count mid-cycle prorates
the difference. Plan changes prorate as described in the plan-changes guide.

## Past-due accounts (dunning)

If a charge fails, the account moves to **past_due**. We retry the charge over several days and
email the admin. After repeated failures, write access may be suspended until payment succeeds.
Advise the customer to update their payment method; do not restore access manually.

## Duplicate charges

If a customer reports being charged twice, **verify against the invoice records** — look for two
charges of the same amount in the same billing period. Duplicate charges are always refundable
(see the refund policy). Reference the specific duplicate invoice ID when arranging the refund.

## Disputes and chargebacks

If a customer has already filed a chargeback with their bank, do not also issue a refund —
escalate to the billing team to avoid a double reversal.

## What support must not do

Never confirm a refund or credit without verifying the invoice. Do not expose internal payment
processor IDs or another customer's billing details.

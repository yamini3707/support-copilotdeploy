# CloudDesk Support Playbook

The rules a CloudDesk support agent (human or AI) follows. **Every label in the datasets is
derived from these rules** — so when you disagree with your agent's output, check it here first.

You are given these rules. You are *not* given the hidden test answers. Your job is to make your
agent follow the playbook well; the eval measures how well it does.

---

## 1. Category — what kind of ticket is it?

Exactly one of:

| Category | It's this when… | Watch out for |
|---|---|---|
| `billing` | money: charges, refunds, invoices, payment methods, pricing | "why did my bill go up" is billing, not account |
| `technical` | something is broken or erroring | a broken feature is technical; a *missing* feature is `feature_request` |
| `account` | access & admin, no money: login, seats, MFA, plan changes, "is X on my plan?" | "how do I enable SSO?" is account (a plan/how-to question), even though it sounds technical |
| `feature_request` | wants functionality that doesn't exist | "do you support Jira import?" → if it doesn't exist, it's a feature request |
| `other` | greeting, spam, off-topic, unintelligible | "it's not working" with no detail is `other`, not technical |

---

## 2. Priority — how urgent is it?

Priority is a **rule**, not a feeling. Compute it from three factors:

- **Impact:** `blocked` (cannot use the core product at all) · `degraded` (partial problem with a workaround — this includes money issues like a double charge; the money is recoverable, the product still works) · `inquiry` (a question, no harm)
- **Scope:** `org` (many users / whole org) · `single` (one user)
- **Plan:** Enterprise / Business have an SLA; Pro / Free don't.

**Step 1 — base priority** (impact × scope):

| | org | single |
|---|---|---|
| **blocked** | urgent | high |
| **degraded** | high | medium |
| **inquiry** | low | low |

**Step 2 — plan bump:** Enterprise → bump up one level. Business → bump up one level *only if*
impact is blocked or degraded. Pro / Free → no bump. (Cap at `urgent`.)

**Step 3 — billing floor:** any active money harm (double charge, wrong charge) is at least `medium`.

*Worked example:* Pro customer, charged twice → impact `degraded`, scope `single`, plan Pro.
Base = `medium`; no plan bump; billing floor `medium` → **medium**.

---

## 3. Escalation — does it need a human? (`requires_human`)

Default is **false** — the agent handles it (answer, cite policy, or take an allowed action).

Set `requires_human = true` only when the correct action is beyond safe self-service:

1. **Bank dispute / chargeback already filed** — don't also refund; a human reconciles it.
2. **Legal / privacy request** — e.g. GDPR data-erasure. A human verifies and actions it.
3. **Unverifiable account recovery** — e.g. the *only* admin is locked out of MFA.

Everything else — normal refunds, plan questions, troubleshooting, logging a feature request —
is `requires_human = false`.

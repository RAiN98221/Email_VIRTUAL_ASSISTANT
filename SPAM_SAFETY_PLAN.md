# Email Sending Safety Plan

This plan turns the spam-risk discussion into implementation steps for the local CSV Email Assistant. The goal is compliance and sender-reputation protection, not bypassing provider filters.

## Goals

- Keep sending reviewable, rate-limited, and reversible.
- Reduce bursty or mechanical sending patterns.
- Stop automatically when the app sees signs of delivery trouble.
- Preserve source CSV files unchanged.
- Store all sending, suppression, and safety state in SQLite.

## Phase 1: Queue Guardrails

- Add a `daily_send_limit` setting per job.
- Add `interval_jitter_minutes` per job so the scheduler can vary the next send time.
- Enforce daily limits before each queued send.
- Show daily cap and jitter settings in the queue form.
- Show cap/jitter values in job cards.

Acceptance checks:

- Creating a job stores daily cap and jitter.
- Scheduler does not send once the job reaches its daily cap.
- Next pending item is scheduled with interval plus bounded random jitter.

## Phase 2: Suppression State

- Add a SQLite suppression table for emails that should not be sent again.
- Track suppression reasons such as `unsubscribed`, `bounced`, `complained`, and `replied`.
- Exclude suppressed recipients during preview and queue creation unless explicitly overridden by a future admin-only control.
- Add an endpoint to list suppressed contacts.
- Add a manual endpoint to suppress or unsuppress a contact.

Acceptance checks:

- Suppressed emails appear as invalid in preview.
- Suppressed emails are not queued.
- Manual suppress/unsuppress actions persist across restarts.

## Phase 3: Failure Classification And Auto-Pause

- Classify SMTP failures into temporary vs. hard failures.
- Mark likely hard bounces or policy blocks as suppression candidates.
- Add per-job `max_failures` and `auto_pause_on_failure` controls.
- Pause a job automatically when failures exceed the configured threshold.
- Store the pause reason on the job for UI visibility.

Acceptance checks:

- Temporary SMTP errors mark the item failed without suppressing the contact.
- Hard SMTP errors suppress the contact with reason `bounced` or `blocked`.
- Jobs auto-pause once the threshold is reached.

## Phase 4: Unsubscribe Support

- Add an unsubscribe token per queued recipient.
- Add a local unsubscribe endpoint that records `unsubscribed` suppression.
- Add unsubscribe link rendering for email bodies.
- Add `List-Unsubscribe` and `List-Unsubscribe-Post` headers when an unsubscribe URL base is configured.

Acceptance checks:

- Queue items include stable unsubscribe tokens.
- Visiting the unsubscribe URL suppresses the email.
- Future previews exclude unsubscribed contacts.

## Phase 5: Observability

- Add a safety summary endpoint for jobs.
- Show sent today, failures, suppressed count, cap status, and pause reason in the UI.
- Add logs for cap reached, suppressed recipient skipped, auto-pause, and unsubscribe events.

Acceptance checks:

- UI makes it obvious why a job is running, capped, paused, or completed.
- Logs include enough context to diagnose sending pauses without exposing email body content.

## Phase 6: Verification

- Add unit tests for database migrations and suppression behavior.
- Add scheduler tests for daily caps, jitter bounds, and auto-pause.
- Add API tests for queue creation and suppression filtering.
- Run the full test suite with the repo virtualenv.
- Do a non-destructive runtime smoke test that creates a queue item without sending real email.

## Implementation Order

1. Queue guardrails: daily cap and interval jitter.
2. Suppression table and preview filtering.
3. Failure classification and auto-pause.
4. Unsubscribe token, endpoint, and headers.
5. UI safety summary.
6. Tests and runtime smoke check.


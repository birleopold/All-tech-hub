# Phase 10 — Automation control center and recovery

Phase 10 adds operational control and evidence around LEOSOFT's durable automation engine. It does not create a second worker, replace the established systemd timer, change customer consent, or automatically replay failed social posts.

## Why this phase was needed

LEOSOFT already had durable jobs with:

- idempotency keys;
- bounded retry attempts;
- exponential retry delays;
- row-lock job claiming;
- stale-lock recovery;
- terminal success, failure and cancellation states.

The missing layer was operational visibility and controlled recovery. Before Phase 10, staff could not see one consolidated answer to:

- Is the timer still running?
- Is automation intentionally paused?
- Which job types are paused?
- Which jobs are due, retrying, stuck or permanently failed?
- Which worker claimed a job?
- What happened during the last timer cycle?
- Is a failed job safe to replay?
- Who paused, resumed, replayed or closed work?

Phase 10 addresses those questions without weakening the existing delivery safeguards.

## Staff control center

Authorised staff can open:

```text
/staff/reports/automation-control/
```

The page shows:

- master pause state;
- per-job-type pauses;
- pause reason and responsible staff member;
- latest worker heartbeat;
- latest run status and worker identity;
- consecutive failed or partial runs;
- queued, due, retrying, running and failed jobs;
- stale running locks;
- dead letters from the last 24 hours and all unresolved dead letters;
- recent worker-run history;
- strict integrity findings;
- append-only evidence for each job.

The page does not expose a button that immediately runs the worker. Worker execution remains controlled by the systemd timer or an explicit server management command.

## Permissions

Viewing the control center requires:

```text
automation.view_automationjob
```

Changing control state or recovering work requires:

```text
automation.change_automationjob
```

The standard `Manager` role receives project automation permissions when this command is run after migration:

```bash
python manage.py bootstrap_roles
```

Other staff roles do not automatically receive automation-control permissions.

## Master pause

A master pause stops the worker from:

- preparing due social-post deliveries;
- queueing saved-cart reminders;
- queueing stock alerts;
- processing scheduled customer campaigns;
- claiming or executing durable jobs.

The timer can continue to run and record a heartbeat while paused. It operates in inspection-only mode and records the run as `Paused`.

Staff must enter the exact phrase:

```text
PAUSE AUTOMATION
```

A reason is required and is written to the control record and staff audit log.

A pause does not terminate a job that is already running. Force-stopping an in-flight job could create duplicate external actions because the external platform may already have accepted the request.

## Per-job-type pause

Staff may pause one durable job type while allowing other work to continue:

- social posts;
- saved-cart emails;
- stock-alert emails.

For example, saved-cart reminders can be paused while copy is reviewed, without stopping stock alerts.

The pause-aware worker excludes paused job types when selecting the next due job. Existing queued jobs remain queued and preserve their original evidence.

## Resume

Staff must enter:

```text
RESUME AUTOMATION
```

Resuming `All automation` clears the master pause and every per-job-type pause. Resuming an individual job type removes only that type from the paused list.

## Worker heartbeat and run history

Every invocation of:

```bash
python manage.py run_growth_automation
```

creates an `AutomationRun` record and updates the singleton `AutomationControl` heartbeat.

The run records:

- timer/manual source;
- worker hostname and process ID;
- start and finish time;
- succeeded, partial, failed, paused or dry-run result;
- nested summary of due posts, growth jobs, customer campaigns and durable-job outcomes;
- unexpected command error, when applicable.

The default heartbeat window is 30 minutes because the existing systemd timer runs every 15 minutes:

```dotenv
ALLTECH_AUTOMATION_HEARTBEAT_MAX_AGE_MINUTES=30
```

A stale heartbeat is an integrity error unless the master pause is active. A master pause is shown as an intentional warning rather than a silent-worker failure.

## Stale job locks

The default stale-lock threshold is:

```dotenv
ALLTECH_AUTOMATION_STALE_JOB_MINUTES=15
```

A running job older than this threshold is recovered by the existing automation service:

- it returns to retry when attempts remain;
- it becomes failed when the maximum attempts were exhausted;
- the stale lock and worker ID are cleared;
- a `Recovered stale lock` event is appended.

A running job cannot be cancelled from the staff interface. Staff must first inspect the linked external or email evidence.

## Append-only job history

`AutomationJobEvent` records job transitions including:

- queued;
- claimed;
- succeeded;
- retry scheduled;
- failed;
- cancelled or reviewed closed;
- replayed;
- recovered from a stale worker lock;
- replay blocked.

Events include the actor when the action came from staff, the previous state, attempt count, worker identifier, message and additional metadata.

Historical jobs created before Phase 10 may not have a complete transition history. Their current durable-job record remains visible.

## Dead-letter review

A job becomes a dead letter when it reaches permanent `Failed` status.

Dead letters are treated as strict integrity errors until they are reviewed. The staff job page shows:

- job type;
- idempotency key;
- payload and stored result;
- attempt count;
- complete error;
- linked social delivery, where applicable;
- append-only transition events.

### Email-job replay

Failed or reviewed-cancelled saved-cart and stock-alert email jobs may be replayed after the underlying issue is corrected.

Staff must enter:

```text
REPLAY <job ID>
```

Replay:

- does not create a second job;
- preserves the idempotency key;
- clears the previous result and worker lock;
- resets the attempt count;
- returns the same job to the queue;
- records the old error in a replay event;
- writes a staff audit event.

The email executors still re-check whether the reminder or alert is currently required. A recovered cart, inactive subscription or already-sent reminder is safely skipped by the existing executor.

### Social-post replay is blocked

Failed Facebook or Instagram jobs cannot be replayed from the control center.

The external platform may have accepted the post even when LEOSOFT did not receive or store the final response. Automatically replaying could publish a duplicate.

Staff must:

1. Check the external Facebook Page or Instagram account.
2. Check the scheduled post and channel-delivery evidence in LEOSOFT.
3. Rebuild the scheduled post only when the external post does not exist.
4. Close the failed job with a clear review note.

A blocked replay attempt is itself recorded in the job and staff audit history.

## Closing reviewed failures

After review, a failed job can be closed with:

```text
CANCEL <job ID>
```

Closing changes the job to `Cancelled`, preserves the review reason, updates an unpublished linked delivery, and appends staff evidence.

This is different from deleting the job. The job, error, payload and history remain available for audit.

Succeeded jobs and already-closed jobs cannot be changed. Running jobs cannot be closed or cancelled.

## Manager notifications

A failed or partial automation run creates an in-app notification for:

- staff superusers;
- members of the `Manager` group.

The notification links to the control center. Individual retry events remain visible in the job evidence and staff audit log.

## Strict audit

Run:

```bash
python manage.py audit_automation_control --json
```

Strict gate:

```bash
python manage.py audit_automation_control --strict
```

The audit fails for:

- stale heartbeat while the master pause is not active;
- master pause without a reason;
- invalid paused job-type values;
- stale running jobs;
- running jobs without a lock time or worker ID;
- terminal jobs without a completion time;
- unresolved failed jobs;
- stale worker-run records;
- control state left `Running` beyond the stale threshold.

A dry worker run creates a heartbeat without queueing or sending anything:

```bash
python manage.py run_growth_automation --dry-run --limit 20
```

## Production health command

The existing operational health command now includes automation checks:

```bash
python manage.py check_operational_health --json
```

It reports:

- heartbeat freshness;
- stale running jobs;
- unresolved dead letters.

An intentional master pause produces a warning for heartbeat state, but stale locks and dead letters still fail the command.

## Database changes

Phase 10 adds migration:

```text
automation.0002_control_runs_job_events
```

It creates:

- `AutomationControl`;
- `AutomationRun`;
- `AutomationJobEvent`.

The migration does not execute jobs, retry failures, publish posts, send emails, pause automation or alter existing job status.

## Safety boundaries

- No web button directly executes the automation worker.
- A master pause affects future queueing and claiming; it does not force-stop uncertain in-flight work.
- Running jobs cannot be cancelled.
- Social-post replay is blocked.
- Email-job replay uses the existing job and idempotency key.
- All recovery actions require exact confirmation phrases.
- Control and job evidence pages are private, no-store and noindex.
- Django admin is read-only for automation control, runs, jobs and events.
- Dead-letter records are closed, never deleted.
- Existing customer-campaign send and scheduler kill switches remain independent from the Phase 10 operational pause.

## Emergency procedure

For a normal operational stop, use the staff control center and enter:

```text
PAUSE AUTOMATION
```

For a hard infrastructure stop:

```bash
sudo systemctl stop leosoft-marketing-posts.timer
sudo systemctl stop leosoft-marketing-posts.service || true
```

Then inspect:

```bash
sudo systemctl status leosoft-marketing-posts.timer --no-pager -l
sudo journalctl -u leosoft-marketing-posts.service -n 200 --no-pager
python manage.py audit_automation_control --json
```

Do not restart the timer while an external-action job remains `Running` or while a failed social-post job has not been checked against the external platform.

# Offline Job Queue When Glimpser detects that network connectivity is
unavailable, scheduled tasks are not executed immediately. Instead
`run_with_timeout` stores job details in the `OfflineJob` table so they can run
later. The database model defined in `app/models/offline_job.py` captures: -
`function` – full dotted path to the callable - `args` – JSON encoded arguments
- `timeout` – maximum runtime in seconds - `timestamp` – when the job was queued
`process_offline_jobs` runs every 30 seconds (via
`schedule_offline_job_processor`). It loads the queued entries, imports the
recorded function, and invokes `run_with_timeout` with the saved arguments.
Successful jobs are removed from the table. ![Offline Job
Sequence](images/offline_job_sequence.svg)

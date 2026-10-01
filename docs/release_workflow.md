# Release Workflow

Glimpser packages are generated automatically when a version tag is pushed to the repository.
The process is split across multiple runners:

- **Ubuntu** builds the Debian package and runs the test suite. The packaging
  script stages a clean source allowlist without local runtime data.
  It reads the version from `pyproject.toml`
  to populate the Debian control file so releases stay in sync.
- **Windows** builds the standalone executable using `build_windows.py`.
- The build sets `GLIMPSER_SKIP_DB_INIT=1` to prevent database access during analysis.
- It also skips the optional `onnxruntime` package to avoid lengthy dependency scanning.
- **macOS** builds a self-contained application with `build_macos.py`.

The Ubuntu job also generates a small `release-badges.md` file that lists
status badges for the current tag. This file becomes the body of the GitHub
release so that each tagged version shows the latest CI status.

The platform artifacts are attached to the GitHub release created for the tag. When the
`PYPI_API_TOKEN` secret is available, Python distributions are also published to
PyPI.

Tags are normally created automatically when the version in `pyproject.toml` is bumped
on the `main` branch. The `Tag Release` workflow runs
`scripts/auto_tag_release.py` to create a tag like `v0.2.9` and push it to
GitHub. It then explicitly dispatches the build jobs above. Before tagging, the workflow
runs `scripts/update_version_files.py` so that `CITATION.cff` and the fallback
version in `app/config.py` stay aligned with the version from `pyproject.toml`.

The tagging job uses `contents: write` to push the tag and `actions: write` to
explicitly dispatch `release-packages.yml` at that tag. A tag pushed with
`GITHUB_TOKEN` does **not** trigger another workflow's `push` event;
`workflow_dispatch` is an explicit exception. See
[GitHub's token event rules](https://docs.github.com/en/actions/concepts/security/github_token).
No personal access token is required.

Version detection reads `[project].version` with Python's TOML parser. It must
not match a separate `[tool.commitizen].version` or depend on whitespace.
Release scripts and the tagging runner use Python 3.11 or newer.

## Before a point release

1. Reconcile deployed source with the candidate Git commit. Include dependencies
   and regression tests for the fixes; exclude credentials, databases, captures,
   local backups, and machine-specific configuration. A healthy deployed service
   is not proof that GitHub contains the same code.
2. Run affected tests, required repository checks, and package builds against
   that exact candidate. Record remaining capacity or feed failures in the notes.
3. Update `[project].version` and the Commitizen version together; run
   `python scripts/update_version_files.py` and review the resulting diff.
4. Verify the version without creating a tag:
   `python scripts/auto_tag_release.py --print-version`.
5. Merge only the reviewed release candidate. The tagging workflow then dispatches
   package builds for the version tag. Verify the run and attached artifacts
   before announcing the release.

If tagging succeeds but the dispatch fails, rerun the tagging job. Existing tags
are left intact and the build dispatch is retried. To retry only packaging, run
`gh workflow run release-packages.yml --ref vX.Y.Z` for the intended existing tag.
A manual build on a branch validates builds but does not publish tag assets.

You can still trigger a release manually by creating and pushing a tag:

```sh
git tag v0.2.9
git push origin v0.2.9
```

Alternatively, run `scripts/auto_tag_release.py` to create and push the tag
for the current version automatically.

## Troubleshooting

If the GitHub releases page still shows an older version than the footer,
the tag may not have been pushed. Run `scripts/auto_tag_release.py` again
or push the tag manually to publish the release and update the page.

## Migrating optional event integrations

Native Knox motion events require `GLIMPSER_KNOX_CAMERAS`, a JSON object mapping
existing camera template names to exact hostnames or IPv4 addresses. For example,
`{"Entrance":"camera.example"}` enables only that template and host. Credentials
remain in the template; do not put credentials, URL paths, or ports in this map.
An empty or invalid map disables the subscriber.

Set `GLIMPSER_PRIVACY_GUARD_URL` to the installation's privacy-status JSON endpoint
when using the office kiosk privacy indicator. Without an endpoint, privacy is
reported as unknown and no request is sent.

Before upgrading an existing installation, preserve its event allowlist and
privacy endpoint in deployment configuration, then verify motion receipt and
fresh privacy status after restart. These settings intentionally have no
household-specific defaults in distributed source.

## Dependency and wheel checks

Use Python 3.11 or newer for the application; release validation
runs on Python 3.11 and 3.13. The security refresh includes
[urllib3 2.8](https://pypi.org/project/urllib3/2.8.0/) and
[Pillow 12.3](https://pypi.org/project/pillow/12.3.0/), which require Python 3.10.
Selenium must also be upgraded: the old 4.33 pin restricts urllib3 to 2.4.

Regenerate and commit `uv.lock` whenever dependency constraints change. Validate
with a clean environment (`uv sync --locked --extra google-events`), run the
complete Python suite and `pip-audit`, and inspect any skipped audit entries.
Glimpser itself is not available to audit on PyPI; source review and tests remain
necessary even when third-party dependencies have no reported advisories.

Build a wheel and install it into a separate environment. Run `glimpser --help`
from outside the source checkout so editable installs cannot hide missing wheel
modules. The wheel must contain `main.py` and `generate_credentials.py` as well
as the application assets. Keep build artifacts private until installation
configuration and source review are complete.

The optional agent tools use `gitlint-core`, the upstream-supported
[installation with looser dependencies](https://jorisroovers.com/gitlint/0.19.x/installation/).
The `gitlint` wrapper pins Click 8.1.3, which conflicts with the patched Click
minimum. The CLI remains `gitlint`.

## Session keys and clean packages

An explicit, nonempty `SECRET_KEY` remains unchanged. Missing keys and the old
known default are replaced with a random key stored alongside the configured
database in a mode-0600 `.session-secret` file. Preserve that file across
restarts and backup/restore; changing it invalidates existing login cookies.
Builds using `GLIMPSER_SKIP_DB_INIT=1` use an ephemeral key and never persist it.
Invalid persisted keys stop startup instead of silently rotating sessions.

Debian builds stage an explicit source/asset allowlist in a new temporary
folder. They do not copy `data/`, logs, environment files, session secrets, or
prior staging output. Native Windows/macOS builds remain separate CI jobs.
Source-level household identifiers still require removal before publication.


## Private household configuration

Set `GLIMPSER_HOUSEHOLD_CONFIG` to an absolute path outside the source checkout
containing installation-specific JSON. Restrict it to the service account
(mode `0600`), preserve it in private backups, and restart after changes.
Missing or invalid configuration disables household polling, presence scheduling,
vehicle telemetry captions, and identity aliases. Invalid settings produce a
warning without logging their contents or path.

A minimal synthetic example is:

```json
{
  "hub_url": "https://hub.example",
  "subjects": {
    "resident": {"label": "Example Resident", "location_device": "1"}
  },
  "presence_sources": [
    {"subject": "resident", "device": "1", "label": "Presence", "heartbeat_required": true}
  ],
  "arrival_cameras": ["Entrance"]
}
```

The hub URL must be an HTTP(S) origin without credentials, query strings, or
paths. Device IDs and subject keys are strings. A subject can additionally set
`gps: true` and a `location_identity` string. Enable GPS only for a source whose
coordinates are appropriate to display. Heartbeat-required sources must provide
fresh heartbeats; preserve that flag during migration.

Optional `location_aliases` entries contain `provider`, `label`, and a configured
`subject` key. Aliases apply only to the matching provider and label.
Optional `vehicle_caption` contains `camera`, `label`, `facts`, `device`, and
`network_device`; identifiers must match existing templates and hub devices.
Vehicle facts belong in this private file, never in distributed source.
Telemetry remains limited to allowed fields and freshness checks.

Before deploying this change to an existing installation, transfer its current
settings into the private file and configure the service environment. Verify
subject visibility, presence scheduling, and telemetry after restart. Do not
change intentionally disconnected or disabled camera templates as part of this
migration. Dashboard presets still need a separate installation-specific audit.


## External bridge refresh helper

The legacy-named `scripts/eufy_refresh_macmini.py` now requires `--profile NAME`.
It reads that external profile's existing bridge URL, authentication headers,
TLS verification setting, and devices path. It has no built-in network endpoint.
Update existing job commands before deploying; invoke it with the same Python
environment and configuration as the application. Only templates whose Eufy
profile matches the selected profile are considered. Disabled devices, failed,
stale, future-dated, or already imported frames retain their current capture.
An unavailable bridge produces no refreshes. Normal capture handles accepted
frames and maintains the usual deduplication and latest-image links.


## Private capture exceptions

`GLIMPSER_CAPTURE_POLICY` points to a private JSON file outside the checkout.
Restrict it to the service account (mode `0600`) and restart after changes.
Missing or invalid settings add no host exceptions. For example:

```json
{
  "variable_size_images": [{"host": "desktop.example", "path": "/Desktop.png"}],
  "hubitat_hosts": ["hub.example"],
  "admin_excluded_hosts": ["service.example"]
}
```

`variable_size_images` bypasses only the response-size variance backoff for the
exact HTTP(S) hostname and case-sensitive path, across ports and query strings.
Other capture validation still applies. `hubitat_hosts` enables local Dashboard
v2 handling for `/dashboard/ui/NUMBER`. `admin_excluded_hosts` excludes named
hosts from the generic LAN admin-page heuristic; explicit modem matching still
applies. Host entries contain no schemes, ports, credentials, or URL paths.
Before deployment, migrate existing exceptions into this file and set the
service environment so installation-specific tuning is preserved.


## Private dashboard membership

Set `GLIMPSER_VIEWER_CONFIG` to a private JSON file outside the checkout, readable
only by the service account (mode `0600`). Restart after changes. An example is:

```json
{
  "context_views": {"arrivals": {"Entrance": ["ExampleDoor"]}},
  "security_cameras": ["ExampleDoor"],
  "security_groups": ["security"],
  "systems_groups": ["systems"],
  "systems_prefixes": ["Hubitat"],
  "systems_cameras": ["ExampleStatus"],
  "regional_groups": ["regional", "weather"],
  "private_groups": ["private-site"],
  "rotation_review_holds": {"ExampleUnavailable": "Offline placeholder"},
  "quarantined_cameras": ["ExampleDuplicate"]
}
```

Context keys are `arrivals`, `property`, and `beach-conditions`; each maps section
labels to exact camera names. Unconfigured context views are empty. Security
uses exact camera membership or configured groups. Systems requires a matching
group plus a camera-name prefix or exact camera name. Group matching is
case-insensitive; camera names and prefixes are case-sensitive. Review holds
and quarantines affect presentation only, preserving capture jobs for repair.

Without configuration, Security uses the `security` group, Systems uses the
`systems` group and `Hubitat` prefix, and Regional uses `regional` or `weather`.
Regional always excludes private flags and the `private` and `archive` groups,
in addition to configured private groups and presentation holds. Security and
Systems now also exclude archived feeds.

Migrate existing memberships, private-group exclusions, and review holds before
deployment to preserve curated views. Room-specific landing profiles remain a
separate migration item; this setting does not replace their layout tuning.


## Private kiosk landing preferences

`GLIMPSER_LANDING_CONFIG` points to private JSON outside the repository. Keep it
mode `0600`, backed up privately, and restart after changes. Missing or invalid
settings use generic presets without named-camera preferences, presentation
exclusions, or automatic host mappings. Existing installations must migrate
these settings before deployment to preserve their kiosk layouts.

Top-level keys correspond to the named settings in `app/landing_defaults.py`.
Provided settings replace those defaults; `LANDING_CONTENT_PROFILES` replaces
only the supplied profiles and retains other generic profiles. Each supplied
profile must include its matching `key`, `label`, `short_label`, `scene_size`,
and `max_scenes`. Optional fields control lane weights, camera/group minimums,
scene/window caps, distributed groups, and rotation timing. Invalid numeric
bounds or incomplete profiles reject the whole file without logging its values.

For example, these settings select an existing generic room profile and reserve
priority handling for one explicitly named camera:

```json
{
  "LANDING_HOST_PROFILE_HINTS": [["example-kiosk", "office"]],
  "LANDING_HOST_MODE_HINTS": [["example-kiosk", "high"]],
  "LANDING_PRIORITY_CAMERAS": ["ExampleDoor"],
  "LANDING_PROFILE_EXCLUDED_CAMERAS": {"office": ["ExampleUnavailable"]}
}
```

Host mappings match a complete hostname or its first DNS label, case-insensitively;
substrings no longer select a profile. Explicit URL profile/mode choices take
precedence. The legacy `hal` profile key remains compatible with bookmarked URLs
but is labeled Workstation by default and has no host or camera associations.
The `priority` group continues to opt a camera into priority handling.
Generic presets preserve layout sizes and timing; they do not reproduce an
installation's named-feed selection. Verify scene membership, rotation,
priority events, and exclusions on each kiosk after applying the migration.


## Debian installation and upgrade behavior

Both the direct package builder and debhelper rules stage the same source
allowlist. The package installs its unit in `/lib/systemd/system`; local unit
overrides belong in `/etc/systemd/system/glimpser.service.d/`.

Configuration creates a dedicated `glimpser` system account and an isolated
`/opt/glimpser/.venv`. It bootstraps the exact uv version in `uv.lock`, then uses
`uv sync --locked --no-dev --no-editable --extra google-events`. The distribution's
Python packages are never overwritten. Installation requires network access to
the configured Python package index or a populated cache. A failed dependency
installation prevents service activation and leaves the package unconfigured.

Source and dependencies stay root-owned. Runtime data and logs under
`/opt/glimpser`, plus `/var/lib/glimpser`, belong to the service account. Existing
runtime data is retained and its ownership migrated from older root-run installs.
The service loads optional environment settings from `/etc/glimpser/environment`;
private JSON files referenced there must also be readable by `glimpser`. Preserve
explicit external database/media paths and grant access before upgrading.
Review existing local unit overrides: a legacy unit in `/etc/systemd/system`
can shadow the new vendor unit, so migrate intentional overrides to a drop-in.

Service activation uses Debian's policy-aware helpers and preserves the saved
enablement choice. Removal stops the service; purge clears helper state but
retains runtime data and the service account. No uninstall action deletes
captures, configuration, databases, or session keys. Back these up before an
upgrade or rollback. Restore the previous package and its matching private
configuration if startup fails; schema compatibility still needs checking.

Maintainer-script tests run in isolated mount/network namespaces with mocked
system commands. They check lock installation, failure ordering, abort handling,
and service policy calls. These tests do not substitute for a fresh-install and
upgrade trial in a disposable Debian VM with real systemd and dependencies.


## Required secret scanning and Eufy device identity

The development dependency lock now includes `detect-secrets`. The hook fails
when that dependency is missing; a skipped scanner is not a successful audit.
The baseline contains reviewed test-only literals and public vendor/protocol
constants. Review new findings individually; never regenerate the baseline to
silence an unexplained credential. A scanner pass does not establish that
source, images, fixtures, or repository history contain no personal data.

Eufy native requests now derive a stable device identifier from the installation's
persisted session secret. Existing native installations can retain their previous
identifier with `GLIMPSER_EUFY_OPENUDID` (exactly 16 hex characters) in private
service configuration. Preserve that override before deploying if device
registration must remain unchanged. Rotating the session secret also changes the
derived identifier unless an override is set. External bridge profiles are
unaffected. Invalid overrides fail without printing their value.


## Private camera census locations

`GLIMPSER_SITE_LOCATIONS` points to a private JSON list outside the checkout.
Use mode `0600` and service-account ownership. Without a valid file the census
helper does not infer household addresses or coordinates. Explicit template
coordinates and locations parsed from the source URL continue to work.

```json
[
  {
    "groups": ["example-site"],
    "url_prefixes": ["sdm://example-site/"],
    "label": "Example Site",
    "latitude": null,
    "longitude": null,
    "accuracy": "site",
    "private": true,
    "evidence": "Operator-configured site; coordinates not yet measured"
  }
]
```

At least one group or URL prefix is required. Selectors match case-insensitively;
URL prefixes preserve the legacy prefix behavior, so make them specific to the
intended sources. They must not contain credentials, query strings, or fragments.
Coordinates must be a finite latitude/longitude pair in geographic bounds, or
both null. Site locations default to private, and invalid settings disable all
seed inference without logging addresses or coordinates. Seed metadata does not
overwrite a complete coordinate pair already recorded on a camera.

Preserve the existing seed list in this file before running a census after the
upgrade. No census or database rewrite occurs merely by loading these settings.
The notes-refresh helper now uses generic `retail` and `private` categories,
instead of installation-specific site aliases. Before using it on older feeds,
review their category tags and recorded view descriptions; preview its output
before applying changes. Generated wording no longer assumes an Eufy camera is
at a beach house or that a marine view is on a particular lake.


Kiosk live camera membership is installation configuration, not a JavaScript
allowlist. Add `kiosk_live` to the private `GLIMPSER_VIEWER_CONFIG` JSON, keyed by
camera name. Each value supports `provider` (`stream` or `google`), `label`,
`profile` (`main` or `sub`), `quality` (`auto` or `kiosk`), and optional
`source_fps` (positive, at most 120). For example:

```json
{"kiosk_live":{"ExampleDoor":{"provider":"stream","label":"Entrance","profile":"main","quality":"auto","source_fps":1}}}
```

Missing settings retain saved captures. Preserve verified camera choices in
private configuration before deploying this candidate; restart after changing
configuration. Only display and stream-selection fields reach the authenticated
landing page. Never put credentials or source URLs in these settings.


The same private viewer file supports `priority_handoffs` (destination camera to
allowed approach camera names), `security_approaches` (camera name list),
`dashboard_group_order` (ordered group tags), and `preferred_areas` (dashboard
key to section label). These preserve installation-specific grouping and alert
transitions without embedding household names in published assets. For example:

```json
{"priority_handoffs":{"ExampleDoor":["ExampleApproach"]},"security_approaches":["ExampleDoor"],"dashboard_group_order":["plants","weather"],"preferred_areas":{"arrivals":"Entrance"}}
```

No handoff occurs without an explicit rule. Existing priority, freshness,
duplicate-event and forward-time checks still apply. Handoff settings reach only
priority-enabled landing profiles and reference only cameras in their inventory.
Preferred areas are returned only when that area exists in the filtered dashboard.


Add installation-specific stale-feed tags to `archived_groups` in the private
viewer file, for example `{"archived_groups":["site-one-stale"]}`. These aliases
augment `archive` and `source-stale` for both runtime and detailed camera health
reports and the caption-backfill helper. Preserve legacy aliases before deploying;
this configuration does not rewrite tags or enable capture jobs. Restart services
after configuration changes. Caption backfill also skips `expected-offline` feeds
by default, even when their recorded failure/offline timestamps are empty.


Private capture policy also supports `caption_detail_cameras` (exact names) and
`caption_detail_prefixes` (case-sensitive prefixes). Matches use 1024-pixel
caption inputs; other cameras use 512, while Hubitat device dashboards retain
1536 for readable measurements. Preserve existing detail choices before deploying.
`dashboard_camera_labels` maps exact camera names to display labels for embedded
Hubitat captures. Labels are passed as browser-script arguments, not executable
source; only names in the current camera inventory are passed.

The private viewer file supports `timelapse_groups`, an ordered-independent list
of camera group tags eligible for history. Default tags are `marine`, `grower`,
and `traffic`; existing URL, coordinates, event-buffer, archive, failure and
operational-screen checks still apply. Preserve installation-specific tags before
deploying. Neither setting changes capture schedules or camera state.

Caption policy version 5 recognizes the shipped legacy default prompt at runtime
and replaces its contradictory unchanged-frame rule with the concise default.
Custom operator prompts remain intact. The model describes one current still;
missing current images cannot silently fall back to an older observation. Readable
uncertainty (including “cannot read”) remains a valid caption; UNREADABLE, missing
input/configuration errors and recognizable refusals preserve the previous caption
without advancing its timestamp.

Both caption-cache identities include a stable fingerprint of the prompt, model,
evidence guidance and capture tuning. Policy changes invalidate reuse without
including the moving wall clock in cache keys. Normal scheduler cadence controls
regeneration; this change does not launch a fleet-wide backfill.

Hubitat Main captions require recognized device-card geometry at 1600×900 or
1920×1080. Aligned cyan card rails identify the device region as card counts change;
unrecognized layouts fail closed, excluding embedded camera thumbnails. Test new
layouts before enabling other sizes/styles. Validation covered saved 1920×1080
layouts with device grids beginning around y=636 and y=490. Private audit images
and site labels are not included in release packages.

Stream captures now own a unique temporary burst directory for every invocation,
including overlapping captures of the same feed. Normal completion and failure
remove that directory. A selected frame is processed and timestamped in a private
staging file beside the destination, checked for PNG integrity, then published
with an atomic replace. Rejected frames and processing/write failures preserve
the previous published image. Stabilization still looks up history beside the
real destination. This protects readers from partially written frames; it does
not provide power-loss durability or remove files left by a forcibly killed worker.

Hardware-decoder fallback shares the current transport attempt's monotonic
deadline. It starts only while time remains, clears frames from the failed decoder,
and cannot gain another full attempt timeout. Stream decoders disable interactive
stdin handling. Existing preflight and transport budgets are unchanged; this is
not a single deadline for the entire capture pipeline.

Stream metadata preflight now requires a video stream with codec metadata; an
empty or malformed successful ffprobe response no longer passes. The probe
requests geometry and frame rate for the existing capture tuning. Unknown or
zero frame rates do not activate the low-FPS burst cap. Successful metadata
inspection skips the redundant null decode probe; when enabled, that probe
remains a fallback and explicitly requires video. The actual capture still
validates decoded frames before publication. Slow-camera startup budgets remain
unchanged.

The private viewer configuration accepts `status_groups`, an ordered list of
group tags for the System Glimpse summary. Generic defaults contain service and
camera categories only. Preserve an installation's existing list in its private
viewer file before rollout; group selection does not enable feeds or alter
expected-offline exclusions.

For 0.2.10, preserve `navigation_groups` and `google_live_cameras` in the private
viewer file. Live token issuance still checks authentication, the explicit camera
allowlist, and the camera's private flag. The capture policy supports
`slow_rtsp_cameras` for the existing longer software-decoder warmup profile and
`admin_hosts` for explicit local admin-page handling. These settings have no
installation-specific defaults. Private migration files must not be committed or
included in release artifacts.

The release candidate also removes browser-local password storage. Remember-me
uses the server's signed cookie; opening the login page clears legacy stored
credentials. Caption and cost table values render as text. Stream filters and
clip durations are validated before capture work; recovery previews and shortcut
updates are restricted to their intended files. Camera XML rejects entity
expansion, URL credentials use structured parsing, and TLS probes explicitly
require TLS 1.2 or newer. Site-specific capture behavior matches DNS hostnames,
not arbitrary URL substrings. The optional Codex bridge defaults to loopback,
requires a token for remote exposure, and confines file browsing to its workspace.

Node tooling is pinned through the committed lockfile and installed with `npm ci`.
The Debian package declares the build dependencies needed by its locked input
capture library; the disposable systemd installation test installs the declared dependencies in its base image before
checking install, upgrade, and removal behavior under the service manager.

Security review boundaries: camera creation, recovery, and URL probing are trusted
operator functions that intentionally fetch operator-selected network sources,
including LAN cameras. Keep login enabled; explicitly configured full-access LAN
subnets have operator privileges. Read-only guests cannot invoke URL probing or
POST capture configuration. Public URL checks reject private resolved addresses,
and the URL test does not follow redirects. These checks are not a sandbox for
untrusted tenants; DNS rebinding and downstream camera/browser redirects require
network-level egress isolation in such a deployment.

Temporary API links use HMAC-SHA256 with constant-time verification. Links issued
by the previous digest implementation must be regenerated after rollout. Camera
protocol SHA1/MD5 challenge responses remain for ONVIF/RTSP interoperability;
these are protocol responses, not the application's password storage. Image
change detection hashes image bytes only. Validation errors deliberately return
field-specific messages, while unexpected upstream errors return generic text.

Python source archives use an explicit source allowlist as well as runtime-file
exclusions; release CI inspects both the wheel and source archive for databases,
secret files, capture data, and dependency caches. Native binaries start at
`main.py`, retain Flask's `app/templates` and `app/static` layout, and must report
the expected version in a timed smoke test before upload. Windows uses exclusive
byte-range locks for capture coordination; POSIX retains `flock`. Both native
runners test lock contention and release before building.

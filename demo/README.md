# Agency V2 guided public demo

An isolated static recovery walkthrough with three additional fictional purchase cases. `build.py`
runs the existing V2 deterministic coordinator and exports its results; browser
interaction selects these precomputed results. No live models, sign-in, provider
connections, personal records, forms, analytics or persistent browser storage.
This does not promote experimental V2 or expose the private BFF.

## Reproduce and verify

From the repository root:

```bash
python3 demo/build.py
python3 demo/build.py --check
node --check demo/app.js
PYTHONPATH=poc/v2 python3 -m unittest discover -s poc/v2/tests -p 'test_coordinator.py'
```

The cases expose overlapping bank exports, conflicting duplicate amounts, and
a missing receipt. They retain uncertain possession and never execute writes.
The public UI is a guided simulation, not a live runtime benchmark.

## Hetzner handoff

Use a separate checkout at a reviewed release commit. Do not modify the existing
MCP/BFF Compose project. No secrets are required. From this checkout:

```bash
docker compose -f demo/compose.yaml config --quiet
docker compose -f demo/compose.yaml up -d --build
curl --fail --head http://127.0.0.1:8092/
```

Port 8092 is loopback-only. Before running, confirm it is unused. The image copies
only four public assets. The existing HTTPS proxy or tunnel must route the
confirmed public demo hostname to this service. For a host proxy that target is
`http://127.0.0.1:8092`. A containerized proxy has a different network context:
inspect the existing topology before configuring it; do not assume its localhost
is the host. Do not expose a Docker daemon or publish the private BFF routes.

Verify external HTTPS, all three interactions, fresh/reloaded sessions, and
mobile/Instagram in-app rendering before announcing. Confirm `/auth/`, unknown
paths and deployment/source files return 404. Record the exact deployed commit,
resolved image digest, HTTPS result, browser checks and rollback reference in
the canonical development roadmap without credentials or private addresses.

Rollback this demo only:

```bash
docker compose -f demo/compose.yaml down
```

Then remove/restore only its dedicated proxy route. Existing infrastructure is
unaffected. Docker and public HTTPS verification remain pending until performed
in an environment with Docker and authorized VPS access.

## Recovery walkthrough

The lead story is now a scripted, entirely fictional recovery-support concept.
Mood is one tap with Skip/Undo; energy independently changes only optional chores.
The care-plan card never changes. Help requests are previews, never sent.
Sound uses a local Web Audio oscillator after opt-in; no audio service is called.
Selections use page memory only, with no persistence, telemetry or remote AI.
The existing three coordinator-generated purchase scenarios remain in a disclosure.
Safety and privacy explanations are on-page. They are not medical-device or GDPR
certifications. Infrastructure logging/retention and a full operator privacy notice
remain separate operational work before collecting any real health information.

For a tunnel-connected deployment, retain the local Compose network override and
include it in all update and rollback commands:

```bash
docker compose -f demo/compose.yaml -f demo/compose.tunnel.yaml up -d --build --wait
```

The override is private deployment configuration, not a public repository file.
Rollback by checking out the previous release commit and running the same command.

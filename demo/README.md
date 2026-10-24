# Agency V2 guided public demo

An isolated static recovery walkthrough with three additional fictional purchase cases. `build.py`
runs the existing V2 deterministic coordinator and exports its results; browser
interaction selects these precomputed results. No live models, sign-in, provider
connections, personal records, forms, analytics or persistent browser storage.
This does not promote experimental V2 or expose the private BFF.

## Languages and video production

English (default), Dutch and Bulgarian use shared templates and checked translation
catalogs. See [LOCALIZATION.md](LOCALIZATION.md) for translation exchange, adding a
language, and the narration/captions/on-screen-text production workflow.

## Reproduce and verify

From the repository root:

```bash
python3 demo/build.py
python3 demo/build.py --check
node --check demo/app.js
python3 demo/localize.py check
python3 -m unittest discover -s demo/tests -p 'test_localization.py'
node demo/tests/test_runtime.mjs
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

Port 8092 is loopback-only. Before running, confirm it is unused. The image copies only public assets explicitly allowed by the Nginx configuration. The existing HTTPS proxy or tunnel must route the
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

## Mobile framing and public persona

On narrow screens, the brand wordmark and subtitle are **separate from the
photograph** so they cannot cover the lifted girl's head. The same approved
panoramic hero image is centred on the four central family members, with the
young boy toward the middle and a gentle edge fade to avoid a hard cut through
other relatives. The existing mobile-crop asset remains in the image for
possible future use, but the hero intentionally uses the panorama on phones.

The original artwork itself ends at the subjects' lower legs. A web crop cannot
restore those missing feet; a future genuinely full-body version requires a
separate, approved artwork revision. This change does not regenerate faces or
change the desktop image.

**Gunter** is the canonical *fictional demo persona* for the public recovery
walkthrough. Use this spelling consistently in public prose and example labels.
Gunter is not the visitor and is not presented as a real case, personal record,
or connected service. The finance cases remain separate fictional fixtures.

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


## Brand-first family homepage

The public demo now begins with the stoqnist. brand, a subdued panoramic family
illustration, a short bridge into the idea, and the original fictional recovery
and purchase walkthroughs. `brand-journey.css` is a small, scoped design layer.
It does not change the V2 coordinator, mock evidence or server infrastructure.

**Before publication:** two approved WebP images still need to be committed
to this same branch. They are included in the user's guided-discovery V2 ZIP:

- `demo/assets/stoqnist-family-hero.webp` — desktop banner (2172 × 724).
- `demo/assets/stoqnist-family-mobile.webp` — mobile crop.

The public Docker image automatically includes WebP images in `demo/assets/`.
The Nginx whitelist only serves these two named images and the existing
`everyday-room.webp`. Until the image files are committed, desktop falls back
to the previous branded SVG banner; mobile shows a forest-green branded hero.
**Do not merge or deploy as the finished family design with assets missing.**

Confirm permission to publicly publish recognizable family members' likenesses,
especially the images involving children, before publishing. The site remains a
fictional demo, not a live connected or medical service.

### VPS update after review and branch merge

Use only the existing `agency-guided-demo` checkout and preserve the private
tunnel override. Do not update the separate `stoq-infrastructure` stack.

```bash
cd /opt/agency-guided-demo
git status --short
git branch --show-current
git fetch origin
git switch feat/weekend-guided-demo
git pull --ff-only origin feat/weekend-guided-demo
test -f demo/compose.tunnel.yaml
docker compose -f demo/compose.yaml -f demo/compose.tunnel.yaml config --quiet
docker compose -f demo/compose.yaml -f demo/compose.tunnel.yaml up -d --build --wait
docker compose -f demo/compose.yaml -f demo/compose.tunnel.yaml ps
curl --fail --head http://127.0.0.1:8092/
curl --fail --head https://stoq.page/
```

These commands assume a clean local checkout. Do not force-reset or remove
untracked files, especially `demo/compose.tunnel.yaml`. Record the old release
commit before switching, and roll back only this demo if validation fails.

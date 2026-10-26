# Localization: English, Dutch and Bulgarian

English is the source language and `/` is always English. Dutch is `/nl/`; Bulgarian
is `/bg/`. Links make the choice shareable and work without JavaScript. There is no
browser-language redirect, cookie, local storage or health-choice persistence.
Switching language reloads the story and keeps the current section anchor.

## Edit and validate

- `templates/index.html`: shared layout; every visible phrase and accessibility label
  comes from a message key. `index.html`, `nl/index.html`, `bg/index.html`, locale
  JavaScript bundles, Dockerfile, Docker context and locale routes are generated.
- `locales/en.json`: canonical wording, including demo results, video narration,
  captions, phone-screen wording and end cards.
- `locales/nl.json` and `locales/bg.json`: translated wording with per-message source
  fingerprints. These initial translations are drafts, not a claim of native-speaker
  or legal review. The `review` field records editorial status separately from
  technical completeness. Review policy/health language with the appropriate editor.
- `locales/registry.json`: native language names, enabled locales and English default.
- `cases.js`: unchanged deterministic evidence. Translated cards use catalogued
  source statements. Technical JSON deliberately retains original keys, identifiers,
  and English source wording, with an explanation and `lang="en"`.

```sh
python3 demo/localize.py report
python3 demo/localize.py build
python3 demo/localize.py check
python3 -m unittest discover -s demo/tests -p 'test_localization.py'
node demo/tests/test_runtime.mjs
```

Edit the English source first. Export the target translation packet; it identifies
missing and stale messages. Translate or review changed entries, then import them.
The import verifies the source fingerprint and placeholders before updating the
catalog. It does not automatically certify editorial review. Never refresh hashes
without checking the meaning. Translation packets are UTF-8 JSON, suitable for a
translator, a translation service or an AI-assisted draft followed by review.

```sh
python3 demo/localize.py export nl /tmp/stoq-nl.json
# Edit translation fields; you can keep only reviewed entries for a partial import.
python3 demo/localize.py import nl /tmp/stoq-nl.json
python3 demo/localize.py build
```

Missing/empty enabled translations, stale source fingerprints, placeholder mismatches,
new uncatalogued coordinator prose, and stale generated files fail the build/CI.
Localized currency uses `Intl.NumberFormat`; currency stays EUR. Proper names, IDs
and technical source JSON are not translated. No translation HTML is executed.

## Add a language on demand

```sh
python3 demo/localize.py add pt --name Português
python3 demo/localize.py export pt /tmp/stoq-pt.json
# Translate the packet, including all film.* messages.
python3 demo/localize.py import pt /tmp/stoq-pt.json
# Set enabled: true for pt in locales/registry.json.
python3 demo/localize.py build
python3 demo/localize.py check
```

Use `pl` / `Polski`, `ro` / `Română`, or another registered BCP 47-style code.
For Portuguese, choose `pt` for a general edition or `pt-PT` for an explicitly
European Portuguese edition. The script adds a disabled locale and planned film
variant first. Enabling it automatically generates links, canonical/hreflang tags,
static pages, runtime bundles, Docker copy rules and narrow nginx routes. It needs
no page-code change. Run the tests and open a feature PR against
`feat/weekend-guided-demo`; merge/deployment remain separate release actions.

## Video localization pipeline

`media/gunter-morning.json` is the first film manifest. The scripts follow the local
Gunter film v3: he reviews a request before sending, and there is no reply yet.
The public Gunter story includes an approved English master. Dutch and Bulgarian
currently display that same English movie with translated WebVTT cues
aligned to the English master’s timings, a local-language transcript, and an
explicit original-audio notice. Subtitle readability on actual devices and
native-speaker editorial review remain required release checks.
These are **captioned fallbacks**, not Dutch- or Bulgarian-dubbed releases. The
English movie has some embedded English labels; native localized movie assets
must be reviewed separately before their variants can be marked ready.

1. Localize all `film.*` strings: spoken narration, editorial captions, phone UI,
   disclosure and end card. Keep the artwork free of baked-in language. Export one
   production packet per locale:

   ```sh
   python3 demo/localize.py video-export nl /tmp/stoq-film-nl
   ```

   This writes `production.json` (scene IDs, translated text, screen strings, content
   hash), `narration.txt`, `timings.json`, and a **provisional** WebVTT file. Give this
   packet to the voice/film renderer. The prior local film renderer still has Dutch
   text baked into its graphics; consume these screen strings when rerendering it.
   This repository does not automatically synthesize voices or render movie binaries.

2. Record or synthesize a suitable voice, render the translated screen graphics and
   movie, then adjust `timings.json` to the final recording. The timing sheet must
   retain the locale/content hash and one ordered, non-overlapping spoken cue per
   scene, within the rendered duration. Split long narration into shorter scenes if
   needed for subtitle readability. Editorial captions are distinct from spoken
   subtitles: the exported VTT contains the actual narration, not the shorter slogans.

   ```sh
   python3 demo/localize.py video-export nl /tmp/stoq-film-nl-final --timings /tmp/stoq-film-nl/timings.json
   ```

3. Review pronunciation, Cyrillic/font coverage, phone-screen line breaks, subtitle
   timing, on-screen wording, disclosure and the final audio on mobile. Copy approved
   assets to `demo/media/gunter-morning-nl.mp4`, `.vtt`, and optionally `.webp`.
   In the variant set `status` to `ready`, the asset paths (starting `/media/`),
   `audioLocale` to `nl`, `timingStatus` to `final`, and `sourceRevision`/`contentHash`
   from the exported production packet. Build and check again.

A ready variant is selected by page language. Captioned fallback is explicit:
set the target variant to `captioned`, supply final translated captions timed to
that fallback movie, and map e.g. `fallbacks.bg` to `nl`. The UI identifies the
actual audio language. Planned/missing media never silently pretends to be dubbed.
Film content edits invalidate approved hashes until the video/captions are reviewed
again. Assets must exist and captions must contain each localized spoken scene.

CI tests the served routes and asset boundary in the real nginx container. Only
approved media files enter the Docker image; manifests, catalogs, translation
packets and source templates remain inaccessible from the public site.

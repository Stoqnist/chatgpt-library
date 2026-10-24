# stoqnist. service website — guided discovery (review candidate)

This folder contains a standalone, static homepage concept for the public-facing **stoqnist.** service. The repository's V2 agent architecture and canonical Library publisher remain separate. This website is **not** an activation of experimental V2 features and is **not** the owner's CV site.

## Experience
The visitor encounters the brand and subtitle first, then a restrained family image, a bridge into the service idea, three keyboard-accessible illustrative example journeys, and the principles of clarity and user control.

## Local preview
Open `index.html` or use `python3 -m http.server 8000` from this folder. No build tool, analytics, network calls, or external fonts are required.

## Images: still to be added
The two original **approved imagery files** are in the separately supplied prototype ZIP and were **not transferred to GitHub** by the integration. Place them unchanged at:
- `website/assets/stoqnist-family-hero.webp`
- `website/assets/stoqnist-family-mobile.webp`

Desktop expects a 3:1 panoramic image. The mobile asset presents an intentional crop. Without these files, the page shows a dark brand-first fallback, so the review branch can be inspected without a broken public image. The artwork must be verified against the approved design before release.

## Publication gates
- Confirm rights and permissions to publish recognizable family likenesses, particularly minors, before including the artwork in a public deployment.
- Review the content and illustrative capability disclaimers against currently implemented V2 functionality; experimental workflows must not be presented as live.
- Verify contrast, mobile crop, keyboard navigation, reduced-motion behavior, and image loading.
- Establish and verify the actual `stoq.page` deployment connection (GitHub Pages, VPS, or another host); none is configured by this branch.
- Merge/deploy only after review. No changes to `library/`, its publisher allowlist, V1 behavior, or V2 experimental runtime are intended.

A static source integration does **not** make the website live.
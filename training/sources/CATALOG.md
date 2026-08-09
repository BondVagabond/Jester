# Requested Source Catalog

This file tracks the requested fantasy/mythology, SRD, and CC source additions.

Status legend:

- `enabled`: checked in as an approved manifest and eligible for runtime collection.
- `cataloged`: checked in as a source manifest but currently outside the active runtime path.
- `review-gated`: requested source recorded here, but not enabled site-wide because the current domain scope is mixed-license, unclear, or needs narrower path/item manifests.

## Public Domain Fantasy & Mythology

| Source | Status | Notes |
| --- | --- | --- |
| Project Gutenberg | enabled | Scoped to ebook catalog pages; treat as US public-domain corpus only. |
| Internet Archive | review-gated | Domain scope is mixed-rights; needs collection-specific manifests. |
| Sacred Texts | review-gated | Catalog includes both public-domain and restricted materials. |
| Perseus Digital Library | review-gated | Needs source-level review for edition/translation scope. |
| LibriVox | enabled | HTML catalog text only; audio binaries remain out of scope. |
| Theoi Greek Mythology | review-gated | Site-wide rights need review before approval. |
| MythologySource | review-gated | Site-wide rights need review before approval. |
| Global Grey eBooks | review-gated | Public-domain intent is strong, but item/premium split needs narrower manifests. |
| Open Library (public-domain items) | review-gated | Catalog metadata is open; full-text content is mixed and must be item-scoped. |
| Bartleby | review-gated | Site-wide rights need review before approval. |

## SRD / Open Game Content

| Source | Status | Notes |
| --- | --- | --- |
| 5e SRD (dnd5e.info) | enabled | OGL 1.0a; retrieval-only under current policy. |
| Open5e | enabled | OGL 1.0a; retrieval-only under current policy. |
| SRD 5.1 (Wizards of the Coast) | enabled | Official CC BY 4.0 PDF manifest now routes through the canonical PDF runtime path. |
| 2025 5e SRD page-scoped websites | enabled | Added 20 exact-page CC BY 4.0 website manifests across Open Gaming Network and D&D Wiki to exercise the canonical HTML crawler without broad mixed-license domain scope. |
| d20 SRD | enabled | OGL 1.0a; retrieval-only under current policy. |
| Pathfinder SRD | review-gated | Needs exact current source/license scoping before approval. |
| Archives of Nethys | review-gated | Needs explicit scope review against Paizo community-use constraints. |
| Basic Fantasy RPG | review-gated | Likely approvable, but current HTML source scope needs a narrower manifest. |
| OSRIC SRD | review-gated | Needs exact current host/license/source path confirmation. |
| Labyrinth Lord SRD | review-gated | Needs exact current host/license/source path confirmation. |
| Swords & Wizardry SRD | review-gated | Needs exact current host/license/source path confirmation. |

## Creative Commons / Open Access

| Source | Status | Notes |
| --- | --- | --- |
| Wikipedia | enabled | CC BY-SA 4.0 with article-namespace path filters. |
| Wikimedia Commons | review-gated | Per-file licensing is mixed; requires asset-level manifests. |
| Wikisource | enabled | CC BY-SA contributor text with title-level provenance still required at export time. |
| OpenGameArt | review-gated | Per-item licenses vary; requires item-level manifests. |
| ccMixter | review-gated | Per-item licenses vary; requires item-level manifests. |
| Open Library (CC works) | review-gated | Requires item-level manifests for CC-scoped content. |
| DOAB | review-gated | Per-book licenses vary; requires collection/item scoping. |
| Open Textbook Library | review-gated | Per-book licenses vary; requires collection/item scoping. |
| Europeana | review-gated | Rights statements vary by item; requires item-level manifests. |
| Smithsonian Open Access | enabled | CC0-scoped HTML metadata/object pages only. |

## Manifest Notes

The enabled manifests now track:

- exact `license` values
- `license_url`
- `attribution_required`
- `attribution_text`
- `share_alike_required`
- scoped URL filters via `allowed_path_prefixes` and `blocked_url_patterns`
- artifact locators via `artifact_path` and `artifact_urls`

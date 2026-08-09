# Licensing And Rights Rules

## Allowed License Values

- `owned`
- `license-grants-training`
- `license-grants-retrieval`
- `cc0-1.0`
- `cc-by-4.0`
- `cc-by-sa-4.0`
- `public-domain`
- `user-consent`
- `all-rights-reserved`
- `contract-restricted`
- `unknown`

## Allowed Rights Basis Values

- `owned-by-jester`
- `explicit-training-license`
- `explicit-retrieval-license`
- `open-license`
- `public-domain`
- `user-opt-in`
- `internal-use-only`
- `contract-restricted`
- `unknown`

## Training-Safe Rights Matrix

`training_and_retrieval` is allowed only when both the license and the rights basis are training-safe.

Training-safe combinations:

- `owned` + `owned-by-jester`
- `license-grants-training` + `explicit-training-license`
- `cc0-1.0` + `open-license`
- `cc-by-4.0` + `open-license`
- `cc-by-sa-4.0` + `open-license`
- `public-domain` + `public-domain`
- `user-consent` + `user-opt-in` after explicit consent and redaction review

`retrieval_only` is allowed for:

- `license-grants-retrieval` + `explicit-retrieval-license`
- internal workspace use with `user-consent` + `internal-use-only`
- copyrighted third-party material where use is approved only for retrieval

`neither` is mandatory for:

- `unknown` license or rights basis
- `all-rights-reserved` without explicit retrieval permission
- `contract-restricted` sources that do not permit the intended downstream use
- disputed or removal-requested content

## DND-Specific Policy

- Official commercial DND books, adventures, and proprietary PDFs are not training-eligible by default.
- SRD or similarly open releases may be training-eligible only when the manifest cites the exact open license.
- Fan transcripts, fan wikis, play reports, and blog posts are retrieval-only unless a written training license exists.
- If rights are unclear, the source is quarantined. "Probably fine" is not an allowed policy state.

## Attribution And Share-Alike

- Attribution obligations must be recorded in the source manifest.
- Share-alike obligations must be surfaced in the dataset manifest before export.
- If the team cannot satisfy attribution or reciprocal terms, the source cannot be marked training-eligible.

## Collection-Time Capture

At collection time the system must store:

- manifest id
- final URL or file path
- owner label
- collection date
- license
- rights basis
- robots result for crawled sources
- content hash

## Hard Failures

- Do not infer a training right from public accessibility.
- Do not infer a training right from robots allow.
- Do not infer a training right from a retrieval-only approval.
- Do not infer a training right from prior local storage.

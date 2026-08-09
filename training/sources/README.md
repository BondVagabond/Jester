# Source Manifests

Approved source manifests live in `approved/`.

Requested-source catalog and rollout status live in `CATALOG.md`.

Checked-in candidate source review records live in `candidates/`.
Runtime-created candidate review artifacts now default to `F:\JesterData\candidate_sources` so operational data stays outside the repo.
These are not approved ingestion manifests. They are review artifacts created by the discovery subsystem.

Quarantined source artifacts and tombstones live in `quarantine/`.

Collection rules:

- Only manifests in `approved/` with `review_status` set to `approved` may be collected by the runtime.
- Discovery may create candidate records in `candidates/`, but those records must not enter approved ingestion automatically.
- Removal requests or unknown rights move content to quarantine and block collection/export.

# Training Eligibility Policy

## Decision Table

`training_and_retrieval`
- Owned internal content
- Explicitly licensed training corpora
- Public-domain content
- Open-license content whose terms permit the intended use
- User-provided content only after explicit opt-in and redaction review

`retrieval_only`
- Official proprietary DND material
- Fan-created DND blogs, transcripts, wikis, and reports
- User uploads by default
- Campaign logs by default
- Third-party references licensed only for lookup

`neither`
- Missing provenance
- Unknown license
- Disputed ownership
- Removal-requested content
- Sensitive or unredacted private content

## Mandatory Human Approvals

The following transitions need explicit human approval captured in the source manifest:

- `retrieval_only` -> `training_and_retrieval`
- any `user_upload` -> training-eligible
- any `campaign_log` -> training-eligible
- any DND-adjacent proprietary source -> training-eligible

## User Upload Rules

- Default: `retrieval_only`
- Training default: denied
- Training exception requires:
  - explicit opt-in
  - ownership or permission statement
  - successful redaction review
  - no removal request

## Campaign Log Rules

- Default: `retrieval_only`
- Logs containing personal data, private messages, or identifiable player details move to `neither` until redacted.
- Campaign logs never become trainable automatically.

## Training Export Rules

A record may enter training export only if:

- `eligibility_class == "training_and_retrieval"`
- `allowed_for_training == true`
- `allowed_for_rag == true`
- `provenance_status == "complete"`
- `removal_required == false`
- `license != "unknown"`
- `rights_basis != "unknown"`

## Refusal Cases

Training export must fail if any included record:

- is missing a source manifest
- is missing required provenance fields
- has unsafe or unknown rights status
- is quarantined
- still contains unresolved redaction findings

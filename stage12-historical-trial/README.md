# Historical non-serving trial, new implementation

This package is a separately identified minimal historical replay implementation.
It is not the original Stage11 sealed package and does not replace missing
original files under their old identities. The frozen 165-file generator and
unchanged input assets retain their exact original byte commitments.

The trial authenticates only collector run 41920338326, attempt 1, and its fixed
saved source. Original receipt and observation timestamps are preserved. Current
source eligibility is deliberately not established. The fixed already-published
legacy predecessor must still match. Any changed source, expired artifact,
lineage mismatch, unsafe path, missing metadata, unexplained visibility loss or
failed independent validation stops the trial.

The source and predecessor are independently reconstructed for QA. Candidate
files and visibility evidence are rechecked before and after QA. Private data,
logs, source archives and generated site output remain in temporary runner
storage and are removed before a successful allowlisted aggregate JSON is
exposed. No site, source dataset or private proof is uploaded. The intended
successful aggregate retention period is seven days.

Public input commitments are checked against their exact known bytes. Private
owner-consent text is not part of this package. The retained old authorization,
package and implementation digests are provenance only; they do not identify or
authorize this new code. No new signature infrastructure or credential is added.

All local workflow material remains OFF. A package inventory is an integrity
commitment, not a claim of review, execution permission, production eligibility
or publication authority. The trial execution path does not invoke any publisher, collector,
scheduler, cross-repository dispatch, automatic source selection or deployment.
Retained frozen code outside that path is not activated.
Local fixtures do not prove actual Actions execution, transport or browser QA.

# Optional reviewed supplement — local integration, not publication approval

Base three-file contract: relationship-supplement.js, relation-supplement/manifest.json,
relation-supplement/items.json. This does not modify the corrected 82 relation
JSON files, existing three modules, or parent/prerequisite/thumbnail semantics.

Both raw build_site.py and verified-output rerender_candidate.py accept paired
`--supplement-bundle` / `--supplement-approval` arguments. Without them the known
supplement import is removed; guarded hooks remain inert. A source candidate
already containing supplement files cannot be rerendered without explicit approved
preservation. After separate publication, the planner's exact-public guard also
refuses missing or changed supplemental modules/data. Do not bypass this guard.

Approval schema1 requires status approved, activate true, exact three file hashes,
version, sourceVersion and explicit scope. Current developer test approval scope
is local-test-only and cannot authorize publication. Real source acceptance is
separate: hash validation alone is not semantic approval.

The supplement schema is boopadb-relation-supplement-v1. sourceVersion must equal
the active approved relation-data version. version is SHA256 of canonical UTF8
JSON {schema,sourceVersion,items}, ensure_ascii=False, sort_keys=True and compact
separators. items.json wraps those fields plus version. manifest contains matching
schema/version/sourceVersion, exact itemIds and an exact items.json SHA/byte entry.
The trusted validator checks all these commitments, the allowlist, narrow reviewed
external-tool URL/key and reference IDs/status/date/evidence-digest fields. No
arbitrary URL, inferred ID, new classifier or remote code execution is supported.

The generated HTML binds the script query to its approved SHA prefix. Reference-card
rails mount beside the primary renderer's replaceable host; typed external-tool
cards join the existing prerequisite rail, with an onRender synchronization hook
to preserve them after primary rerenders;
current-product epoch checks protect asynchronous results. Supplemental rendering
runs concurrently with primary product-metadata enrichment and reconciles after it;
held-metadata fixture tests verify this ordering, not real-network performance. Errors are scoped and
must not remove known primary relationships. Unlisted items mean absent supplemental
coverage, never proof of no relationship. Reference links are not compatibility or
required-tool claims; reviewed observation dates remain explicit.

Current source review is recorded separately in the UI workstream. No source
ledger, original master, credentials or raw catalog is copied into the public
supplement. Existing v4 and correction-addon archives remain immutable; these
working-tree changes are not automatically installed on Muse or any mini PC.

## Optional original PNG asset

The only allowed fourth supplemental file is
`relation-supplement/assets/modular-avatar-logo.png`. Approval inventory hashes
bind its exact bytes; the shared renderer must itself match approved relation
module bytes and reference the same asset hash query exactly once. Bounded PNG
structure checks reject non-PNG, corrupt CRCs, oversized/unsupported headers,
APNG chunks or trailing content. Legacy three-file approval remains valid only
when no active shared renderer references the missing logo. Existing exact-public
namespace checks already prevent omission/rollback once the asset is published.

Original PNG/source ZIP provenance is separate from use permission. The user
requested continued promotional identification after scope uncertainty disclosure;
no rights-holder permission or definitive guideline coverage is asserted. The
original color/shape, contain layout, native alt plus persistent card-name/official-link fallback and no-endorsement presentation
must remain unchanged. No source semantic records or remote logo fetch are added.

The final MA card sync does not guarantee the shared custom gray-placeholder error handler; only native alt and persistent card name/official link are claimed.

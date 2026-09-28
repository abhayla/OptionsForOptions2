# Findings registry (this project)

One JSON file per proven finding, `knowledge/findings/<slug>.json`, written as a **class** (a population), with the
instance and its evidence in `first_seen`. Rules: `.claude/rules/kit/learning.md` (F1 to F6, learn-or-block) and
`.claude/rules/kit/spec-adherence.md` (findings carry their spec section).

Read this registry before answering "why does the system behave like this?", "is this defect new?" or designing a
new mechanism.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | the slug, same as the file name without `.json` (lowercase, digits, hyphens) |
| `class` | yes | the population, stated generically: which inputs, states or places the mechanism hits |
| `mechanism` | yes | why it happens, one or two sentences |
| `first_seen` | yes | object: `date`, `where`, `evidence` (the query and counts, log line or file:line that proved it) |
| `fix` | yes | the class-level fix, or "none yet" |
| `detection` | yes | object: `status` (`guarded` only when a named check covers the class, else `unguarded`), `checks` (names of those checks), optional `note` |
| `spec_ref` | yes (kit rule) | list of spec sections the finding touches, e.g. `["spec/business-rules/pricing.md#rounding"]`; `[]` only if it touches none, said in `detection.note` |

Extra fields are allowed (for example `occurrences`), but any generated index must render them.

## Example

```json
{
  "id": "check-validates-nothing-reports-pass",
  "class": "Any check fed rows that lack the field it reads reports PASS, whatever the data holds.",
  "mechanism": "The check skips rows where the field is missing instead of failing, so an empty input is a clean result.",
  "first_seen": {
    "date": "YYYY-MM-DD",
    "where": "nightly audit, check X",
    "evidence": "check reported PASS on 23 rows; a direct query found 23 violations"
  },
  "fix": "The check fails when the field it reads is absent from any row.",
  "detection": { "status": "guarded", "checks": ["test_check_x_fails_on_missing_field"] },
  "spec_ref": ["spec/testing/audit.md#check-x"]
}
```

## Index

If an index (`INDEX.md`) is kept, it is GENERATED from these files by a script and checked for staleness in CI;
never hand-edit it.

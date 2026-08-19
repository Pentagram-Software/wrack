# CatRecognizer — Phase 2 GCP infrastructure (PEN-259, task 5.5)

Storage infrastructure for identification's enrollment photos, processed splits, and exported
ONNX model artifacts. Scoped to Phase 2 only — Phase 1's off-the-shelf pretrained detector needs
no cloud storage of its own (see `design.md`'s "V1 ships in two internal phases" decision).

**Status**: written, not yet run against real GCP. The `/opsx:apply` session that generated
these files had `gcloud` authenticated (project `wrack-control`) but deliberately did not
provision real, billable cloud resources without an explicit go-ahead — run `setup-infra.sh`
yourself when ready.

## Supersedes prior unmerged branches

A prior planning pass left two unmerged, mutually-diverged branches — `cursor/pen-24-gcp-iam-service-accounts-cc54`
and `cursor/pen-25-infra-provision-gcs-buckets-{44a6,f9ef}` — scoped for a training approach
(Vertex AI Custom Jobs, Docker images via Artifact Registry) this design does not use. This
infra is a fresh build, not a resurrection of those branches; their three-bucket shape was kept
as a useful reference, nothing else. See `design.md`'s "GCP infrastructure is rebuilt clean, not
resurrected from prior branches" decision for the full rationale. Those branches should
eventually be closed out, but doing so isn't a blocker for this change.

## Buckets

| Bucket | Purpose | Lifecycle |
|--------|---------|-----------|
| `<project>-cat-recognizer-raw-data` | Raw per-cat reference/enrollment photos, under `{ryfka,chaja,lea}/` | 90-day auto-delete |
| `<project>-cat-recognizer-processed-data` | Processed splits, under `{train,val,test}/` | None |
| `<project>-cat-recognizer-models` | Exported ONNX model artifacts (detector + embedding backbone) | None |

## Service accounts (least-privilege, bucket-scoped only)

| Service account | raw-data | processed-data | models |
|-----------------|----------|-----------------|--------|
| `cat-recognizer-data-collector` | `objectAdmin` | `objectViewer` | — |
| `cat-recognizer-trainer-export` | `objectViewer` | `objectAdmin` | `objectAdmin` |

Neither service account has Artifact Registry roles — there's no containerized training to
authorize for V1 (`design.md`: "Training happens locally, not in the cloud, for V1").

## Setup

```bash
GCP_PROJECT_ID=wrack-control bash setup-infra.sh          # review first with --dry-run
python3 smoke_test.py --project wrack-control \
    --data-key path/to/data-collector-key.json \
    --trainer-key path/to/trainer-export-key.json
```

Generate service account keys the same way `cloud/bigquery/setup-iam.sh` does (`gcloud iam
service-accounts keys create`), or wire up Workload Identity Federation instead of long-lived
keys if running from CI — not scripted here since V1's enrollment (task 6.4) runs from a local
laptop, not a CI pipeline.

## Related tasks

- 5.1-5.4 implemented by `setup-infra.sh` + `smoke_test.py`.
- 6.3/6.4 (`../../edge/vision/identification/enroll.py`) writes enrollment photos and
  prototypes; wiring `enroll.py`'s output to upload into `raw-data`/`models` here is a
  follow-up once real photos and a real backbone export exist.

#!/usr/bin/env python3
"""End-to-end cat_detection ingestion test (PEN-251/PEN-269, tasks 3.5 and 7.2).

Builds one ``cat_detection`` event, sends it through the **real**
``RpiTelemetrySender`` -> unified ingress -> BigQuery path (not a direct
`bq query INSERT`, unlike ``cloud/bigquery/test-insert.sh`` — this
specifically exercises the same edge-to-cloud path production events take),
sends it a **second time with the same event_id** to directly test the
idempotency requirement, then queries BigQuery to confirm exactly one row
landed. **Not run this session** — needs a real Pi (or any machine with
network access to the deployed ingress) plus a provisioned device token; see
``cloud/functions/setup-device-tokens.sh``.

Usage — task 3.5 (Phase 1, identity fixed to unknown)::

    TELEMETRY_ENDPOINT=https://europe-central2-wrack-control.cloudfunctions.net/unifiedIngress \\
    TELEMETRY_DEVICE_TOKEN=<token> \\
    python3 e2e_ingestion_test.py --device-id rpi-camera-01 \\
        --model-version yolov8n-1.0.0 --pipeline-version edge-vision-0.1.0

Usage — task 7.2 (Phase 2, real identity), once identification is wired in::

    python3 e2e_ingestion_test.py --device-id rpi-camera-01 \\
        --model-version yolov8n-1.0.0+mobilenetv3-1.0.0 --pipeline-version edge-vision-0.1.0 \\
        --predicted-identity ryfka --final-identity ryfka --identification-confidence 0.87
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telemetry.builder import build_cat_detection_event  # noqa: E402
from telemetry.sender import RpiTelemetrySender  # noqa: E402


def query_row_count(project_id: str, event_id: str) -> int:
    """Query BigQuery via the `bq` CLI (same tool `cloud/bigquery/test-insert.sh`
    uses) for how many rows landed for *event_id*."""
    query = (
        "SELECT COUNT(*) as row_count FROM `{}.wrack_telemetry.events` "
        "WHERE event_id = '{}' AND event_type = 'cat_detection'"
    ).format(project_id, event_id)
    result = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=csv", "--project_id={}".format(project_id), query],
        capture_output=True,
        text=True,
        check=True,
    )
    # csv output: header line "row_count", then the value
    lines = [line for line in result.stdout.strip().splitlines() if line]
    return int(lines[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--pipeline-version", required=True)
    parser.add_argument("--predicted-identity", default="unknown")
    parser.add_argument("--final-identity", default="unknown")
    parser.add_argument("--identification-confidence", type=float, default=None)
    parser.add_argument("--project-id", default="wrack-control")
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=15.0,
        help="Delay before querying BigQuery, to let the streaming insert land",
    )
    args = parser.parse_args()

    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"
    event = build_cat_detection_event(
        event_start_time=now,
        event_end_time=now,
        detection_confidence=0.9,
        device_id=args.device_id,
        model_version=args.model_version,
        pipeline_version=args.pipeline_version,
        predicted_identity=args.predicted_identity,
        final_identity=args.final_identity,
        identification_confidence=args.identification_confidence,
    )
    event_id = event["event_id"]
    print("Built event {} (predicted_identity={}, final_identity={})".format(
        event_id, args.predicted_identity, args.final_identity
    ))

    sender = RpiTelemetrySender(device_id=args.device_id)

    print("Sending (attempt 1)...")
    ok1 = sender.send_events([event])
    print("  ok={}".format(ok1))

    print("Sending again with the SAME event_id (simulated retry, tests idempotency)...")
    ok2 = sender.send_events([event])
    print("  ok={}".format(ok2))

    print("Waiting {}s for the streaming insert to land...".format(args.wait_seconds))
    time.sleep(args.wait_seconds)

    row_count = query_row_count(args.project_id, event_id)
    print("Rows in wrack_telemetry.events for event_id={}: {}".format(event_id, row_count))

    if row_count != 1:
        print("FAIL: expected exactly 1 row, got {}".format(row_count))
        sys.exit(1)
    print("PASS: exactly one row, retried send was deduplicated.")


if __name__ == "__main__":
    main()

"""
Typed event builder for ``vision_detection`` telemetry events (PEN-169).

This is the integration surface a future vision/inference runtime will call
once it exists — no detection or inference logic lives here. See PEN-169 for
the full payload spec and PEN-166 for why this lives alongside the standalone
Raspberry Pi telemetry module rather than the shared multi-language contract
in ``shared/telemetry-types/`` (that JSON Schema + TypeScript work remains
open in PEN-169).

Usage::

    from telemetry.builder import build_vision_detection_event

    event = build_vision_detection_event(
        frame_index=4821,
        model_id="yolov8n-wrack",
        detections=[
            {
                "label": "cat",
                "creature_category": "animal",
                "confidence": 0.91,
                "bbox_norm": [0.12, 0.34, 0.45, 0.78],
            }
        ],
        inference_latency_ms=87.4,
        model_version="1.2.0",
        analysis_fps=4.9,
        scene_summary="cat, center",
        device_id="rpi-camera-01",
    )
    # Returns a validated event envelope dict ready to pass to
    # RpiTelemetryCollector.collect_raw(event) or json.dumps().
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .schemas import validate_event


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_vision_detection_event(
    frame_index: int,
    model_id: str,
    detections: List[Dict[str, Any]],
    *,
    inference_latency_ms: Optional[float] = None,
    model_version: Optional[str] = None,
    analysis_fps: Optional[float] = None,
    scene_summary: Optional[str] = None,
    session_id: Optional[str] = None,
    device_id: Optional[str] = None,
    source: str = "rpi",
) -> Dict[str, Any]:
    """Build and validate a ``vision_detection`` event envelope.

    Parameters
    ----------
    frame_index:
        Monotonic frame counter from the inference loop.
    model_id:
        Identifier matching the ``model_id`` from the model card.
    detections:
        List of detection dicts: ``label``, ``creature_category``,
        ``confidence``, ``bbox_norm``, and optional ``track_id``. May be
        empty. ``detection_count`` is derived as ``len(detections)``.
    inference_latency_ms, model_version, analysis_fps, scene_summary:
        Optional payload fields — see PEN-169 for the full spec.
    session_id, device_id:
        Optional envelope fields, forwarded verbatim when provided.
    source:
        Event source string. Defaults to ``"rpi"``.

    Returns
    -------
    dict
        A validated telemetry event envelope.

    Raises
    ------
    ValidationError
        If the constructed event fails schema validation (e.g. a detection
        has a confidence outside ``[0, 1]``, a malformed ``bbox_norm``, or
        an unrecognised ``creature_category``).
    """
    payload: Dict[str, Any] = {
        "frame_index": frame_index,
        "model_id": model_id,
        "detections": list(detections),
        "detection_count": len(detections),
    }
    if inference_latency_ms is not None:
        payload["inference_latency_ms"] = inference_latency_ms
    if model_version is not None:
        payload["model_version"] = model_version
    if analysis_fps is not None:
        payload["analysis_fps"] = analysis_fps
    if scene_summary is not None:
        payload["scene_summary"] = scene_summary

    event: Dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "event_type": "vision_detection",
        "source": source,
        "timestamp": _utc_now_iso(),
        "device_id": device_id,
        "session_id": session_id,
        "payload": payload,
    }

    validate_event(event)
    return event


def build_cat_detection_event(
    event_start_time: str,
    event_end_time: Optional[str],
    detection_confidence: float,
    device_id: str,
    model_version: str,
    pipeline_version: str,
    *,
    predicted_identity: str = "unknown",
    final_identity: str = "unknown",
    identification_confidence: Optional[float] = None,
    event_id: Optional[str] = None,
    session_id: Optional[str] = None,
    source: str = "rpi",
) -> Dict[str, Any]:
    """Build and validate a ``cat_detection`` event envelope (PEN-193).

    Emitted once per confirmed cat event, at close (see
    :mod:`edge.vision.events.lifecycle`). Phase 1 callers omit
    ``predicted_identity``/``final_identity``/``identification_confidence``,
    leaving the Phase-1 defaults (``"unknown"`` / ``"unknown"`` / ``None``)
    in place; Phase 2 passes the real identification output once wired in
    (task 7.1).

    Parameters
    ----------
    event_start_time, event_end_time:
        ISO 8601 UTC timestamps bounding the confirmed event. ``event_end_time``
        may be ``None`` if this is ever called before the event closes, though
        V1 only calls it at close.
    detection_confidence:
        Detector confidence for the frame that confirmed this event, in [0, 1].
    device_id, model_version, pipeline_version:
        See ``cat_detection.json`` — required, non-empty strings.
    predicted_identity, final_identity:
        One of ``ryfka``, ``chaja``, ``lea``, ``unknown``. Both default to
        ``"unknown"`` for Phase 1, where no identification model runs.
    identification_confidence:
        In [0, 1], or ``None`` (Phase 1 default) when identification did not
        run for this event.
    event_id:
        Explicit event id for stable retries — see
        :func:`edge.vision.telemetry.sender.RpiTelemetrySender`'s reuse of
        ``event_id`` as the BigQuery streaming-insert dedup key. Defaults to
        a freshly generated UUID v4 when not provided; callers that need to
        rebuild the *same* event dict across retry attempts (rather than
        keeping the first-built dict in memory) should pass the id from the
        first build explicitly.
    session_id:
        Optional envelope field, forwarded verbatim when provided.
    source:
        Event source string. Defaults to ``"rpi"``.

    Returns
    -------
    dict
        A validated telemetry event envelope, with ``type`` explicitly set
        to ``"event"`` so the unified ingress (PEN-227) routes it to
        BigQuery rather than the Grafana/health leg.

    Raises
    ------
    ValidationError
        If the constructed event fails schema validation.
    """
    payload: Dict[str, Any] = {
        "event_start_time": event_start_time,
        "event_end_time": event_end_time,
        "predicted_identity": predicted_identity,
        "final_identity": final_identity,
        "detection_confidence": detection_confidence,
        "identification_confidence": identification_confidence,
        "device_id": device_id,
        "model_version": model_version,
        "pipeline_version": pipeline_version,
    }

    event: Dict[str, Any] = {
        "event_id": event_id if event_id is not None else str(uuid.uuid4()),
        "event_type": "cat_detection",
        "source": source,
        "timestamp": _utc_now_iso(),
        "device_id": device_id,
        "session_id": session_id,
        "type": "event",
        "payload": payload,
    }

    validate_event(event)
    return event

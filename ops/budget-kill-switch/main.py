"""Cloud Run function entry point: Pub/Sub budget notification -> maybe disable billing.

Environment:
  TARGET_PROJECT_ID  project whose billing is detached (required)
  DRY_RUN            "true" to only log what would happen (default "false")
  KILL_RATIO         fraction of the budget that triggers the stop (default 1.0)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

import functions_framework
from cloudevents.http.event import CloudEvent
from google.cloud import billing_v1

from kill_switch import decide, parse_notification


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {"severity": record.levelname, "message": record.getMessage()}
        for key in ("project_id", "cost", "budget", "currency"):
            if hasattr(record, key):
                out[key] = getattr(record, key)
        if record.exc_info:
            out["exception"] = self.formatException(record.exc_info)
        return json.dumps(out)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)


class CloudBilling:
    def __init__(self) -> None:
        self._client = billing_v1.CloudBillingClient()

    def billing_enabled(self, project_id: str) -> bool:
        info = self._client.get_project_billing_info(name=f"projects/{project_id}")
        return bool(info.billing_enabled)

    def disable_billing(self, project_id: str) -> None:
        self._client.update_project_billing_info(
            name=f"projects/{project_id}",
            project_billing_info=billing_v1.ProjectBillingInfo(billing_account_name=""),
        )


@functions_framework.cloud_event
def on_budget_notification(event: CloudEvent) -> None:
    project_id = os.environ["TARGET_PROJECT_ID"]
    payload = parse_notification(event.data["message"]["data"])
    decide(
        payload,
        CloudBilling(),
        project_id,
        dry_run=os.environ.get("DRY_RUN", "false").lower() == "true",
        ratio=float(os.environ.get("KILL_RATIO", "1.0")),
    )

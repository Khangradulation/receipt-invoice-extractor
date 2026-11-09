"""Decision logic for the budget kill switch (no Google Cloud imports, so it is unit-testable).

Cloud Billing sends a budget notification to Pub/Sub several times a day. When the cost for the
current period reaches the budget, billing is detached from the project, which stops all paid
services in it. Re-enable by re-linking a billing account in the console.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger("budget-kill-switch")


class BillingClient(Protocol):
    def billing_enabled(self, project_id: str) -> bool: ...

    def disable_billing(self, project_id: str) -> None: ...


@dataclass(frozen=True)
class Decision:
    action: str  # "none" | "already_disabled" | "dry_run" | "disabled"
    cost: float
    budget: float


def parse_notification(message_data_b64: str) -> dict[str, Any]:
    payload = json.loads(base64.b64decode(message_data_b64).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("budget notification is not a JSON object")
    return payload


def decide(
    payload: dict[str, Any],
    client: BillingClient,
    project_id: str,
    *,
    dry_run: bool,
    ratio: float = 1.0,
) -> Decision:
    cost = float(payload["costAmount"])
    budget = float(payload["budgetAmount"])
    currency = payload.get("currencyCode", "")
    limit = budget * ratio
    ctx = {"project_id": project_id, "cost": cost, "budget": budget, "currency": currency}

    if cost < limit:
        logger.info("under budget; no action", extra=ctx)
        return Decision("none", cost, budget)

    if not client.billing_enabled(project_id):
        logger.info("billing already disabled", extra=ctx)
        return Decision("already_disabled", cost, budget)

    if dry_run:
        logger.warning("DRY RUN: budget reached; would disable billing", extra=ctx)
        return Decision("dry_run", cost, budget)

    client.disable_billing(project_id)
    logger.critical("budget reached; billing disabled for project", extra=ctx)
    return Decision("disabled", cost, budget)

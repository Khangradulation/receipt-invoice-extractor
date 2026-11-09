import base64
import json

import pytest

from kill_switch import decide, parse_notification


class FakeBilling:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.disabled_calls: list[str] = []

    def billing_enabled(self, project_id: str) -> bool:
        return self.enabled

    def disable_billing(self, project_id: str) -> None:
        self.disabled_calls.append(project_id)
        self.enabled = False


def note(cost: float, budget: float = 10.0) -> dict[str, object]:
    return {"costAmount": cost, "budgetAmount": budget, "currencyCode": "CAD"}


def test_under_budget_does_nothing() -> None:
    client = FakeBilling()
    assert decide(note(9.99), client, "p", dry_run=False).action == "none"
    assert client.disabled_calls == []


def test_at_budget_disables_billing() -> None:
    client = FakeBilling()
    assert decide(note(10.0), client, "p", dry_run=False).action == "disabled"
    assert client.disabled_calls == ["p"]


def test_dry_run_never_disables() -> None:
    client = FakeBilling()
    assert decide(note(25.0), client, "p", dry_run=True).action == "dry_run"
    assert client.disabled_calls == []


def test_already_disabled_is_idempotent() -> None:
    client = FakeBilling(enabled=False)
    assert decide(note(50.0), client, "p", dry_run=False).action == "already_disabled"
    assert client.disabled_calls == []


def test_ratio_triggers_early() -> None:
    client = FakeBilling()
    assert decide(note(9.0), client, "p", dry_run=False, ratio=0.9).action == "disabled"


def test_parse_notification_roundtrip() -> None:
    data = base64.b64encode(json.dumps(note(1.5)).encode()).decode()
    assert parse_notification(data)["costAmount"] == 1.5


def test_parse_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_notification(base64.b64encode(b"[1,2]").decode())

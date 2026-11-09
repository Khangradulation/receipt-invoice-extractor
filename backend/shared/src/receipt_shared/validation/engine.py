"""Validation engine: run every rule, check duplicates, decide the processing outcome.

Outcome:
  DUPLICATE        the exact file was uploaded before
  REVIEW_REQUIRED  any error (missing required field, totals do not add up, possible duplicate, ...)
  VALID            no errors (warnings are allowed)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime

from receipt_shared.config import Settings, get_settings
from receipt_shared.models.enums import DocumentStatus, DuplicateStatus, ProcessingOutcome
from receipt_shared.models.extraction import ExtractedDocument
from receipt_shared.models.validation import (
    Severity,
    ValidationCode,
    ValidationIssue,
    ValidationResult,
)
from receipt_shared.validation.config import ValidationConfig
from receipt_shared.validation.duplicates import DuplicateIndex, check_duplicates, fingerprint
from receipt_shared.validation.rules import ALL_RULES, Rule

# Bump when rules or thresholds change meaningfully; stored with each result.
RULES_VERSION = "2026-11-09.1"


class DocumentValidator:
    def __init__(
        self,
        config: ValidationConfig | None = None,
        *,
        rules: Sequence[Rule] = ALL_RULES,
        settings: Settings | None = None,
    ) -> None:
        self.config = config or ValidationConfig.from_settings(settings or get_settings())
        self._rules = tuple(rules)

    def validate(
        self,
        document: ExtractedDocument,
        *,
        document_id: str,
        user_id: str,
        file_sha256: str,
        created_at: datetime | None = None,
        extraction_warnings: Iterable[str] = (),
        duplicate_index: DuplicateIndex | None = None,
        duplicate_acknowledged: bool = False,
        today: date | None = None,
    ) -> ValidationResult:
        """Validate one extracted document.

        ``duplicate_acknowledged`` is set by a reviewer who confirmed that a *possible* duplicate
        is a separate transaction (Phase 9). It never overrides an exact-file duplicate.
        """
        today = today or datetime.now(UTC).date()
        issues: list[ValidationIssue] = []
        for rule in self._rules:
            issues.extend(rule(document, self.config, today))
        issues.extend(
            ValidationIssue(
                code=ValidationCode.EXTRACTION_WARNING, severity=Severity.WARNING, message=w
            )
            for w in extraction_warnings
        )

        duplicate_status = DuplicateStatus.NOT_DUPLICATE
        duplicate_of: list[str] = []
        if duplicate_index is not None:
            current = fingerprint(
                document_id=document_id,
                user_id=user_id,
                file_sha256=file_sha256,
                document=document,
                status=DocumentStatus.VALIDATING.value,
                created_at=created_at or datetime.now(UTC),
            )
            duplicate_status, duplicate_of, dup_issues = check_duplicates(current, duplicate_index)
            if duplicate_status is DuplicateStatus.POSSIBLE_DUPLICATE and duplicate_acknowledged:
                dup_issues = [
                    ValidationIssue(
                        code=ValidationCode.POSSIBLE_DUPLICATE,
                        severity=Severity.WARNING,
                        message="Possible duplicate confirmed by a reviewer as a separate "
                        "transaction.",
                    )
                ]
            issues.extend(dup_issues)

        errors = [i for i in issues if i.severity is Severity.ERROR]
        warnings = [i for i in issues if i.severity is Severity.WARNING]

        if duplicate_status is DuplicateStatus.DUPLICATE:
            status = ProcessingOutcome.DUPLICATE
        elif errors:
            status = ProcessingOutcome.REVIEW_REQUIRED
        else:
            status = ProcessingOutcome.VALID

        failed_fields = sorted({f for issue in errors for f in issue.fields})
        return ValidationResult(
            is_valid=status is ProcessingOutcome.VALID,
            validation_status=status,
            validation_errors=errors,
            validation_warnings=warnings,
            failed_fields=failed_fields,
            duplicate_status=duplicate_status,
            duplicate_of=duplicate_of,
            rules_version=RULES_VERSION,
        )

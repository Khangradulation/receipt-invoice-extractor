# Log-based metrics from the services' structured JSON logs, plus alert policies.
# Phase 14 adds the dashboard and tunes thresholds.
variable "project_id" { type = string }
variable "notification_channels" {
  description = "Monitoring notification channel IDs (e.g. an email channel); empty = no notifications"
  type        = list(string)
  default     = []
}

locals {
  worker = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"receipt-worker\""
}

resource "google_logging_metric" "documents_processed" {
  project     = var.project_id
  name        = "receipt/documents_processed"
  description = "Documents finished by the worker, by final status"
  filter      = "${local.worker} AND jsonPayload.message=\"processing completed\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    labels {
      key        = "status"
      value_type = "STRING"
    }
  }
  label_extractors = { status = "EXTRACT(jsonPayload.status)" }
}

resource "google_logging_metric" "processing_failures" {
  project     = var.project_id
  name        = "receipt/processing_failures"
  description = "Worker failures (permanent and retried), by error code"
  filter      = "${local.worker} AND (jsonPayload.message=\"processing failed permanently\" OR jsonPayload.message=\"processing attempt failed; will retry\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    labels {
      key        = "error_code"
      value_type = "STRING"
    }
  }
  label_extractors = { error_code = "EXTRACT(jsonPayload.error_code)" }
}

resource "google_logging_metric" "gemini_latency" {
  project         = var.project_id
  name            = "receipt/gemini_latency_ms"
  description     = "Gemini extraction latency per document (ms)"
  filter          = "${local.worker} AND jsonPayload.message=\"extraction stored\""
  value_extractor = "EXTRACT(jsonPayload.gemini_latency_ms)"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"
  }
  bucket_options {
    exponential_buckets {
      num_finite_buckets = 20
      growth_factor      = 1.5
      scale              = 500
    }
  }
}

resource "google_logging_metric" "bigquery_write_failures" {
  project     = var.project_id
  name        = "receipt/bigquery_write_failures"
  description = "Failed BigQuery writes (worker or API)"
  filter      = "resource.type=\"cloud_run_revision\" AND jsonPayload.message=\"bigquery write failed\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "processing_failures" {
  project               = var.project_id
  display_name          = "Receipt worker: processing failures"
  combiner              = "OR"
  notification_channels = var.notification_channels
  conditions {
    display_name = "More than 5 failures in 15 minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.processing_failures.name}\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "0s"
      aggregations {
        alignment_period     = "900s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
  documentation {
    content = "Check worker logs for error_code; see docs/processing.md."
  }
}

resource "google_monitoring_alert_policy" "bigquery_write_failures" {
  project               = var.project_id
  display_name          = "Receipt pipeline: BigQuery write failures"
  combiner              = "OR"
  notification_channels = var.notification_channels
  conditions {
    display_name = "Any BigQuery write failure in 10 minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.bigquery_write_failures.name}\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "gemini_latency" {
  project               = var.project_id
  display_name          = "Receipt worker: high Gemini latency"
  combiner              = "OR"
  notification_channels = var.notification_channels
  conditions {
    display_name = "p95 Gemini latency above 60 s for 15 minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.gemini_latency.name}\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 60000
      duration        = "900s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MAX"
      }
    }
  }
}

output "metrics" {
  value = [
    google_logging_metric.documents_processed.name,
    google_logging_metric.processing_failures.name,
    google_logging_metric.gemini_latency.name,
    google_logging_metric.bigquery_write_failures.name,
  ]
}

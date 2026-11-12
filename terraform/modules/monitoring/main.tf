# Observability for the processing pipeline: log-based metrics from the services' structured JSON
# logs (IDs, statuses and timings only, never document contents), alert policies, an email
# notification channel and a Cloud Monitoring dashboard.
variable "project_id" { type = string }
variable "notification_channels" {
  description = "Existing notification channel IDs to notify, in addition to alert_emails"
  type        = list(string)
  default     = []
}
variable "alert_emails" {
  description = "Email addresses that receive alert notifications (one channel each)"
  type        = list(string)
  default     = []
}
variable "review_rate_threshold" {
  description = "Alert when more than this share of processed documents need review (6 h, min 10 docs)"
  type        = number
  default     = 0.5
}

locals {
  run    = "resource.type=\"cloud_run_revision\""
  worker = "${local.run} AND resource.labels.service_name=\"receipt-worker\""
  api    = "${local.run} AND resource.labels.service_name=\"receipt-api\""
  user   = "logging.googleapis.com/user"
  channels = concat(
    var.notification_channels,
    [for c in google_monitoring_notification_channel.email : c.id],
  )
}

# --- Notification channel ----------------------------------------------------------------------
resource "google_monitoring_notification_channel" "email" {
  for_each     = toset(var.alert_emails)
  project      = var.project_id
  display_name = "Receipt extractor alerts (${each.value})"
  type         = "email"
  labels       = { email_address = each.value }
}

# --- Log-based metrics -------------------------------------------------------------------------
resource "google_logging_metric" "upload_urls_issued" {
  project     = var.project_id
  name        = "receipt/upload_urls_issued"
  description = "Upload URLs issued by the API (one per document upload), by content type"
  filter      = "${local.api} AND jsonPayload.message=\"upload url issued\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    labels {
      key        = "content_type"
      value_type = "STRING"
    }
  }
  label_extractors = { content_type = "EXTRACT(jsonPayload.content_type)" }
}

resource "google_logging_metric" "processing_attempts" {
  project     = var.project_id
  name        = "receipt/processing_attempts"
  description = "Processing attempts started by the worker, by attempt number"
  filter      = "${local.worker} AND jsonPayload.message=\"processing started\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    labels {
      key        = "attempt"
      value_type = "STRING"
    }
  }
  label_extractors = { attempt = "EXTRACT(jsonPayload.attempt)" }
}

resource "google_logging_metric" "documents_processed" {
  project     = var.project_id
  name        = "receipt/documents_processed"
  description = "Documents finished by the worker, by final status (REVIEW_REQUIRED = failed validation)"
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

resource "google_logging_metric" "processing_duration" {
  project         = var.project_id
  name            = "receipt/processing_duration_ms"
  description     = "End-to-end worker processing time per document (ms)"
  filter          = "${local.worker} AND jsonPayload.message=\"processing completed\""
  value_extractor = "EXTRACT(jsonPayload.duration_ms)"
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

resource "google_logging_metric" "event_retries" {
  project     = var.project_id
  name        = "receipt/event_retries"
  description = "Upload events handed back to Eventarc for redelivery, by reason"
  filter      = "${local.worker} AND (jsonPayload.message=\"processing attempt failed; will retry\" OR jsonPayload.message=\"event redelivered while processing; retry later\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    labels {
      key        = "reason"
      value_type = "STRING"
    }
  }
  label_extractors = { reason = "EXTRACT(jsonPayload.message)" }
}

resource "google_logging_metric" "worker_errors" {
  project     = var.project_id
  name        = "receipt/worker_errors"
  description = "Worker log entries at ERROR or above (unexpected exceptions)"
  filter      = "${local.worker} AND severity>=ERROR"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
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

resource "google_logging_metric" "gemini_errors" {
  project     = var.project_id
  name        = "receipt/gemini_errors"
  description = "Failed Gemini calls (each attempt, including ones retried), by error code"
  filter      = "${local.worker} AND (jsonPayload.message=\"gemini attempt failed\" OR jsonPayload.message=\"gemini extraction failed\")"
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

resource "google_logging_metric" "bigquery_write_failures" {
  project     = var.project_id
  name        = "receipt/bigquery_write_failures"
  description = "Failed BigQuery jobs (worker or API); the log entry's operation field says which"
  # "bigquery write failed" is the message of revisions deployed before Phase 13.
  filter = "${local.run} AND (jsonPayload.message=\"bigquery job failed\" OR jsonPayload.message=\"bigquery write failed\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_logging_metric" "review_actions" {
  project     = var.project_id
  name        = "receipt/review_actions"
  description = "Manual review activity: corrections saved, approvals, rejections"
  filter      = "${local.api} AND (jsonPayload.message=\"review corrections saved\" OR jsonPayload.message=\"document approved\" OR jsonPayload.message=\"document rejected\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    labels {
      key        = "action"
      value_type = "STRING"
    }
  }
  label_extractors = { action = "EXTRACT(jsonPayload.message)" }
}

resource "google_logging_metric" "documents_deleted" {
  project     = var.project_id
  name        = "receipt/documents_deleted"
  description = "Documents permanently deleted by their owners"
  filter      = "${local.api} AND jsonPayload.message=\"document deleted\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

# --- Alert policies ----------------------------------------------------------------------------
resource "google_monitoring_alert_policy" "processing_failures" {
  project               = var.project_id
  display_name          = "Receipt worker: high processing failure count"
  severity              = "ERROR"
  combiner              = "OR"
  notification_channels = local.channels
  conditions {
    display_name = "More than 5 failures in 15 minutes"
    condition_threshold {
      filter          = "metric.type=\"${local.user}/${google_logging_metric.processing_failures.name}\" AND resource.type=\"cloud_run_revision\""
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
  alert_strategy { auto_close = "3600s" }
  documentation {
    content = "Documents are failing to process. Group the receipt/processing_failures metric by error_code, then check the worker logs for that code (docs/monitoring.md)."
  }
}

resource "google_monitoring_alert_policy" "worker_errors" {
  project               = var.project_id
  display_name          = "Receipt worker: repeated errors"
  severity              = "ERROR"
  combiner              = "OR"
  notification_channels = local.channels
  conditions {
    display_name = "3 or more worker errors in 15 minutes"
    condition_threshold {
      filter          = "metric.type=\"${local.user}/${google_logging_metric.worker_errors.name}\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 2
      duration        = "0s"
      aggregations {
        alignment_period     = "900s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
  alert_strategy { auto_close = "3600s" }
  documentation {
    content = "The worker logged unexpected errors. Open Logs Explorer with resource.labels.service_name=\"receipt-worker\" severity>=ERROR (docs/monitoring.md)."
  }
}

resource "google_monitoring_alert_policy" "gemini_latency" {
  project               = var.project_id
  display_name          = "Receipt worker: high Gemini latency"
  severity              = "WARNING"
  combiner              = "OR"
  notification_channels = local.channels
  conditions {
    display_name = "p95 Gemini latency above 60 s for 15 minutes"
    condition_threshold {
      filter          = "metric.type=\"${local.user}/${google_logging_metric.gemini_latency.name}\" AND resource.type=\"cloud_run_revision\""
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
  alert_strategy { auto_close = "3600s" }
  documentation {
    content = "Gemini is slow. Check the Vertex AI status page and the gemini_errors metric; documents still complete, only later."
  }
}

resource "google_monitoring_alert_policy" "bigquery_write_failures" {
  project               = var.project_id
  display_name          = "Receipt pipeline: BigQuery write failures"
  severity              = "ERROR"
  combiner              = "OR"
  notification_channels = local.channels
  conditions {
    display_name = "Any BigQuery job failure in 10 minutes"
    condition_threshold {
      filter          = "metric.type=\"${local.user}/${google_logging_metric.bigquery_write_failures.name}\" AND resource.type=\"cloud_run_revision\""
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
  alert_strategy { auto_close = "3600s" }
  documentation {
    content = "Analytics writes are failing; the worker retries and dashboards may lag. Search logs for \"bigquery job failed\" and check error_type (docs/monitoring.md)."
  }
}

resource "google_monitoring_alert_policy" "review_rate" {
  project               = var.project_id
  display_name          = "Receipt pipeline: unusually high review rate"
  severity              = "WARNING"
  combiner              = "OR"
  notification_channels = local.channels
  conditions {
    display_name = "Over ${var.review_rate_threshold * 100}% of documents need review (6 h, at least 10 documents)"
    condition_prometheus_query_language {
      query               = <<-EOT
        (
          sum(increase(logging_googleapis_com:user_receipt_documents_processed{monitored_resource="cloud_run_revision",status="REVIEW_REQUIRED"}[6h]))
          / sum(increase(logging_googleapis_com:user_receipt_documents_processed{monitored_resource="cloud_run_revision"}[6h]))
        ) > ${var.review_rate_threshold}
        and on() sum(increase(logging_googleapis_com:user_receipt_documents_processed{monitored_resource="cloud_run_revision"}[6h])) >= 10
      EOT
      duration            = "0s"
      evaluation_interval = "300s"
    }
  }
  alert_strategy { auto_close = "21600s" }
  documentation {
    content = "Many documents are failing validation. Check the dashboard's validation outcome chart and recent uploads: a new document layout, a model change or a prompt regression (run the benchmark, docs/evaluation.md)."
  }
  depends_on = [google_logging_metric.documents_processed]
}

resource "google_monitoring_alert_policy" "api_errors" {
  project               = var.project_id
  display_name          = "Receipt API: server errors"
  severity              = "ERROR"
  combiner              = "OR"
  notification_channels = local.channels
  conditions {
    display_name = "More than 5 HTTP 5xx responses in 10 minutes"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"receipt-api\" AND metric.labels.response_code_class=\"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "0s"
      aggregations {
        alignment_period     = "600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
  alert_strategy { auto_close = "3600s" }
  documentation {
    content = "The API is returning 5xx. Search API logs for \"unhandled error\" or \"request completed\" with http_status>=500; each has a request_id (docs/monitoring.md)."
  }
}

output "metrics" {
  value = [for m in [
    google_logging_metric.upload_urls_issued, google_logging_metric.processing_attempts,
    google_logging_metric.documents_processed, google_logging_metric.processing_duration,
    google_logging_metric.processing_failures, google_logging_metric.event_retries,
    google_logging_metric.worker_errors, google_logging_metric.gemini_latency,
    google_logging_metric.gemini_errors, google_logging_metric.bigquery_write_failures,
    google_logging_metric.review_actions, google_logging_metric.documents_deleted,
  ] : m.name]
}
output "notification_channels" { value = local.channels }

# --- Dashboard ---------------------------------------------------------------------------------
locals {
  # One chart per row of this list: [title, metric filter, aligner, reducer, group-by, plot type].
  charts = [
    ["Uploads (upload URLs issued)", "metric.type=\"${local.user}/receipt/upload_urls_issued\"", "ALIGN_SUM", "REDUCE_SUM", ["metric.label.content_type"], "STACKED_BAR"],
    ["Documents processed by outcome", "metric.type=\"${local.user}/receipt/documents_processed\"", "ALIGN_SUM", "REDUCE_SUM", ["metric.label.status"], "STACKED_BAR"],
    ["Processing attempts (attempt > 1 = retry)", "metric.type=\"${local.user}/receipt/processing_attempts\"", "ALIGN_SUM", "REDUCE_SUM", ["metric.label.attempt"], "STACKED_BAR"],
    ["Processing failures by error code", "metric.type=\"${local.user}/receipt/processing_failures\"", "ALIGN_SUM", "REDUCE_SUM", ["metric.label.error_code"], "STACKED_BAR"],
    ["Processing duration p95 (ms)", "metric.type=\"${local.user}/receipt/processing_duration_ms\"", "ALIGN_PERCENTILE_95", "REDUCE_MAX", [], "LINE"],
    ["Processing duration p50 (ms)", "metric.type=\"${local.user}/receipt/processing_duration_ms\"", "ALIGN_PERCENTILE_50", "REDUCE_MAX", [], "LINE"],
    ["Gemini latency p95 (ms)", "metric.type=\"${local.user}/receipt/gemini_latency_ms\"", "ALIGN_PERCENTILE_95", "REDUCE_MAX", [], "LINE"],
    ["Gemini errors by code", "metric.type=\"${local.user}/receipt/gemini_errors\"", "ALIGN_SUM", "REDUCE_SUM", ["metric.label.error_code"], "STACKED_BAR"],
    ["Event retries by reason", "metric.type=\"${local.user}/receipt/event_retries\"", "ALIGN_SUM", "REDUCE_SUM", ["metric.label.reason"], "STACKED_BAR"],
    ["BigQuery job failures", "metric.type=\"${local.user}/receipt/bigquery_write_failures\"", "ALIGN_SUM", "REDUCE_SUM", [], "STACKED_BAR"],
    ["Manual review actions", "metric.type=\"${local.user}/receipt/review_actions\"", "ALIGN_SUM", "REDUCE_SUM", ["metric.label.action"], "STACKED_BAR"],
    ["Worker errors", "metric.type=\"${local.user}/receipt/worker_errors\"", "ALIGN_SUM", "REDUCE_SUM", [], "STACKED_BAR"],
    ["API requests by response class", "metric.type=\"run.googleapis.com/request_count\" resource.label.service_name=\"receipt-api\"", "ALIGN_SUM", "REDUCE_SUM", ["metric.label.response_code_class"], "STACKED_BAR"],
    ["API latency p95 (ms)", "metric.type=\"run.googleapis.com/request_latencies\" resource.label.service_name=\"receipt-api\"", "ALIGN_PERCENTILE_95", "REDUCE_MAX", [], "LINE"],
    ["Documents deleted by users", "metric.type=\"${local.user}/receipt/documents_deleted\"", "ALIGN_SUM", "REDUCE_SUM", [], "STACKED_BAR"],
    ["Cloud Run instances", "metric.type=\"run.googleapis.com/container/instance_count\"", "ALIGN_MAX", "REDUCE_SUM", ["resource.label.service_name"], "STACKED_AREA"],
  ]
  review_rate_query = <<-EOT
    sum(increase(logging_googleapis_com:user_receipt_documents_processed{monitored_resource="cloud_run_revision",status="REVIEW_REQUIRED"}[1h]))
    / sum(increase(logging_googleapis_com:user_receipt_documents_processed{monitored_resource="cloud_run_revision"}[1h]))
  EOT
}

resource "google_monitoring_dashboard" "pipeline" {
  project = var.project_id
  dashboard_json = jsonencode({
    displayName = "Receipt extractor: pipeline"
    mosaicLayout = {
      columns = 48
      tiles = concat(
        # Positions of 0 are omitted and defaults (targetAxis, style) spelled out, because the API
        # stores the dashboard that way and Terraform would otherwise see a permanent diff.
        [{
          width = 48, height = 4
          widget = {
            title = "About"
            text = {
              style   = {}
              format  = "MARKDOWN"
              content = "Uploads → Eventarc → worker (Gemini, validation) → Firestore/BigQuery. Counts come from structured logs (IDs and statuses only). Alerts and runbook: docs/monitoring.md."
            }
          }
        }],
        [for i, c in local.charts : merge(i % 2 == 1 ? { xPos = 24 } : {}, {
          yPos                                                = 4 + floor(i / 2) * 16
          width                                               = 24
          height                                              = 16
          widget = {
            title = c[0]
            xyChart = {
              dataSets = [{
                plotType   = c[5]
                targetAxis = "Y1"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "${c[1]} resource.type=\"cloud_run_revision\""
                    aggregation = merge({
                      alignmentPeriod    = "300s"
                      perSeriesAligner   = c[2]
                      crossSeriesReducer = c[3]
                    }, length(c[4]) > 0 ? { groupByFields = c[4] } : {})
                  }
                }
              }]
            }
          }
        })],
        [{
          yPos = 4 + ceil(length(local.charts) / 2) * 16, width = 48, height = 16
          widget = {
            title = "Review rate (share of processed documents needing review, 1 h window)"
            xyChart = {
              dataSets = [{
                plotType        = "LINE"
                targetAxis      = "Y1"
                timeSeriesQuery = { prometheusQuery = local.review_rate_query }
              }]
              thresholds = [{ value = var.review_rate_threshold, label = "Alert threshold" }]
            }
          }
        }],
      )
    }
  })
  depends_on = [
    google_logging_metric.upload_urls_issued, google_logging_metric.processing_attempts,
    google_logging_metric.documents_processed, google_logging_metric.processing_duration,
    google_logging_metric.processing_failures, google_logging_metric.event_retries,
    google_logging_metric.worker_errors, google_logging_metric.gemini_latency,
    google_logging_metric.gemini_errors, google_logging_metric.bigquery_write_failures,
    google_logging_metric.review_actions, google_logging_metric.documents_deleted,
  ]
}

output "dashboard_id" { value = google_monitoring_dashboard.pipeline.id }

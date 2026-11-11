output "documents_bucket" { value = module.documents.name }
output "artifact_registry" { value = module.registry.url }
output "worker_uri" { value = module.worker.uri }
output "api_uri" { value = try(module.api[0].uri, null) }
output "frontend_uri" { value = try(module.frontend[0].uri, null) }
output "github_wif_provider" { value = module.github_wif.provider_name }
output "ci_deployer_email" { value = module.github_wif.deployer_email }
output "bigquery_tables" { value = module.bigquery.tables }

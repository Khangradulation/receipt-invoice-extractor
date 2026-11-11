output "documents_bucket" { value = module.stack.documents_bucket }
output "artifact_registry" { value = module.stack.artifact_registry }
output "worker_uri" { value = module.stack.worker_uri }
output "api_uri" { value = module.stack.api_uri }
output "frontend_uri" { value = module.stack.frontend_uri }
output "github_wif_provider" { value = module.stack.github_wif_provider }
output "ci_deployer_email" { value = module.stack.ci_deployer_email }
output "bigquery_tables" { value = module.stack.bigquery_tables }

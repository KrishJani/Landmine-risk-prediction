# Backend helper scripts

Run from `reland-backend/` unless noted.

| Script | Purpose |
|--------|---------|
| **Deploy** | |
| `manual_deploy.sh` | Manual deployment steps |
| `create_apprunner_service.sh` | Create App Runner service |
| `create_service_manual.sh` | Manual service creation |
| `push_tested_image.sh` | Push Docker image to ECR |
| `cleanup_and_push.sh` | Clean and push image |
| **Diagnose / monitor** | |
| `check_app_logs.sh` | Check application logs |
| `check_deployment_logs.sh` | Check deployment logs |
| `check_service_config.sh` | Check service configuration |
| `diagnose_apprunner.sh` | Diagnose App Runner issues |
| `monitor_deployment.sh` | Monitor deployment |
| `watch_current_deployment.sh` | Watch current deployment |
| `wait_for_service.sh` | Wait for service to be ready |
| **Health / fix** | |
| `fix_healthcheck.sh` | Fix health check config |
| `update_health_check_fast.sh` | Update health check (fast) |
| **Verify / test** | |
| `test_before_deploy.sh` | Run tests before deploy |
| `test_docker_local.sh` | Test Docker locally |
| `test_health_local.sh` | Test health endpoint locally |
| `verify_ecr_image.sh` | Verify ECR image |
| `verify_start_command.sh` | Verify start command |

Primary entry points (kept in backend root): `start_backend.sh`, `start.sh`, `test_api.sh`, `test_production.sh`, `ec2-user-data.sh`.

package migrations

import _ "embed"

//go:embed 001_backend.sql
var Baseline string

//go:embed 002_contract_13.sql
var Upgrade string

//go:embed 003_job_controller.sql
var Queue string

//go:embed 006_worker_contracts.sql
var WorkerContracts string

//go:embed 007_runbook_contract.sql
var RunbookContract string

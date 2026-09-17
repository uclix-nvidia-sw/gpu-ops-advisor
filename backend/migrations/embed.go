package migrations

import _ "embed"

//go:embed 001_backend.sql
var Baseline string

//go:embed 002_contract_13.sql
var Upgrade string

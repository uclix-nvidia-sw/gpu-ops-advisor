$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $env:GOCACHE = Join-Path (Get-Location) '.local/go-build'
    if (-not $env:DATABASE_URL) {
        $env:DATABASE_URL = 'postgres://dsx:local-development-only@127.0.0.1:55432/dsx?sslmode=disable'
    }
    $env:DSX_MIGRATE = 'true'
    $env:DSX_SEED = 'true'
    if (-not $env:DSX_SCHEDULER_ENABLED) { $env:DSX_SCHEDULER_ENABLED = 'true' }
    go run ./cmd/server
    if ($LASTEXITCODE -ne 0) { throw 'Backend failed.' }
} finally { Pop-Location }

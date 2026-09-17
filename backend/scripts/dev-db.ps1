$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $env:GOCACHE = Join-Path (Get-Location) '.local/go-build'
    go run ./cmd/devdb
    if ($LASTEXITCODE -ne 0) { throw 'Local PostgreSQL failed.' }
} finally { Pop-Location }

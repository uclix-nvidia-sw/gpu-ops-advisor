param([switch]$E2E)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $env:GOCACHE = Join-Path (Get-Location) '.local/go-build'
    go test ./...
    if ($LASTEXITCODE -ne 0) { throw 'Unit test failed.' }
    go vet ./...
    if ($LASTEXITCODE -ne 0) { throw 'Go vet failed.' }
    if ($E2E) {
        if (-not $env:E2E_DATABASE_URL) {
            $env:E2E_DATABASE_URL = 'postgres://dsx:local-development-only@127.0.0.1:55432/dsx?sslmode=disable'
        }
        go test -tags=e2e ./tests -v -count=1
        if ($LASTEXITCODE -ne 0) { throw 'Backend E2E failed.' }
    }
} finally { Pop-Location }

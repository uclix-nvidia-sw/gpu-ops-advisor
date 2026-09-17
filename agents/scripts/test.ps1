param([switch]$E2E, [string]$PgBin)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location $repo
try {
    if ($E2E) {
        $env:GOCACHE = Join-Path $repo '.local/go-cache'
        $env:GOMODCACHE = Join-Path $repo '.local/go-mod'
        go -C job-controller build -o ../.local/job-controller.exe ./cmd/server
        if ($LASTEXITCODE -ne 0) { throw 'JC build failed' }
        if ($PgBin) { $env:PG_BIN = (Resolve-Path -LiteralPath $PgBin).Path }
        $env:RUN_AGENT_E2E = '1'
        .venv/Scripts/python.exe -m pytest -c agents/pytest.ini agents/tests -q
    } else {
        .venv/Scripts/python.exe -m pytest -c agents/pytest.ini agents/tests -m 'not e2e' -q
    }
    if ($LASTEXITCODE -ne 0) { throw 'Agent tests failed' }
} finally { Pop-Location }

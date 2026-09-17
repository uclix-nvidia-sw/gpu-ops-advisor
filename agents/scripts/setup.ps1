param([switch]$DownloadMcp)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location $repo
try {
    $env:UV_CACHE_DIR = Join-Path $repo '.local/uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $repo '.local/python'
    uv venv --python 3.12 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment failed' }
    uv pip install --python .venv/Scripts/python.exe -r agents/requirements.txt -e shared/python -e rcca-agent -e ops-agent
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    if ($DownloadMcp) {
        $target = Join-Path $repo '.local/mcp-grafana'
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        $release = 'https://github.com/grafana/mcp-grafana/releases/download/v1.4.2'
        $archive = Join-Path $target 'server.zip'
        $checksums = Join-Path $target 'checksums.txt'
        Invoke-WebRequest "$release/mcp-grafana_Windows_x86_64.zip" -OutFile $archive
        Invoke-WebRequest "$release/mcp-grafana_1.4.2_checksums.txt" -OutFile $checksums
        $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower()
        $expected = (Select-String -LiteralPath $checksums -Pattern 'mcp-grafana_Windows_x86_64.zip').Line.Split(' ')[0]
        if ($actual -ne $expected) { throw 'Grafana MCP checksum mismatch' }
        Expand-Archive -LiteralPath $archive -DestinationPath $target -Force
    }
} finally { Pop-Location }

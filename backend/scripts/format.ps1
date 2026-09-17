$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    gofmt -w cmd internal migrations/embed.go tests
    if ($LASTEXITCODE -ne 0) { throw 'gofmt failed.' }
    # gofmt emits LF. Preserve the repository's explicitly requested CRLF policy.
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    foreach ($folder in @('cmd', 'internal', 'migrations', 'tests')) {
        Get-ChildItem -LiteralPath $folder -Recurse -File -Filter '*.go' | ForEach-Object {
            $text = [System.IO.File]::ReadAllText($_.FullName)
            [System.IO.File]::WriteAllText($_.FullName, ($text -replace "`r?`n", "`r`n"), $utf8)
        }
    }
} finally { Pop-Location }

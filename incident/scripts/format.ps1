$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Get-ChildItem $root -Recurse -File -Filter *.go | Where-Object { $_.FullName -notmatch '[\\/]\.local[\\/]' } | ForEach-Object {
    gofmt -w $_.FullName
    if ($LASTEXITCODE -ne 0) { throw 'gofmt failed.' }
    $content = [IO.File]::ReadAllText($_.FullName) -replace "`r?`n", "`r`n"
    [IO.File]::WriteAllText($_.FullName, $content, [Text.UTF8Encoding]::new($false))
}

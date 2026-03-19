$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pytestLocalAppData = Join-Path $repoRoot ".pytest-localappdata"
$pytestBinary = Join-Path $repoRoot ".venv\\Scripts\\pytest.exe"

New-Item -ItemType Directory -Force -Path $pytestLocalAppData | Out-Null
$env:LOCALAPPDATA = $pytestLocalAppData

& $pytestBinary @args

$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (!(Test-Path -LiteralPath (Join-Path $projectRoot '.venv/Scripts/python.exe'))) {
  py -3.11 -m venv .venv
  if ($LASTEXITCODE) { throw 'Install Python 3.11 or create .venv using your supported Python version.' }
}
& ./.venv/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed. Check network access and the supported Python version.' }
& ./.venv/Scripts/python.exe -m pip check
if ($LASTEXITCODE) { throw 'Dependency verification failed.' }
if (!(Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
Write-Host 'Setup complete. Run: ./.venv/Scripts/python.exe scripts/run.py'

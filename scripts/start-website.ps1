param([int]$Port=8897)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$pythonPath=Join-Path $projectRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Run ./scripts/setup.ps1 first.' }
& $pythonPath (Join-Path $PSScriptRoot 'run.py') --port $Port

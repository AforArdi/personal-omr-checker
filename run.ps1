param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CommandArgs)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install the dependencies first; see README.md.' }
if (-not $CommandArgs) { $CommandArgs = @('bot') }
& $pythonPath -m omr_check @CommandArgs
exit $LASTEXITCODE

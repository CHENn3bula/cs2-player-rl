param([ValidateSet('starter', 'full')][string]$Corpus = 'starter')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw 'Run scripts/bootstrap.ps1 first to create the project runtime.'
}
& $PythonPath -m igl serve --corpus $Corpus
exit $LASTEXITCODE

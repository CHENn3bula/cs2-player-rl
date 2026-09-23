param([string]$Python312 = '')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $ProjectRoot
try {
    $ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $ProjectPython)) {
        if (-not $Python312) {
            $BundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
            if (Test-Path -LiteralPath $BundledPython) {
                $Python312 = $BundledPython
            } else {
                throw 'Provide Python 3.12: .\scripts\bootstrap.ps1 -Python312 C:\Path\python.exe'
            }
        }
        & $Python312 -c 'import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 is required"'
        if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
        & $Python312 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' }
    }
    & $ProjectPython -m pip install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Main dependency installation failed.' }
    & $ProjectPython -m pip install -e . --no-deps
    if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    & $ProjectPython scripts/setup_decoy.py --install
    if ($LASTEXITCODE -ne 0) { throw 'DECOY setup failed.' }
    & $ProjectPython -m igl fetch
    if ($LASTEXITCODE -ne 0) { throw 'Data fetch failed.' }
    & $ProjectPython -m igl prepare
    if ($LASTEXITCODE -ne 0) { throw 'Data normalization failed.' }
    & $ProjectPython -m igl export-map
    if ($LASTEXITCODE -ne 0) { throw 'Navigation export failed.' }
    & $ProjectPython scripts/verify.py
    if ($LASTEXITCODE -ne 0) { throw 'Verification failed; see reports.' }
    Write-Output 'Foundation ready. Start the viewer with .\scripts\serve.ps1'
} finally {
    Pop-Location
}

param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    & $Python -c 'import sys; assert sys.version_info >= (3,11), "Python >= 3.11 required"'
    if ($LASTEXITCODE -ne 0) { throw 'Chon Python >= 3.11 bang tham so -Python.' }
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Khong tao duoc .venv.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements-models.txt
    if ($LASTEXITCODE -ne 0) { throw 'Cai thu vien that bai.' }
    & '.\.venv\Scripts\python.exe' -m defi_models check
    if ($LASTEXITCODE -ne 0) { throw 'Data chua qua preflight; xem thong bao ben tren.' }
} finally { Pop-Location }

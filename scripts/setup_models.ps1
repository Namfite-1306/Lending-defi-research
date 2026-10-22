param(
    [string]$Python = 'python',
    [switch]$Repair,
    [switch]$SkipDataCheck
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        'import sys; assert sys.version_info >= (3,11), "Python >= 3.11 required"' | & $Python -
        if ($LASTEXITCODE -ne 0) { throw 'Chon Python >= 3.11 bang tham so -Python.' }
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Khong tao duoc .venv.' }
    }
    'import sys; assert sys.version_info >= (3,11), "Python >= 3.11 required"; print(sys.version)' | & '.\.venv\Scripts\python.exe' -
    if ($LASTEXITCODE -ne 0) { throw 'Python trong .venv khong chay duoc hoac qua cu; tao moi truong rieng bang Python >= 3.11.' }
    $pipArguments = @('-m', 'pip', 'install', '-r', 'requirements-models.txt')
    if ($Repair) { $pipArguments += @('--force-reinstall', '--no-cache-dir', '--only-binary=:all:') }
    & '.\.venv\Scripts\python.exe' @pipArguments
    if ($LASTEXITCODE -ne 0) { throw 'Cai thu vien that bai.' }
    # Check compiled extensions too: pip may accept metadata left by another Python.
    'import numpy, scipy; from scipy.optimize import minimize; from scipy.special import expit, gammaln; print("NumPy", numpy.__version__, "SciPy", scipy.__version__)' | & '.\.venv\Scripts\python.exe' -
    if ($LASTEXITCODE -ne 0) { throw 'NumPy/SciPy khong import duoc. Chay lai scripts/setup_models.ps1 -Repair -SkipDataCheck de cai wheel dung Python cua .venv.' }
    if (-not $SkipDataCheck) {
        & '.\.venv\Scripts\python.exe' -m defi_models check
        if ($LASTEXITCODE -ne 0) { throw 'Thu vien da import duoc, nhung data chua qua preflight; xem thong bao ben tren.' }
    }
} finally { Pop-Location }

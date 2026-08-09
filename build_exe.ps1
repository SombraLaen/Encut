$ErrorActionPreference = "Stop"
$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $baseDir "runtime\python\python.exe"

if (-not (Test-Path $pythonPath)) {
    $pythonPath = "python"
}

Write-Host "Building Encut standalone executable..." -ForegroundColor Cyan
Write-Host "Using Python: $pythonPath" -ForegroundColor Gray

$args = @(
    "-m", "nuitka",
    "--standalone",
    "--onefile",
    "--windows-disable-console",
    "--include-package=tkinter",
    "--include-package=encut_web",
    "--include-data-files=silence_cutter.py=.",
    "--include-data-dir=encut_static=encut_static",
    "--include-data-files=presets_ajustes.json=.",
    "--include-data-files=update_config.json=.",
    "--output-dir=$baseDir\dist",
    "--output-filename=Encut.exe",
    "--assume-yes-for-downloads",
    "$baseDir\silence_cutter.py"
)

& python $args

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild successful! Output: $baseDir\dist\Encut.exe" -ForegroundColor Green
} else {
    Write-Host "`nBuild failed!" -ForegroundColor Red
}

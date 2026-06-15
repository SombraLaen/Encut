[CmdletBinding()]
param(
    [switch]$Silent,
    [switch]$RemoverDados,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$AppName = "Encut"
$AppId = "Encut"
$Root = Split-Path -Parent $PSCommandPath
$InstallDir = Join-Path $Root "instalacao"
$ManifestPath = Join-Path $InstallDir "instalacao.json"
$LogPath = Join-Path $InstallDir "desinstalador.log"

function Write-UninstallerLog {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    if (-not $Silent) {
        Write-Host $line
    }

    if (-not $DryRun) {
        if (-not (Test-Path -LiteralPath $InstallDir)) {
            New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        }
        Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    }
}

function Get-SpecialFolderPath {
    param(
        [string]$Name,
        [string]$Fallback
    )

    $path = [Environment]::GetFolderPath($Name)
    if ([string]::IsNullOrWhiteSpace($path)) {
        return $Fallback
    }
    return $path
}

function Read-InstallManifest {
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    }
    catch {
        Write-UninstallerLog "Aviso: manifesto de instalacao invalido. Usando caminhos padrao."
        return $null
    }
}

function Remove-ItemIfExists {
    param(
        [string]$Path,
        [switch]$Recurse
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    if ($DryRun) {
        Write-UninstallerLog "DRY-RUN: removeria $Path"
        return
    }

    if ($Recurse) {
        Remove-Item -LiteralPath $Path -Force -Recurse
    }
    else {
        Remove-Item -LiteralPath $Path -Force
    }
    Write-UninstallerLog "Removido: $Path"
}

function Remove-UninstallEntry {
    $registryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"
    if (-not (Test-Path -LiteralPath $registryPath)) {
        return
    }

    if ($DryRun) {
        Write-UninstallerLog "DRY-RUN: removeria registro $registryPath"
        return
    }

    Remove-Item -LiteralPath $registryPath -Force -Recurse
    Write-UninstallerLog "Registro de desinstalacao removido."
}

$desktopDir = Get-SpecialFolderPath -Name "DesktopDirectory" -Fallback (Join-Path $env:USERPROFILE "Desktop")
$programsDir = Get-SpecialFolderPath -Name "Programs" -Fallback (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs")
$startMenuDir = Join-Path $programsDir $AppName

$manifest = Read-InstallManifest
if ($manifest -ne $null) {
    $desktopShortcut = [string]$manifest.desktop_shortcut
    $startMenuShortcut = [string]$manifest.start_menu_shortcut
    $startMenuUninstallShortcut = [string]$manifest.start_menu_uninstall_shortcut
}
else {
    $desktopShortcut = Join-Path $desktopDir "$AppName.lnk"
    $startMenuShortcut = Join-Path $startMenuDir "$AppName.lnk"
    $startMenuUninstallShortcut = Join-Path $startMenuDir "Desinstalar $AppName.lnk"
}

Write-UninstallerLog "Iniciando desinstalacao do $AppName."
Write-UninstallerLog "Pasta da aplicacao preservada: $Root"

Remove-ItemIfExists -Path $desktopShortcut
Remove-ItemIfExists -Path $startMenuShortcut
Remove-ItemIfExists -Path $startMenuUninstallShortcut

if (Test-Path -LiteralPath $startMenuDir -PathType Container) {
    $remaining = Get-ChildItem -LiteralPath $startMenuDir -Force
    if ($remaining.Count -eq 0) {
        Remove-ItemIfExists -Path $startMenuDir -Recurse
    }
}

Remove-UninstallEntry
Remove-ItemIfExists -Path $ManifestPath

if ($RemoverDados) {
    Write-UninstallerLog "Removendo dados gerados dentro da pasta Encut."
    Remove-ItemIfExists -Path (Join-Path $Root "relatorios") -Recurse
    Remove-ItemIfExists -Path (Join-Path $Root "backups") -Recurse
    Remove-ItemIfExists -Path (Join-Path $Root "presets_ajustes.json")
}
else {
    Write-UninstallerLog "Relatorios, backups e presets foram preservados."
}

Write-UninstallerLog "Desinstalacao concluida."

if (-not $Silent) {
    Write-Host ""
    Write-Host "$AppName foi removido dos atalhos e da lista de aplicativos."
    Write-Host "A pasta Encut foi preservada: $Root"
}

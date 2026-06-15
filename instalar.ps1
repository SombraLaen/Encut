[CmdletBinding()]
param(
    [switch]$NoDesktopShortcut,
    [switch]$NoStartMenuShortcut,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$AppName = "Encut"
$AppId = "Encut"
$Root = Split-Path -Parent $PSCommandPath
$ExePath = Join-Path $Root "iniciar.exe"
$ScriptPath = Join-Path $Root "silence_cutter.py"
$VersionPath = Join-Path $Root "VERSION"
$InstallDir = Join-Path $Root "instalacao"
$ManifestPath = Join-Path $InstallDir "instalacao.json"
$LogPath = Join-Path $InstallDir "instalador.log"
$UninstallScript = Join-Path $Root "desinstalar.ps1"

function Write-InstallerLog {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line

    if (-not $DryRun) {
        if (-not (Test-Path -LiteralPath $InstallDir)) {
            New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        }
        Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    }
}

function Require-File {
    param(
        [string]$Path,
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Description nao encontrado: $Path"
    }
}

function Get-AppVersion {
    if (Test-Path -LiteralPath $VersionPath -PathType Leaf) {
        $value = (Get-Content -LiteralPath $VersionPath -Raw).Trim()
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }
    return "0.0.0"
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

function New-AppShortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$Description,
        [string]$IconLocation
    )

    if ($DryRun) {
        Write-InstallerLog "DRY-RUN: criaria atalho: $ShortcutPath"
        return
    }

    $shortcutDir = Split-Path -Parent $ShortcutPath
    if (-not (Test-Path -LiteralPath $shortcutDir)) {
        New-Item -ItemType Directory -Force -Path $shortcutDir | Out-Null
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.Description = $Description
    if (-not [string]::IsNullOrWhiteSpace($Arguments)) {
        $shortcut.Arguments = $Arguments
    }
    if (-not [string]::IsNullOrWhiteSpace($IconLocation)) {
        $shortcut.IconLocation = $IconLocation
    }
    $shortcut.Save()
}

function Set-UninstallEntry {
    param(
        [string]$Version
    )

    $registryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"
    $uninstallCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $UninstallScript
    $quietUninstallCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -Silent' -f $UninstallScript

    if ($DryRun) {
        Write-InstallerLog "DRY-RUN: registraria desinstalador em $registryPath"
        return
    }

    New-Item -Path $registryPath -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name "DisplayName" -Value $AppName -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name "DisplayVersion" -Value $Version -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name "Publisher" -Value "Codex local" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name "InstallLocation" -Value $Root -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name "DisplayIcon" -Value $ExePath -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name "UninstallString" -Value $uninstallCommand -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name "QuietUninstallString" -Value $quietUninstallCommand -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name "NoModify" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name "NoRepair" -Value 1 -PropertyType DWord -Force | Out-Null
}

function Save-Manifest {
    param(
        [string]$Version,
        [string]$DesktopShortcut,
        [string]$StartMenuShortcut,
        [string]$StartMenuUninstallShortcut
    )

    if ($DryRun) {
        Write-InstallerLog "DRY-RUN: salvaria manifesto em $ManifestPath"
        return
    }

    if (-not (Test-Path -LiteralPath $InstallDir)) {
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    }

    $manifest = [ordered]@{
        app_name = $AppName
        app_id = $AppId
        version = $Version
        installed_at = (Get-Date).ToString("s")
        install_location = $Root
        desktop_shortcut = $DesktopShortcut
        start_menu_shortcut = $StartMenuShortcut
        start_menu_uninstall_shortcut = $StartMenuUninstallShortcut
        uninstall_registry_key = "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"
    }

    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8
}

function Test-CommandAvailable {
    param([string[]]$Names)

    foreach ($name in $Names) {
        if (Get-Command $name -ErrorAction SilentlyContinue) {
            return $true
        }
    }
    return $false
}

Require-File -Path $ExePath -Description "Executavel iniciar.exe"
Require-File -Path $ScriptPath -Description "Arquivo principal silence_cutter.py"
Require-File -Path $UninstallScript -Description "Script de desinstalacao"

$version = Get-AppVersion
$desktopDir = Get-SpecialFolderPath -Name "DesktopDirectory" -Fallback (Join-Path $env:USERPROFILE "Desktop")
$programsDir = Get-SpecialFolderPath -Name "Programs" -Fallback (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs")
$startMenuDir = Join-Path $programsDir $AppName
$desktopShortcut = Join-Path $desktopDir "$AppName.lnk"
$startMenuShortcut = Join-Path $startMenuDir "$AppName.lnk"
$startMenuUninstallShortcut = Join-Path $startMenuDir "Desinstalar $AppName.lnk"
$uninstallArguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $UninstallScript
$manifestDesktopShortcut = ""
$manifestStartMenuShortcut = ""
$manifestStartMenuUninstallShortcut = ""

Write-InstallerLog "Iniciando instalacao do $AppName v$version."
Write-InstallerLog "Pasta da aplicacao: $Root"

if (-not (Test-CommandAvailable -Names @("pythonw.exe", "python.exe", "py.exe"))) {
    Write-InstallerLog "Aviso: Python nao foi encontrado no PATH. O app pode pedir instalacao do Python ao abrir."
}

if (-not $NoDesktopShortcut) {
    New-AppShortcut `
        -ShortcutPath $desktopShortcut `
        -TargetPath $ExePath `
        -Arguments "" `
        -WorkingDirectory $Root `
        -Description "Abrir $AppName" `
        -IconLocation $ExePath
    Write-InstallerLog "Atalho da area de trabalho configurado: $desktopShortcut"
    $manifestDesktopShortcut = $desktopShortcut
}

if (-not $NoStartMenuShortcut) {
    New-AppShortcut `
        -ShortcutPath $startMenuShortcut `
        -TargetPath $ExePath `
        -Arguments "" `
        -WorkingDirectory $Root `
        -Description "Abrir $AppName" `
        -IconLocation $ExePath

    New-AppShortcut `
        -ShortcutPath $startMenuUninstallShortcut `
        -TargetPath "powershell.exe" `
        -Arguments $uninstallArguments `
        -WorkingDirectory $Root `
        -Description "Desinstalar $AppName" `
        -IconLocation $ExePath

    Write-InstallerLog "Atalhos do Menu Iniciar configurados em: $startMenuDir"
    $manifestStartMenuShortcut = $startMenuShortcut
    $manifestStartMenuUninstallShortcut = $startMenuUninstallShortcut
}

Set-UninstallEntry -Version $version
Save-Manifest `
    -Version $version `
    -DesktopShortcut $manifestDesktopShortcut `
    -StartMenuShortcut $manifestStartMenuShortcut `
    -StartMenuUninstallShortcut $manifestStartMenuUninstallShortcut

if ($DryRun) {
    Write-InstallerLog "Simulacao de instalacao concluida."
}
else {
    Write-InstallerLog "Instalacao concluida."
}
Write-Host ""
if ($DryRun) {
    Write-Host "$AppName seria instalado para o usuario atual."
}
else {
    Write-Host "$AppName instalado para o usuario atual."
}
Write-Host "A aplicacao continua na pasta: $Root"

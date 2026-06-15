[CmdletBinding()]
param(
    [string]$BaseUrl = "",
    [string]$Notes = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSCommandPath
$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw).Trim()
$Dist = Join-Path $Root "dist_site"
$Work = Join-Path $Dist "_package"
$PackageName = "Encut_$Version.zip"
$PackagePath = Join-Path $Dist $PackageName
$ManifestPath = Join-Path $Dist "update.json"
$SiteBundlePath = Join-Path $Dist "Encut_site_upload_$Version.zip"

New-Item -ItemType Directory -Force -Path $Dist | Out-Null
if (Test-Path -LiteralPath $Work) { Remove-Item -LiteralPath $Work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Work | Out-Null

$files = @("EncutSetup.exe", "README.md", "VERSION", "CHANGELOG.md")
foreach ($file in $files) {
    Copy-Item -LiteralPath (Join-Path $Root $file) -Destination (Join-Path $Work $file) -Force
}

if (Test-Path -LiteralPath $PackagePath) { Remove-Item -LiteralPath $PackagePath -Force }
Compress-Archive -Path (Join-Path $Work "*") -DestinationPath $PackagePath -Force
$Hash = (Get-FileHash -LiteralPath $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()

$zipUrl = $PackageName
if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) {
    $zipUrl = $BaseUrl.TrimEnd("/") + "/" + $PackageName
}
if ([string]::IsNullOrWhiteSpace($Notes)) {
    $Notes = "Encut v$Version"
}

$manifest = [ordered]@{
    app_name = "Encut"
    version = $Version
    published_at = (Get-Date).ToString("s")
    zip_url = $zipUrl
    sha256 = $Hash
    notes = $Notes
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

@"
$Hash  $PackageName
"@ | Set-Content -LiteralPath (Join-Path $Dist "SHA256SUMS.txt") -Encoding UTF8

$siteReadme = @"
Encut v$Version - pacote para site

Arquivos para hospedar:
- update.json
- $PackageName

Canal principal recomendado: publique uma release no GitHub com tag v$Version e anexe $PackageName ou EncutSetup.exe.

Fallback por manifesto: configure update_config.json no Encut instalado apontando manifest_url para a URL publica do update.json.
Exemplo:
{
  "enabled": true,
  "check_on_startup": true,
  "github_repo": "",
  "github_branch": "main",
  "manifest_url": "https://seu-site.com/encut/update.json"
}

O campo zip_url no update.json pode ser relativo ao proprio update.json ou absoluto.
"@
$siteReadme | Set-Content -LiteralPath (Join-Path $Dist "README_SITE.txt") -Encoding UTF8

if (Test-Path -LiteralPath $SiteBundlePath) { Remove-Item -LiteralPath $SiteBundlePath -Force }
Compress-Archive -Path $ManifestPath, $PackagePath, (Join-Path $Dist "SHA256SUMS.txt"), (Join-Path $Dist "README_SITE.txt") -DestinationPath $SiteBundlePath -Force
Remove-Item -LiteralPath $Work -Recurse -Force

Write-Host "Pacote gerado: $PackagePath"
Write-Host "Manifesto: $ManifestPath"
Write-Host "Bundle para upload: $SiteBundlePath"
Write-Host "SHA256: $Hash"

param([string]$AnkiData = (Join-Path $env:APPDATA 'Anki2'), [switch]$Update)
$ErrorActionPreference = 'Stop'
$taskSource = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\spanish_helper'))
$taskAddonsRoot = [IO.Path]::GetFullPath((Join-Path $AnkiData 'addons21'))
$taskDestination = [IO.Path]::GetFullPath((Join-Path $taskAddonsRoot 'spanish_helper'))
if (-not $taskDestination.StartsWith($taskAddonsRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Invalid add-on destination.' }
$taskAnkiRunning = [bool](Get-Process -Name anki -ErrorAction SilentlyContinue)
if (Test-Path -LiteralPath $taskDestination) {
    if (-not $Update) { throw 'Spanish Helper is already installed. Use -Update or install the .ankiaddon package from Anki.' }
    $taskBackupRoot = Join-Path $AnkiData 'addon_backups'
    $taskBackup = Join-Path $taskBackupRoot ('spanish_helper_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
    New-Item -ItemType Directory -Path $taskBackup -Force | Out-Null
    Get-ChildItem -LiteralPath $taskDestination | Where-Object { $_.Name -notin @('__pycache__','user_files') } | Copy-Item -Destination $taskBackup -Recurse
    Write-Output "Previous add-on code and settings backed up to $taskBackup"
}
New-Item -ItemType Directory -Path $taskDestination -Force | Out-Null
Get-ChildItem -LiteralPath $taskSource | Where-Object { $_.Name -notin @('__pycache__','user_files') } | Copy-Item -Destination $taskDestination -Recurse -Force
$taskMetaPath = Join-Path $taskDestination 'meta.json'
if (-not (Test-Path -LiteralPath $taskMetaPath)) {
    $taskMeta = @{ name = 'Spanish Helper - Pronunciation, hints and translation checks'; disabled = $false }
    [IO.File]::WriteAllText($taskMetaPath, ($taskMeta | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
}
Write-Output "Installed Spanish Helper to $taskDestination"
if ($taskAnkiRunning) { Write-Output 'Restart Anki to load the new add-on, then start a review.' }
else { Write-Output 'Open Anki and start a review.' }
Write-Output 'Settings: Tools > Spanish Helper.'

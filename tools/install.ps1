param([string]$AnkiData = (Join-Path $env:APPDATA 'Anki2'))
$ErrorActionPreference = 'Stop'
$taskSource = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\spanish_helper'))
$taskAddonsRoot = [IO.Path]::GetFullPath((Join-Path $AnkiData 'addons21'))
$taskDestination = [IO.Path]::GetFullPath((Join-Path $taskAddonsRoot 'spanish_helper'))
if (-not $taskDestination.StartsWith($taskAddonsRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Invalid add-on destination.' }
$taskAnkiRunning = [bool](Get-Process -Name anki -ErrorAction SilentlyContinue)
if (Test-Path -LiteralPath $taskDestination) { throw 'Spanish Helper is already installed. Use the .ankiaddon package from Anki to update it.' }
New-Item -ItemType Directory -Path $taskDestination -Force | Out-Null
Get-ChildItem -LiteralPath $taskSource | Where-Object { $_.Name -notin @('__pycache__','user_files') } | Copy-Item -Destination $taskDestination -Recurse
$taskMeta = @{ name = 'Spanish Helper - Pronunciation and B1 hints'; disabled = $false }
[IO.File]::WriteAllText((Join-Path $taskDestination 'meta.json'), ($taskMeta | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
Write-Output "Installed Spanish Helper to $taskDestination"
if ($taskAnkiRunning) { Write-Output 'Restart Anki to load the new add-on, then start a review.' }
else { Write-Output 'Open Anki and start a review.' }
Write-Output 'Settings: Tools > Spanish Helper.'

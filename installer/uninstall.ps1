<#
.SYNOPSIS
  Removes the PersonalOS program. Your vault is never deleted.

.DESCRIPTION
  Removes, using the record in install.json: the program files, the `personalos`/`pos` commands, the PATH entry,
  the scheduled task and the Claude Code skill. Your vault is always kept.
  Your index/logs folder and archive folder are kept unless you ask for them to be removed AND confirm by
  typing DELETE (or pass -ConfirmDelete DELETE when running non-interactively).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File installer\uninstall.ps1
#>
[CmdletBinding()]
param(
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'PersonalOS'),
  [switch]$RemoveIndex,
  [switch]$RemoveArchive,
  [string]$ConfirmDelete,
  [switch]$NonInteractive
)
$ErrorActionPreference = 'Stop'
function Info($text) { Write-Host "  $text" }
function AskYesNo($question) {
  if ($NonInteractive) { return $false }
  $a = Read-Host "  $question (y/N)"
  return (-not [string]::IsNullOrWhiteSpace($a)) -and $a.Trim().ToLower().StartsWith('y')
}
function ConfirmDeletion($what) {
  if ($NonInteractive) { return $ConfirmDelete -ceq 'DELETE' }
  Write-Host "  This permanently deletes $what." -ForegroundColor Yellow
  return (Read-Host '  Type DELETE to confirm') -ceq 'DELETE'
}

$recordFile = Join-Path $InstallDir 'install.json'
if (-not (Test-Path $recordFile)) { Write-Host "No PersonalOS installation found in $InstallDir." -ForegroundColor Red; exit 1 }
$r = Get-Content -Raw $recordFile | ConvertFrom-Json
$cmd = Join-Path $InstallDir 'bin\personalos.cmd'
if ($r.config_path) { $env:PERSONALOS_CONFIG = $r.config_path }
Write-Host "Uninstalling PersonalOS $($r.version) from $InstallDir" -ForegroundColor Cyan

# Integrations: removes only what PersonalOS created (the Claude Code skill); archives are kept.
if ((Test-Path $cmd) -and $r.integrations) {
  foreach ($name in $r.integrations) { & $cmd integrations disable $name | ForEach-Object { Info $_ } }
}
$configFile = if (Test-Path $cmd) { & $cmd config path } else { $null }

if ($r.scheduled_task) {
  try { Unregister-ScheduledTask -TaskName $r.scheduled_task -Confirm:$false; Info "Removed scheduled task '$($r.scheduled_task)'." }
  catch { Info "Scheduled task '$($r.scheduled_task)' was already gone." }
}
if ($r.path_added) {
  $bin = Join-Path $InstallDir 'bin'
  $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
  $kept = ($userPath -split ';') | Where-Object { $_ -and $_ -ne $bin }
  [Environment]::SetEnvironmentVariable('Path', ($kept -join ';'), 'User')
  Info 'Removed PersonalOS from your PATH.'
}
foreach ($d in 'app', 'bin') {
  $p = Join-Path $InstallDir $d
  if (Test-Path $p) { Remove-Item -Recurse -Force $p; Info "Removed $p" }
}

$wantIndex = $RemoveIndex -or (AskYesNo "Also delete the search index and logs in $($r.data_dir)? (your notes are not in there)")
if ($wantIndex -and (Test-Path $r.data_dir)) {
  if (ConfirmDeletion "the index and logs in $($r.data_dir)") { Remove-Item -Recurse -Force $r.data_dir; Info "Deleted $($r.data_dir)" }
  else { Info "Kept $($r.data_dir)" }
}
if ($r.archive_dir -and (Test-Path $r.archive_dir)) {
  $wantArchive = $RemoveArchive -or (AskYesNo "Also delete the archive in $($r.archive_dir)? (it contains archived conversations and documents)")
  if ($wantArchive -and (ConfirmDeletion "everything in the archive $($r.archive_dir)")) { Remove-Item -Recurse -Force $r.archive_dir; Info "Deleted $($r.archive_dir)" }
}
$dataGone = -not (Test-Path $r.data_dir)
if ($dataGone -and $configFile -and (Test-Path $configFile)) {
  Remove-Item -Force $configFile
  Info "Removed configuration $configFile"
}
Remove-Item -Force $recordFile
if (-not (Get-ChildItem -Force $InstallDir -ErrorAction SilentlyContinue)) { Remove-Item -Force $InstallDir }

Write-Host ""
Write-Host 'PersonalOS has been removed.' -ForegroundColor Green
Info "Your vault was NOT touched: $($r.vault)"
if (Test-Path $r.data_dir) { Info "Index and logs kept: $($r.data_dir)" }
if ($r.archive_dir -and (Test-Path $r.archive_dir)) { Info "Archive kept: $($r.archive_dir)" }
if (-not $dataGone -and $configFile -and (Test-Path $configFile)) { Info "Configuration kept (reinstalling picks it up): $configFile" }

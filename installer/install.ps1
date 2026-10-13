<#
.SYNOPSIS
  Installs PersonalOS for the current Windows user. No administrator rights and no internet connection needed.

.DESCRIPTION
  1. Checks requirements (Windows 10/11, Python 3.10+ with SQLite FTS5)
  2. Shows your drives and free space
  3. Lets you choose where the vault, the index (SSD) and the optional archive (HDD) live
  4. Copies PersonalOS to %LOCALAPPDATA%\PersonalOS and creates the `personalos` and `pos` commands
  5. Creates your vault and builds the search index
  6. Optionally enables integrations (Claude Code, Obsidian, MCP)
  7. Optionally restricts folder permissions and schedules weekly maintenance
  8. Runs a health check and explains how to use it
  Everything it creates is recorded in install.json, which uninstall.ps1 uses.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File installer\install.ps1
.EXAMPLE
  install.ps1 -NonInteractive -VaultPath "D:\Notes\PersonalOS" -ArchivePath "E:\PersonalOS Archive" -AddToPath
#>
[CmdletBinding()]
param(
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'PersonalOS'),
  [string]$VaultPath,
  [string]$DataPath,
  [string]$ArchivePath,
  [string]$ConfigPath,
  [switch]$Demo,
  [switch]$Adopt,
  [string[]]$Integrations = @(),
  [switch]$AddToPath,
  [switch]$ScheduleMaintenance,
  [switch]$RestrictPermissions,
  [switch]$NonInteractive
)
$ErrorActionPreference = 'Stop'
$Source = Split-Path -Parent $PSScriptRoot
$Version = (Select-String -Path (Join-Path $Source 'personalos\__init__.py') -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
$TaskName = 'PersonalOS Weekly Maintenance'

function Step($n, $text) { Write-Host ""; Write-Host "[$n/9] $text" -ForegroundColor Cyan }
function Info($text) { Write-Host "      $text" }
function Fail($text) { Write-Host ""; Write-Host "Installation stopped: $text" -ForegroundColor Red; exit 1 }
function Ask($question, $default) {
  if ($NonInteractive) { return $default }
  $suffix = if ($default) { " [$default]" } else { '' }
  $answer = Read-Host "      $question$suffix"
  if ([string]::IsNullOrWhiteSpace($answer)) { return $default } else { return $answer.Trim().Trim('"') }
}
function AskYesNo($question, [bool]$default) {
  if ($NonInteractive) { return $false }  # non-interactive runs only do what was switched on explicitly
  $d = if ($default) { 'Y/n' } else { 'y/N' }
  $answer = Read-Host "      $question ($d)"
  if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
  return $answer.Trim().ToLower().StartsWith('y')
}
function IsUnder($child, $parent) {
  $c = [IO.Path]::GetFullPath($child).TrimEnd('\') + '\'
  $p = [IO.Path]::GetFullPath($parent).TrimEnd('\') + '\'
  return $c.StartsWith($p, [StringComparison]::OrdinalIgnoreCase)
}

Write-Host "PersonalOS $Version installer" -ForegroundColor Green
Write-Host "Local-first: nothing is uploaded, no account is needed, no admin rights are used."

# ------------------------------------------------------------------ 1. requirements
Step 1 'Checking requirements'
$os = [Environment]::OSVersion.Version
if ($os.Major -lt 10) { Fail "Windows 10 or 11 is required (found $os)." }
Info "Windows $($os.Major).0 build $($os.Build): OK"
Info "PowerShell $($PSVersionTable.PSVersion): OK"

$python = $null
# A probe file, not `python -c`: Windows PowerShell 5.1 strips quotes from native-command arguments.
$probe = Join-Path ([IO.Path]::GetTempPath()) "personalos-probe-$PID.py"
[IO.File]::WriteAllText($probe, "import sys, sqlite3`nc = sqlite3.connect(':memory:')`nc.execute('create virtual table t using fts5(x)')`nprint(sys.executable)`nprint('%d.%d' % sys.version_info[:2])`n")
foreach ($candidate in @(@('py', '-3'), @('python'), @('python3'))) {
  $exe = $candidate[0]
  if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
  $path = (Get-Command $exe).Source
  if ($path -like '*\WindowsApps\*' -and $exe -ne 'py') { continue }  # Microsoft Store stub opens the Store
  try {
    $args2 = @($candidate | Select-Object -Skip 1) + @('-I', $probe)
    $out = @(& $exe @args2 2>$null)
    if ($LASTEXITCODE -eq 0 -and $out.Count -ge 2) {
      $ver = [version]$out[1]
      if ($ver -ge [version]'3.10') { $python = $out[0]; Info "Python $ver with SQLite FTS5: OK ($python)"; break }
      Info "Python $ver found at $($out[0]) but 3.10 or newer is required"
    }
  } catch { }
}
Remove-Item -Force $probe -ErrorAction SilentlyContinue
if (-not $python) {
  Fail "Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH') or run: winget install Python.Python.3.12  Then run this installer again."
}

# ------------------------------------------------------------------ 2. storage
Step 2 'Detecting storage'
$mediaByLetter = @{}
try {
  foreach ($disk in Get-PhysicalDisk) {
    foreach ($part in (Get-Partition -DiskNumber $disk.DeviceId -ErrorAction SilentlyContinue)) {
      if ($part.DriveLetter) { $mediaByLetter[[string]$part.DriveLetter] = [string]$disk.MediaType }
    }
  }
} catch { }
foreach ($d in Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -gt 0 }) {
  $media = $mediaByLetter[$d.Name]
  if (-not $media -or $media -eq 'Unspecified') { $media = 'type unknown' }
  Info ("{0}:  {1,8} GB free   {2}" -f $d.Name, [math]::Round($d.Free / 1GB, 1).ToString([Globalization.CultureInfo]::InvariantCulture), $media)
}
Info 'Tip: keep the index on an SSD (fast search). An archive drive (HDD) is optional, for old material.'

# ------------------------------------------------------------------ 3. locations
Step 3 'Choosing locations'
$existingConfig = if ($ConfigPath) { [IO.Path]::GetFullPath($ConfigPath) } else { Join-Path $env:APPDATA 'PersonalOS\config.json' }
if (Test-Path $existingConfig) {
  # Reinstall or upgrade: keep the user's existing locations.
  $c = Get-Content -Raw $existingConfig | ConvertFrom-Json
  $VaultPath = $c.vault; $DataPath = $c.data_dir; $ArchivePath = $c.archive_dir; $Adopt = $true; $Demo = $false
  Info "Existing configuration found ($existingConfig); keeping its locations."
}
if (-not $VaultPath) { $VaultPath = Ask 'Vault folder (your notes)' (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'PersonalOS Vault') }
if (-not $DataPath) { $DataPath = Ask 'Index and logs folder (SSD recommended)' (Join-Path $InstallDir 'data') }
if (-not $PSBoundParameters.ContainsKey('ArchivePath') -and -not $NonInteractive) {
  $ArchivePath = Ask 'Archive folder on a second drive (leave empty for single-drive mode)' ''
}
$VaultPath = [IO.Path]::GetFullPath($VaultPath)
$DataPath = [IO.Path]::GetFullPath($DataPath)
if ($ArchivePath) { $ArchivePath = [IO.Path]::GetFullPath($ArchivePath) }
if (IsUnder $DataPath $VaultPath) { Fail 'The index folder must not be inside the vault.' }
if ((Test-Path $VaultPath) -and (Get-ChildItem -Force $VaultPath | Select-Object -First 1)) {
  if (-not $Adopt) {
    $Adopt = AskYesNo "$VaultPath already contains files. Use it as your existing vault without changing anything in it?" $false
    if (-not $Adopt) { Fail 'Choose an empty or new vault folder, or use -Adopt for an existing vault.' }
  }
  $Demo = $false
} elseif (-not $PSBoundParameters.ContainsKey('Demo') -and -not $NonInteractive) {
  $Demo = AskYesNo 'Fill the new vault with fictional demo notes so you can try things out?' $false
}
Info "Vault:   $VaultPath$(if ($Adopt) { '  (existing, left unchanged)' })"
Info "Index:   $DataPath"
Info "Archive: $(if ($ArchivePath) { $ArchivePath } else { 'none (single-drive mode)' })"
foreach ($p in @($DataPath) + @($ArchivePath | Where-Object { $_ })) {
  $root = [IO.Path]::GetPathRoot($p)
  if (-not (Test-Path $root)) { Fail "Drive $root is not available." }
}

# ------------------------------------------------------------------ 4. program files
Step 4 'Installing PersonalOS'
$AppDir = Join-Path $InstallDir 'app'
$BinDir = Join-Path $InstallDir 'bin'
New-Item -ItemType Directory -Force -Path $AppDir, $BinDir | Out-Null
if (Test-Path (Join-Path $AppDir 'personalos')) { Remove-Item -Recurse -Force (Join-Path $AppDir 'personalos') }
Copy-Item -Recurse -Path (Join-Path $Source 'personalos') -Destination $AppDir
Get-ChildItem -Recurse -Directory -Filter '__pycache__' $AppDir | Remove-Item -Recurse -Force
$shim = @(
  '@echo off',
  'setlocal',
  "set `"PYTHONPATH=$AppDir`"",
  'set "PERSONALOS_LAUNCHER=%~f0"'
)
if ($ConfigPath) { $shim += "set `"PERSONALOS_CONFIG=$([IO.Path]::GetFullPath($ConfigPath))`"" }
$shim += "`"$python`" -X utf8 -m personalos %*"
foreach ($name in 'personalos.cmd', 'pos.cmd') {
  [IO.File]::WriteAllLines((Join-Path $BinDir $name), $shim, (New-Object Text.UTF8Encoding $false))
}
$cmd = Join-Path $BinDir 'personalos.cmd'
Info "Program: $AppDir"
Info "Commands: $BinDir\personalos.cmd (and pos.cmd)"

$record = [ordered]@{
  version = $Version; installed = (Get-Date -Format s); install_dir = $InstallDir; python = $python
  config_path = $(if ($ConfigPath) { [IO.Path]::GetFullPath($ConfigPath) } else { $null })
  vault = $VaultPath; data_dir = $DataPath; archive_dir = $ArchivePath
  path_added = $false; scheduled_task = $null; integrations = @(); restricted = @()
}
function SaveRecord { $record | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $InstallDir 'install.json') }
SaveRecord

# ------------------------------------------------------------------ 5. vault and index
Step 5 'Creating your vault and search index'
if ($ConfigPath) { $env:PERSONALOS_CONFIG = [IO.Path]::GetFullPath($ConfigPath) }
$configFile = & $cmd config path
if (Test-Path $configFile) {
  Info "An existing configuration was found at $configFile; it is kept as it is."
} else {
  $initArgs = @('init', '--vault', $VaultPath, '--data', $DataPath)
  if ($ArchivePath) { $initArgs += @('--archive', $ArchivePath) }
  if ($Demo) { $initArgs += '--demo' }
  if ($Adopt) { $initArgs += '--adopt' }
  & $cmd @initArgs
  if ($LASTEXITCODE -ne 0) { Fail 'PersonalOS could not create the vault (see the message above).' }
}

# ------------------------------------------------------------------ 6. integrations
Step 6 'Optional integrations'
$claudeHome = Join-Path $env:USERPROFILE '.claude'
$wanted = @($Integrations)
if (-not $NonInteractive) {
  if ((Test-Path $claudeHome) -and (AskYesNo 'Claude Code was found. Let it search PersonalOS, and archive its conversations?' $false)) { $wanted += 'claude_code' }
  if (AskYesNo 'Do you use Obsidian to edit notes?' $false) { $wanted += 'obsidian' }
  if (AskYesNo 'Enable the MCP server so other AI assistants can search PersonalOS (read-only)?' $false) { $wanted += 'mcp' }
}
foreach ($name in $wanted | Select-Object -Unique) {
  & $cmd integrations enable $name
  if ($LASTEXITCODE -eq 0) { $record.integrations += $name } else { Info "Skipped $name." }
}
if (-not $record.integrations) { Info 'None enabled. Add them later with: personalos integrations enable <name>' }
SaveRecord

# ------------------------------------------------------------------ 7. permissions and maintenance
Step 7 'Permissions and maintenance'
$profileDir = [Environment]::GetFolderPath('UserProfile')
$toRestrict = @($DataPath, $ArchivePath) | Where-Object { $_ -and -not (IsUnder $_ $profileDir) }
if ($toRestrict -and ($RestrictPermissions -or (AskYesNo "Restrict $($toRestrict -join ', ') to your account (plus SYSTEM and Administrators)?" $true))) {
  $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
  foreach ($dir in $toRestrict) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    & icacls $dir /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /Q | Out-Null
    if ($LASTEXITCODE -eq 0) { $record.restricted += $dir; Info "Restricted: $dir" } else { Info "Could not change permissions on $dir (left as they were)." }
  }
} else {
  Info 'Folders inside your user profile are already private to your account.'
}
if ($ScheduleMaintenance -or (AskYesNo 'Run maintenance automatically every Sunday at 19:00? (it only suggests changes)' $false)) {
  try {
    $action = New-ScheduledTaskAction -Execute $cmd -Argument 'maintain --quiet'
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '19:00'
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'PersonalOS: archive, index and write a maintenance report' -Force | Out-Null
    $record.scheduled_task = $TaskName
    Info "Scheduled task '$TaskName' created."
  } catch { Info "Could not create the scheduled task: $($_.Exception.Message)" }
} else {
  Info 'No schedule. Run `personalos maintain` weekly yourself.'
}
SaveRecord

# ------------------------------------------------------------------ 8. PATH
Step 8 'Command line access'
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$onPath = ($userPath -split ';') -contains $BinDir
if ($onPath) { Info 'Already on your PATH.' }
elseif ($AddToPath -or (AskYesNo "Add $BinDir to your PATH so 'personalos' works in any new terminal?" $true)) {
  $newPath = if ([string]::IsNullOrEmpty($userPath)) { $BinDir } else { "$userPath;$BinDir" }
  [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
  $record.path_added = $true
  Info 'Added. Open a new terminal to use it.'
} else {
  Info "Not added. Run it as: `"$cmd`""
}
SaveRecord

# ------------------------------------------------------------------ 9. health check
Step 9 'Health check'
& $cmd doctor
$healthy = ($LASTEXITCODE -eq 0)

Write-Host ""
Write-Host "PersonalOS is installed." -ForegroundColor Green
Write-Host @"

  personalos ui                       open the local interface in your browser
  personalos search <words>           search, most trustworthy sources first
  personalos capture "an idea"        save something to your inbox
  personalos maintain                 weekly tidy-up suggestions (changes nothing)
  personalos backup --to <folder>     verified backup of your vault and settings
  personalos doctor                   health check

  Your notes are plain Markdown in: $VaultPath
  Start with Home.md and fill in 99_System\Identity.md and Goals.md.
  Guide: docs\QUICKSTART.md   Uninstall: installer\uninstall.ps1 (never deletes your notes)
"@
if (-not $healthy) { exit 2 }

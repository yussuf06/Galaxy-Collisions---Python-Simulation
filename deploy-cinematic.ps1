$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath('C:\Users\yusuf\Desktop\galaxy-python-desktop\galaxy-python-desktop')
$expected = 'C:\Users\yusuf\Desktop\galaxy-python-desktop\galaxy-python-desktop'
if ($project -ne $expected -or -not (Test-Path -LiteralPath (Join-Path $project 'AGENTS.md'))) { throw 'Unexpected project target' }
$stage = Join-Path $PSScriptRoot 'cinematic-update'
$files = @('main.py','galaxy_app\appearance.py','galaxy_app\view.py','galaxy_app\window.py','galaxy_app\worker.py','README.md','README-AR.md','test_appearance.py','test_view_ui.py','test_worker.py','launch_here.bat')
foreach ($relative in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $stage $relative))) { throw "Missing staged file: $relative" }
}
$backup = Join-Path $project ('backups\before-cinematic-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
foreach ($relative in $files) {
    $original = Join-Path $project $relative
    if (Test-Path -LiteralPath $original) {
        $saved = Join-Path $backup $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $saved) -Force | Out-Null
        Copy-Item -LiteralPath $original -Destination $saved
    }
}
foreach ($relative in $files) {
    $destination = Join-Path $project $relative
    Copy-Item -LiteralPath (Join-Path $stage $relative) -Destination $destination -Force
    if ((Get-FileHash -LiteralPath $destination).Hash -ne (Get-FileHash -LiteralPath (Join-Path $stage $relative)).Hash) { throw "Verification failed: $relative" }
}
Write-Output "Updated $($files.Count) files; backup: $backup"
$logFolder = Join-Path $project 'logs'
New-Item -ItemType Directory -Path $logFolder -Force | Out-Null
$running = Start-Process -FilePath 'C:\Users\yusuf\.venv\Scripts\python.exe' -ArgumentList ('"' + (Join-Path $project 'main.py') + '"') -WorkingDirectory $project -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logFolder 'desktop-launch.stdout.log') -RedirectStandardError (Join-Path $logFolder 'desktop-launch.stderr.log') -PassThru
Write-Output "Launched Galaxy Encounter process $($running.Id)"

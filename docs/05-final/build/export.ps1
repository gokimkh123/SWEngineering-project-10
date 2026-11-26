param([string]$src, [string]$outDir, [int]$width = 1600)
$ErrorActionPreference = "Stop"
$was = @(Get-CimInstance Win32_Process -Filter "Name='POWERPNT.EXE'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -notmatch '-Embedding' }).Count -gt 0
$ppt = New-Object -ComObject PowerPoint.Application
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Get-ChildItem $outDir -Filter *.png | Remove-Item
$pres = $ppt.Presentations.Open($src, $true, $false, $false)
$h = [int]($width * $pres.PageSetup.SlideHeight / $pres.PageSetup.SlideWidth)
$i = 1
foreach ($s in $pres.Slides) { $s.Export((Join-Path $outDir ("slide{0:D2}.png" -f $i)), "PNG", $width, $h); $i++ }
Write-Output ("slides=" + $pres.Slides.Count + " size=" + $pres.PageSetup.SlideWidth + "x" + $pres.PageSetup.SlideHeight)
$pres.Close()
if (-not $was -and $ppt.Presentations.Count -eq 0) { $ppt.Quit() }
Write-Output ("wasRunning=" + $was)

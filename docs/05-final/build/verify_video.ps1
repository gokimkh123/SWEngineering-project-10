param([string]$src)
$ErrorActionPreference = "Stop"
$was = @(Get-CimInstance Win32_Process -Filter "Name='POWERPNT.EXE'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -notmatch '-Embedding' }).Count -gt 0
$ppt = New-Object -ComObject PowerPoint.Application
$pres = $ppt.Presentations.Open($src, $true, $false, $true)   # 창을 띄워야 미디어 정보가 읽힘
try {
  try { $pres.Windows(1).WindowState = 2 } catch {}
  foreach ($s in $pres.Slides) {
    foreach ($sh in $s.Shapes) {
      if ($sh.Type -eq 16) {
        $mf = $sh.MediaFormat
        Write-Output ("slide=" + $s.SlideIndex + " mediaType=" + $sh.MediaType + " lengthMs=" + $mf.Length + " embedded=" + $mf.IsEmbedded + " effects=" + $s.TimeLine.MainSequence.Count)
      }
    }
  }
} finally {
  $pres.Close()
  if (-not $was -and $ppt.Presentations.Count -eq 0) { $ppt.Quit() }
}

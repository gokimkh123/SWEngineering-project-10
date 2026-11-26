param([string]$src, [string]$dst)
$ErrorActionPreference = "Stop"
$was = @(Get-CimInstance Win32_Process -Filter "Name='POWERPNT.EXE'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -notmatch '-Embedding' }).Count -gt 0
$ppt = New-Object -ComObject PowerPoint.Application
$pres = $ppt.Presentations.Open($src, $false, $false, $false)
try {
$n = 0
foreach ($s in $pres.Slides) {
  foreach ($sh in $s.Shapes) {
    if ($sh.Type -eq 16) {   # msoMedia: 클릭하면 재생 (슬라이드 넘김 대신 영상 시작)
      $eff = $s.TimeLine.MainSequence.AddEffect($sh, 83, 0, 1)   # msoAnimEffectMediaPlay, OnPageClick
      $n++
    }
  }
}
$pres.SaveAs($dst, 24, -1)   # 24 = pptx, -1 = 트루타입 글꼴 포함 (발표 PC에 Pretendard가 없어도 같은 모양)
} finally {
$pres.Close()
if (-not $was -and $ppt.Presentations.Count -eq 0) { $ppt.Quit() }
}
Write-Output ("media=" + $n + " saved=" + $dst)

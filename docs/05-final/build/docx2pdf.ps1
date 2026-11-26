param([string]$src, [string]$pdf)
$ErrorActionPreference = "Stop"
$was = @(Get-Process WINWORD -ErrorAction SilentlyContinue).Count -gt 0
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
try {
  $doc = $w.Documents.Open($src, $false, $true)
  $doc.ExportAsFixedFormat($pdf, 17)
  Write-Output ("pages=" + $doc.ComputeStatistics(2))
  $doc.Close($false)
} finally {
  if (-not $was -and $w.Documents.Count -eq 0) { $w.Quit() }
}
Write-Output ("wasRunning=" + $was)

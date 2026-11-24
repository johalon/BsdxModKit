# pac_index_dump.ps1 — 巨大な pac から「ファイル名一覧（インデックス）」部分だけを小さなファイルに切り出す。
# 読み取りのみ。ゲームのファイルは一切変更しない。
# 使い方（PowerShell）:
#   powershell -ExecutionPolicy Bypass -File pac_index_dump.ps1 -GameDir "<GAME>" -OutDir "<PROJECT>\pac_index\BALDRSKY_DIVEX"
param(
  [Parameter(Mandatory=$true)][string]$GameDir,
  [Parameter(Mandatory=$true)][string]$OutDir
)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Get-ChildItem -Path $GameDir -Filter *.pac | ForEach-Object {
  $fs = [System.IO.File]::OpenRead($_.FullName)
  try {
    $head = New-Object byte[] 12
    [void]$fs.Read($head, 0, 12)
    if ([System.Text.Encoding]::ASCII.GetString($head, 0, 3) -ne 'PAC') { Write-Host "skip (not PAC): $($_.Name)"; return }
    $len = $fs.Length
    $fs.Seek($len - 4, 'Begin') | Out-Null
    $b4 = New-Object byte[] 4
    [void]$fs.Read($b4, 0, 4)
    $isz = [BitConverter]::ToUInt32($b4, 0)
    if ($isz -le 0 -or $isz -gt ($len - 16)) { Write-Host "skip (old-style index?): $($_.Name)"; return }
    $tail = New-Object byte[] ($isz + 4)
    $fs.Seek($len - 4 - $isz, 'Begin') | Out-Null
    [void]$fs.Read($tail, 0, $tail.Length)
    $out = Join-Path $OutDir ($_.Name + '.idx')
    $w = [System.IO.File]::Create($out)
    $w.Write($head, 0, 12); $w.Write($tail, 0, $tail.Length); $w.Close()
    Write-Host ("{0,-20} index {1,10} bytes -> {2}" -f $_.Name, $isz, $out)
  } finally { $fs.Close() }
}
Write-Host "done."

# DeerFlowApp 图标生成脚本
# 用法：替换 static/app-icon.png 后，在此目录运行:
#   powershell -File generate-icons.ps1
#
# 自动生成所有平台所需的各种尺寸图标到 unpackage/res/icons/

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $scriptDir "static\app-icon.png"

if (-not (Test-Path $source)) {
    Write-Host "ERROR: Source icon not found at $source" -ForegroundColor Red
    Write-Host "Place a 1024x1024 PNG at static/app-icon.png" -ForegroundColor Yellow
    exit 1
}

$targetDir = Join-Path $scriptDir "unpackage\res\icons"
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

try {
    $python = (Get-Command python -ErrorAction Stop).Source
} catch {
    Write-Host "ERROR: Python not found" -ForegroundColor Red
    exit 1
}

$srcEscaped = $source.Replace("\", "\\")
$tgtEscaped = $targetDir.Replace("\", "\\")

$tmpFile = Join-Path $env:TEMP "df_icons_$(Get-Random).py"
@"
from PIL import Image
import os
src = r'$srcEscaped'
target = r'$tgtEscaped'
img = Image.open(src)
w, h = img.size
if w != h:
    s = min(w, h)
    left = (w - s) // 2
    top = (h - s) // 2
    img = img.crop((left, top, left + s, top + s))
for name, size in {
    '72x72.png': 72, '96x96.png': 96, '144x144.png': 144, '192x192.png': 192,
    '120x120.png': 120, '180x180.png': 180, '1024x1024.png': 1024,
}.items():
    r = img.resize((size, size), Image.LANCZOS)
    r.save(os.path.join(target, name))
    print(f'  {name} ({size}x{size})')
print('Done! 7 icons generated')
"@ | Out-File -FilePath $tmpFile -Encoding utf8

Write-Host "Generating icons..." -ForegroundColor Cyan
& $python $tmpFile
Remove-Item $tmpFile -Force
Write-Host "Done! Icons saved to unpackage/res/icons/" -ForegroundColor Green
Write-Host "To change icon: replace static/app-icon.png and re-run this script" -ForegroundColor Cyan

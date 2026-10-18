# 手工安装 iso_analyze_finding_GB19001-2016 到 DSH profile
# 用法：powershell -ExecutionPolicy Bypass -File scripts/install.ps1
param(
  [string]$Profile = (Join-Path $env:USERPROFILE ".dsh\profiles\desktop"),
  [switch]$SkipPnpm
)
$ErrorActionPreference = "Stop"

$src = Split-Path -Parent $PSScriptRoot
$pkgName = "iso_analyze_finding_GB19001-2016"
$dst = Join-Path $Profile ("plugins\" + $pkgName)

Write-Host "[1/4] 复制插件到 $dst"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Copy-Item -Recurse $src $dst
Remove-Item -Recurse -Force (Join-Path $dst "node_modules") -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Directory -Filter "__pycache__" $dst | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "[2/4] 写入依赖与组合包列表"
$pkgPath = Join-Path $Profile "package.json"
if (-not (Test-Path $pkgPath)) { throw "找不到 profile 的 package.json：$pkgPath" }
Copy-Item $pkgPath ($pkgPath + ".bak-iso-audit") -Force
$pkg = Get-Content $pkgPath -Raw | ConvertFrom-Json
if (-not $pkg.dependencies) { $pkg | Add-Member -NotePropertyName dependencies -NotePropertyValue ([pscustomobject]@{}) }
$pkg.dependencies | Add-Member -NotePropertyName $pkgName -NotePropertyValue ("link:./plugins/" + $pkgName) -Force
if (-not $pkg.dsh) { $pkg | Add-Member -NotePropertyName dsh -NotePropertyValue ([pscustomobject]@{}) }
if (-not $pkg.dsh.profile) { $pkg.dsh | Add-Member -NotePropertyName profile -NotePropertyValue ([pscustomobject]@{}) }
$bundles = @()
if ($pkg.dsh.profile.bundles) { $bundles = @($pkg.dsh.profile.bundles) }
if ($bundles -notcontains $pkgName) { $bundles += $pkgName }
$pkg.dsh.profile | Add-Member -NotePropertyName bundles -NotePropertyValue $bundles -Force
$pkg | ConvertTo-Json -Depth 20 | Set-Content $pkgPath -Encoding UTF8

Write-Host "[3/4] 安装依赖（pnpm）"
if (-not $SkipPnpm) {
  $node = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
  $pnpm = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs"
  if ((Test-Path $node) -and (Test-Path $pnpm)) {
    Push-Location $Profile
    try { & $node $pnpm install --ignore-scripts } finally { Pop-Location }
  } else {
    Write-Host "  未找到 DSH 自带 node/pnpm，请手动执行 pnpm install"
  }
}

Write-Host "[4/4] 完成"
Write-Host "请重启 DeepSeek Harness 桌面应用后生效。"
Write-Host "自检：在会话中说 用 iso_clause_lookup 查 7.5.3"

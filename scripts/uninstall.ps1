# 卸载 iso_analyze_finding_GB19001-2016
param(
  [string]$Profile = (Join-Path $env:USERPROFILE ".dsh\profiles\desktop"),
  [switch]$SkipPnpm
)
$ErrorActionPreference = "Stop"
$pkgName = "iso_analyze_finding_GB19001-2016"

Write-Host "[1/3] 从组合包列表移除"
$pkgPath = Join-Path $Profile "package.json"
if (Test-Path $pkgPath) {
  $pkg = Get-Content $pkgPath -Raw | ConvertFrom-Json
  if ($pkg.dsh -and $pkg.dsh.profile -and $pkg.dsh.profile.bundles) {
    $kept = @($pkg.dsh.profile.bundles | Where-Object { $_ -ne $pkgName })
    $pkg.dsh.profile | Add-Member -NotePropertyName bundles -NotePropertyValue $kept -Force
  }
  if ($pkg.dependencies -and $pkg.dependencies.PSObject.Properties.Name -contains $pkgName) {
    $pkg.dependencies.PSObject.Properties.Remove($pkgName)
  }
  $pkg | ConvertTo-Json -Depth 20 | Set-Content $pkgPath -Encoding UTF8
  Write-Host "  已移除依赖与 bundles 条目"
}

Write-Host "[2/3] 同步依赖"
if (-not $SkipPnpm) {
  $node = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
  $pnpm = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs"
  if ((Test-Path $node) -and (Test-Path $pnpm)) {
    Push-Location $Profile
    try { & $node $pnpm install --ignore-scripts } finally { Pop-Location }
  }
}

Write-Host "[3/3] 删除插件目录"
$dst = Join-Path $Profile ("plugins\" + $pkgName)
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }

Write-Host "卸载完成。重启应用后 6 个工具不再出现。"

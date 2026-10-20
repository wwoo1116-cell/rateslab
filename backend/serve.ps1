# V2-LOCAL EDIT 3 of 5 — see ../BACKEND.md
#
# sauron-v2's own backend launcher. It binds :8200.
#
# The port was never in the source: v1 passes it on the uvicorn command line
# from `.sauron\start-backend.ps1`, which lives outside the repo and belongs to
# braveworld. So "bind :8200" could not be a one-line source edit — it is this
# file, which is the v2-local equivalent of that launcher.
#
# :8100 IS NEVER BOUND HERE. That port belongs to braveworld, is taken down
# every time its gate runs, and the deployed site is served from it.
#
# ── -Local [2026-08-20, 배포 준비] ─────────────────────────────────────────
# 배포되면 이 포트가 Tailscale Funnel 로 공개된다. 그때부터 "포트가 열려 있다"
# 는 사실만으로는 내가 띄운 개발 백엔드인지 **사람들이 쓰고 있는 라이브
# 서비스**인지 알 수 없다. v1 은 그 구별을 못 해서 라이브에 대고 테스트를
# 돌렸다.
#
#   .\serve.ps1 -Local    개발용. 쪽지(backend/.cache/dev-backend.json)를 남기고,
#                          백엔드 테스트는 그 쪽지가 있어야만 이 포트를 건드린다.
#   .\serve.ps1           공개 서비스용. 쪽지를 안 남긴다 → 테스트가 거절한다.
#
# 쪽지를 쓰는 것은 앱 자신(app/dev_marker.py)이다. 여기서는 선언만 켠다.

param(
  [switch]$Local,
  [int]$Port = 8200
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
# 로그는 포트마다 따로. 8200 은 예약 작업·BACKEND.md·세션 프롬프트가 모두
# `backend.log` 를 가리키므로 그 이름을 지킨다.
#
# [2026-10-20] 한 파일을 함께 쓰면 **둘째 백엔드를 띄울 수 없다**: 라이브 :8200 의
# uvicorn 은 cmd 의 `>>` 로 이 파일을 독점으로 열고 있고, 그 상태에서 아래
# Add-Content 가 IOException 으로 떨어진다. $ErrorActionPreference="Stop" 이라
# 런처가 거기서 죽어서 ─ 포트도 안 열리고 로그도 안 남아 ─ 원인이 안 보였다.
# 눈으로 재려면 :8299 가 :8200 과 동시에 서야 한다(프런트 `.env.development.local`
# 이 :8299 를 가리킨다).
$logName = if ($Port -eq 8200) { "backend.log" } else { "backend-$Port.log" }
$log = Join-Path (Split-Path -Parent $root) $logName
$python = "C:\Users\infomax\Miniconda3\python.exe"

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
  Write-Host ":$Port already serving — nothing to do"
  exit 0
}

# 로그가 영원히 자라지 않게. v1 launcher 와 같은 규칙(5MB 넘으면 새로 시작).
# 예약 태스크로 돌면 이 파일에 몇 달치가 쌓인다.
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 5MB)) { Remove-Item $log -Force }
Add-Content $log "`n===== start $(Get-Date -Format o) port=$Port local=$($Local.IsPresent) ====="

$env:PYTHONUTF8 = "1"
if ($Local) {
  $env:SAURON_DEV_LOCAL = "1"
  Write-Host "-Local: 개발용 쪽지를 남깁니다 (백엔드 테스트가 이 포트를 자기 것으로 인정합니다)"
} else {
  # 상속된 값이 남아 있으면 공개 서비스가 쪽지를 남긴다. 명시적으로 지운다.
  Remove-Item Env:\SAURON_DEV_LOCAL -ErrorAction SilentlyContinue
}
Set-Location $root

# cmd owns the redirection: PS 5.1 wraps native stderr lines into ErrorRecords,
# and the backend's harmless dataset warnings on stderr kill the launcher.
# (Carried over from v1's launcher, which learned this the hard way.)
& cmd.exe /s /c " ""$python"" -m uvicorn app.main:app --port $Port >> ""$log"" 2>&1 "

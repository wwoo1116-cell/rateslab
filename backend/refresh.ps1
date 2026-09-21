# 아침 데이터 갱신 — 백엔드를 **다시 읽게** 만든다.
#
# ── 왜 필요한가 [진단 2026-08-24] ──────────────────────────────────────────
#
# `app/main.py:288` 이 모듈 import 시점에 데이터셋을 한 번 읽고, 그 스냅샷에서
# `_bases`·`_curves`·`_events`·`_volatility`·`_forwards`·`_surface` 를 전부 미리
# 계산해 전역에 붙든다. **다시 읽는 자리가 없다.**
#
# 그래서 백엔드가 뜬 뒤에 `mkt_irs_close` 에 새 날이 들어오면 서버는 그걸 영원히
# 못 본다. 2026-08-24 실측:
#
#     SauronV2Backend  06:57 기동  → SQL 을 그때 읽음 (2,627행 · ~08-20)
#     SauronMorningBake 07:20 실행
#     SQL 실제          2,628행 · ~08-21 · 15/15 칸 다 참
#     화면              하루 종일 08-20                ← 여기
#
# v1 백엔드가 멀쩡해 보였던 것은 우연히 09:17 에 떴기 때문이다. 순서가 뒤바뀌면
# 어느 쪽이든 같은 병에 걸린다.
#
# ── 왜 «그냥 7시에 재기동» 이 아니라 기다리는가 ─────────────────────────────
#
# `mkt_irs_close` 를 채우는 것은 이 PC 가 아니라 외부 적재(miraebond2)이고,
# **적재 지연이 잦다**. 고정 시각에 무조건 재기동하면 늦은 날에는 옛 데이터를
# 다시 읽고 그대로 하루를 보낸다 — 지금과 똑같은 상태가 된다.
#
# 그래서 이 스크립트는 **SQL 이 백엔드보다 새로울 때만** 재기동하고, 아직이면
# 기다렸다 다시 본다. 이미 최신이면 아무것도 안 한다(끊김 0).
#
# ── 태스크 정지로는 안 죽는다 ──────────────────────────────────────────────
#
# `Stop-ScheduledTask` 가 uvicorn 을 안 죽인다. 2026-08-24 에 실측으로 다시
# 확인했다 — 태스크를 멈춘 뒤에도 PID 15888 이 :8200 을 쥐고 있었고, 그대로
# 다시 시작했으면 `serve.ps1` 이 "already serving — nothing to do" 로 조용히
# 끝나서 **아무것도 안 바뀌었을** 것이다. 리스너를 직접 잡는다.

param(
  [int]$Port = 8200,
  [string]$TaskName = "SauronV2Backend",
  # 적재를 기다리는 총 시간. 5분마다 다시 본다.
  [int]$WaitMinutes = 60
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path (Split-Path -Parent $root) "refresh.log"
$python = "C:\Users\infomax\Miniconda3\python.exe"

function Say($msg) {
  $line = "$(Get-Date -Format o)  $msg"
  Write-Host $line
  Add-Content $log $line -Encoding utf8
}

if ((Test-Path $log) -and ((Get-Item $log).Length -gt 5MB)) { Remove-Item $log -Force }
Say "===== refresh start port=$Port ====="

# SQL 이 들고 있는 마지막 날. 로더를 그대로 쓴다 — 여기서 쿼리를 다시 쓰면
# 서버가 읽는 것과 다른 것을 볼 수 있다.
function Get-SqlAsof {
  $env:PYTHONUTF8 = "1"
  Push-Location $root
  try {
    $out = & $python -c "import sys; sys.path.insert(0,'.'); from app.mysqldb import irs_close_rows; r=irs_close_rows(); print(r[-1]['irs_date'] if r else '')" 2>$null
    return ($out | Select-Object -Last 1).Trim()
  } catch { return "" } finally { Pop-Location }
}

# 지금 서비스 중인 백엔드가 보는 날. 못 읽으면 빈 문자열 — 그건 «안 떠 있다» 다.
function Get-ServedAsof {
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 8
    return [string]$r.asof
  } catch { return "" }
}

# ── 계획면을 미리 굽는다 [2026-09-21] ──────────────────────────────────────
#
# `/api/mr/plan` 은 계열 스물다섯을 **배경에서** 굽는다(실측 40초). 빌더를 깨우는
# 것은 첫 요청이라, 안 찔러 두면 아침 첫 사람이 「채점 중 3/25」를 본다. 여기서
# 한 번 부르면 트레이더가 화면을 열 때는 다 서 있다.
#
# 기동 시점에 안 굽는 이유는 시험이다 — 백엔드 시험이 `TestClient(app)` 로
# lifespan 을 타므로 거기서 빌더가 뜨면 시험마다 몇 분이 붙는다(`app/mrplan.py` 머리).
#
# 실패해도 재기동 결과를 안 바꾼다 — 화면이 스스로 다시 묻는다.
function Invoke-PlanWarm {
  try {
    $p = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/mr/plan" -TimeoutSec 30
    Say "계획면을 깨웠어요 — done=$($p.done)/$($p.total) building=$($p.building)"
  } catch {
    Say "계획면 워밍은 실패했어요(무시): $($_.Exception.Message)"
  }
}

$deadline = (Get-Date).AddMinutes($WaitMinutes)
$sqlAsof = ""
$served = ""

while ($true) {
  $sqlAsof = Get-SqlAsof
  $served = Get-ServedAsof
  Say "SQL=$sqlAsof  served=$served"

  if ($sqlAsof -eq "") {
    Say "SQL 을 못 읽었어요 — 자격증명(BW_MYSQL_*)이나 DB 를 보세요. 재기동 안 함."
    exit 1
  }
  # 백엔드가 안 떠 있으면 기다릴 것 없이 띄운다.
  if ($served -eq "") { Say "백엔드가 안 떠 있어요 — 띄웁니다."; break }
  # 이미 최신이면 건드리지 않는다. 끊김 0 이 기본값이다.
  if ($served -ge $sqlAsof) { Say "이미 최신이에요 — 아무것도 안 합니다."; Invoke-PlanWarm; exit 0 }
  # SQL 이 더 새로우면 재기동한다.
  if ($sqlAsof -gt $served) { Say "SQL 이 더 새로워요 — 재기동합니다."; break }

  if ((Get-Date) -ge $deadline) {
    Say "$WaitMinutes 분을 기다렸는데 SQL 이 안 새로워졌어요 — 재기동 안 함."
    exit 2
  }
  Start-Sleep -Seconds 300
}

# ── 재기동 ─────────────────────────────────────────────────────────────────
try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch {}
Start-Sleep -Seconds 2

# **여기가 핵심이다.** 태스크를 멈춰도 uvicorn 이 포트를 쥐고 있으면 `serve.ps1`
# 이 "already serving" 으로 끝나 아무것도 안 바뀐다.
$pids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
if ($pids) {
  Say ("리스너를 직접 종료합니다: " + ($pids -join ','))
  $pids | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} }
}
Start-Sleep -Seconds 2

Start-ScheduledTask -TaskName $TaskName
Say "재기동 요청을 보냈어요."

# ── 확인 ───────────────────────────────────────────────────────────────────
# 「보냈다」 는 「됐다」 가 아니다. 실제로 새 날짜를 서빙하는지 본다.
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 4
  $now = Get-ServedAsof
  if ($now -ne "") {
    if ($now -ge $sqlAsof) { Say "확인: asof=$now — 갱신됐어요."; Invoke-PlanWarm; exit 0 }
    Say "떴는데 아직 asof=$now (기대 $sqlAsof) — 더 봅니다."
  }
}
Say "2분 안에 기대한 날짜로 안 왔어요 — backend.log 를 보세요."
exit 3

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
# ── 왜 «그냥 7시에 재기동» 이 아니라 조건부인가 ─────────────────────────────
#
# `mkt_irs_close` 를 채우는 것은 이 PC 가 아니라 외부 적재(miraebond2)이고,
# **적재 지연이 잦다**. 고정 시각에 무조건 재기동하면 늦은 날에는 옛 데이터를
# 다시 읽고 그대로 하루를 보낸다 — 지금과 똑같은 상태가 된다.
#
# 그래서 이 스크립트는 **재기동해야 날짜가 앞설 때만** 재기동한다. 아니면 아무것도
# 안 한다(끊김 0).
#
# ── 기다리는 자리는 이 스크립트가 아니다 [2026-09-22] ───────────────────────
#
# 옛 판은 `-WaitMinutes 60` 으로 «기다렸다 다시 본다» 고 적고 있었다. **그 루프는
# 한 번도 돈 적이 없다.** 판정 두 줄(`served -ge $sql` / `$sql -gt $served`)이
# ISO 날짜 문자열에 대해 완전하고 서로 배타적이라, 어느 쪽이든 첫 바퀴에서
# exit 하거나 break 했다 — `Start-Sleep 300` 은 **도달 불가능한 코드**였다.
#
# 그리고 진짜 병은 대기 시간이 아니라 **판정의 어휘**였다. 아침 순서는 이렇다:
#
#     07:37  PC 부팅 → SauronV2Backend 가 그때의 SQL 을 읽는다
#     07:42  이 스크립트 → SQL 과 서버가 «같다» → 「이미 최신이에요」
#     그 뒤   전영업일 종가가 SQL 에 도착 → 아무도 다시 안 본다
#
# 둘이 같은 것은 참이었다. 거짓이었던 것은 그 상태를 «최신» 이라 부른 것이다 —
# SQL 자신이 기대 전영업일을 안 들고 있었다. refresh.log 에 그 한 줄이 **2026-09-10
# 부터 09-22 까지 열 번의 아침** 연속으로 찍혀 있다. 그동안 Main·Backtest 는 늘
# 한 영업일 늦은 화면이었다(Strategy 쪽은 SQL 을 라이브로 읽어 멀쩡했다 — 그래서
# 증상이 화면마다 달랐고 진단이 늦었다).
#
# 고친 방향은 「더 오래 기다리기」가 아니라 **「다시 보기」**다:
#   · 판정은 `scripts/check_close.py` 로 옮겼다(파이썬엔 시험이 있다).
#     다섯 상태 중 «waiting» 이 새로 생긴 것이 수리의 전부다.
#   · 기다림은 **스케줄러의 반복 트리거**가 한다(`refresh_schedule.ps1`,
#     기본 30분 간격). 이 스크립트는 한 번 보고 끝나는 단발이다 —
#     그래야 `MultipleInstances=IgnoreNew` 와 `ExecutionTimeLimit=PT2H` 아래서
#     오래 도는 인스턴스가 다음 회차를 막지 않는다.
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
  # 판정까지만 하고 리스너를 안 죽인다. 이 스크립트를 고친 뒤 **재기동 경로를
  # 프로덕션에 물리기 전에** 한 번 지나 보는 자리다 — 판정이 맞아도 배관이
  # 틀릴 수 있고, 그 배관은 데스크가 보는 백엔드를 죽인다.
  [switch]$DryRun
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

# 판정 한 번. **비교하는 두 수를 같은 계산에서 뽑는다** — `wouldServe` 는 서버가
# 부팅 때 지나는 그 로더(`load_dataset_merged`)의 asof 다. 옛 판이 쓴
# `irs_close_rows()[-1]` 은 테이블의 raw MAX 라서 전일종가 컷·엑셀 병합을 안 지난다.
# 30분마다 다시 보는 지금은 그 오독의 대가가 헛재기동 한 번이 아니라 **종일
# 재기동**이다(테이블에 오늘 자 행이 한 번 들어오면 「SQL 이 더 새롭다」가 영구히
# 참이 된다).
#
# 판정 문장(`why`)도 파이썬이 만든다 — 한 사실에 두 어휘가 생기는 것이 이 리포의
# 고질병이다. 여기서는 그대로 로그에 옮긴다.
function Get-Verdict($served) {
  $env:PYTHONUTF8 = "1"
  # ⚠ Windows PowerShell 5.1 함정 — 이 한 줄이 없으면 **항상** null 이 돈다.
  # 로더는 stderr 에 경고를 쓴다(`[dataset] last observation ... is 34 days old`).
  # 5.1 은 네이티브 exe 의 stderr 를 리다이렉트하면 각 줄을 ErrorRecord 로 싸는데,
  # 스크립트 머리의 `$ErrorActionPreference = "Stop"` 이 그걸 **종료 오류**로
  # 올려서 아래 catch 가 먹는다. 실측으로 밟았다(2026-09-22): 파이썬은 JSON 을
  # 정상 출력했는데 스크립트는 「판정을 못 구했어요」로 exit 1 했다.
  # 옛 `Get-SqlAsof` 가 안 밟은 이유는 `python -c` 가 stderr 를 안 썼기 때문이다.
  $ErrorActionPreference = "Continue"
  # ⚠ 세 번째 함정 — 이 두 줄이 없으면 **로그의 한글이 깨진다**. PS 5.1 은 네이티브
  # 프로세스의 stdout 을 `[Console]::OutputEncoding`(기본 cp949)으로 디코드한다.
  # 태스크는 `conhost --headless` 밑에서 도니 내 대화형 셸과 다르고, 그래서 손으로
  # 돌릴 때는 멀쩡하고 **스케줄러가 돌릴 때만** 깨진다(실측 2026-09-22 08:30 회차:
  # `湲곕? ?꾩쁺?낆씪源뚯? …`). JSON 키·날짜는 ASCII 라 판정은 맞았고 사람이 읽는
  # 문장만 깨졌다 — 판정을 ASCII 필드에 둔 설계가 그걸 버텼다.
  $prevEnc = [Console]::OutputEncoding
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  Push-Location $root
  try {
    # ⚠ `--served=$served` 이고 `--served "$served"` 가 아니다 — 두 번째 함정이다.
    # 백엔드가 안 떠 있으면 `$served` 가 빈 문자열이고, PS 5.1 은 네이티브 exe 에
    # 넘기는 **빈 인자를 그냥 떨어뜨린다**. 그러면 argparse 가 값 없는 `--served` 를
    # 보고 usage 로 죽어서 판정이 영영 null 이 된다(실측 2026-09-22 — 「백엔드가
    # 안 떠 있다」가 하필 그 경로였다). `=` 꼴은 한 토큰이라 안 떨어진다.
    $out = & $python "scripts\check_close.py" --json "--served=$served" 2>$null
    # 로더가 stdout 에 경고를 섞는다(`[dataset] ...`). JSON 줄만 집는다.
    $line = ($out | Where-Object { $_ -match '^\s*\{' } | Select-Object -Last 1)
    if (-not $line) { return $null }
    return ($line | ConvertFrom-Json)
  } catch { return $null } finally {
    Pop-Location
    [Console]::OutputEncoding = $prevEnc
  }
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

# ── 판정 ───────────────────────────────────────────────────────────────────
#
# 단발이다. 루프가 없는 것이 수리다(머리의 「기다리는 자리」 참조) — 다시 보는
# 것은 스케줄러가 한다.
$served = Get-ServedAsof
$r = Get-Verdict $served
if ($null -eq $r) {
  Say "판정을 못 구했어요(check_close.py) — 파이썬·자격증명(BW_MYSQL_*)을 보세요. 재기동 안 함."
  exit 1
}

$serveAsof = [string]$r.wouldServe.asof
$expected = if ($r.expected) { [string]$r.expected } else { "(영업일 아님)" }
$sqlStatus = if ($r.sql) { [string]$r.sql.status } else { "-" }
Say "served=$served  wouldServe=$serveAsof  expected=$expected  sql=$sqlStatus  -> $($r.verdict)"
Say $r.why

switch ($r.verdict) {
  "error"   { exit 1 }
  # 기다림은 실패가 아니다. 종료 코드를 따로 두는 것은 스케줄러 이력에서
  # 「아직 안 왔다」와 「할 일 없다」를 가르기 위해서다.
  "waiting" { Invoke-PlanWarm; exit 2 }
  "current" { Invoke-PlanWarm; exit 0 }
  "start"   { }   # 아래 재기동으로
  "restart" { }   # 아래 재기동으로
  # 모르는 판정은 **재기동이 아니라 정지**다. 기본값이 「흘러내려 재기동」이면
  # 판정이 비거나 낱말이 바뀐 날에 데스크의 백엔드가 죽는다.
  default   {
    Say "모르는 판정입니다: '$($r.verdict)' — 재기동 안 함. check_close.py 를 보세요."
    exit 1
  }
}

# ── 재기동 ─────────────────────────────────────────────────────────────────
if ($DryRun) {
  $pidsWouldDie = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
                  Select-Object -ExpandProperty OwningProcess -Unique
  # ⚠ 두 줄이 필요한 이유. `$x = if (...) {...} else {...}` (대입)은 5.1 에서
  # **되고**, 위 `$expected`·`$sqlStatus` 가 그 꼴이다. 안 되는 것은 식 **안**의
  # if — `("..." + (if (...) {...}))` 처럼 다른 식의 피연산자로 쓰는 경우다.
  # 게다가 `Parser::ParseFile` 은 그걸 **명령 이름 `if`** 로 읽어 «parse OK» 를
  # 내므로, 파스 검사가 초록이어도 런타임에 CommandNotFound 로 죽는다
  # (실측 2026-09-22 — 이 자리에서 한 번 밟았다).
  $who = "(없음)"
  if ($pidsWouldDie) { $who = $pidsWouldDie -join ',' }
  Say "DryRun — 여기서 멈춥니다. 실제로는 $TaskName 을 다시 띄우고 리스너를 죽입니다: $who"
  exit 0
}

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
    if ($now -ge $serveAsof) { Say "확인: asof=$now — 갱신됐어요."; Invoke-PlanWarm; exit 0 }
    Say "떴는데 아직 asof=$now (기대 $serveAsof) — 더 봅니다."
  }
}
Say "2분 안에 기대한 날짜로 안 왔어요 — backend.log 를 보세요."
exit 3

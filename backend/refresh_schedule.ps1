# 아침 갱신을 **하루 한 번 보기**에서 **하루 종일 다시 보기**로 [2026-09-22].
#
#     powershell -File backend/refresh_schedule.ps1                  # 지금 상태만 본다
#     powershell -File backend/refresh_schedule.ps1 -Apply           # 반복을 건다
#     powershell -File backend/refresh_schedule.ps1 -Revert -Apply   # 되돌린다
#
# ── 왜 트리거를 고치는가 ────────────────────────────────────────────────────
#
# `refresh.ps1` 은 단발이다. 「적재를 기다린다」를 스크립트 안의 `Start-Sleep`
# 으로 하면 `MultipleInstances=IgnoreNew` 아래서 오래 도는 인스턴스가 다음 회차를
# 막고, `ExecutionTimeLimit=PT2H` 가 그걸 도중에 죽인다. 기다림은 스케줄러가
# 하는 일이다.
#
# 고치기 전 실측(2026-09-22):
#   트리거  = 매일 07:00, 반복 없음
#   그 결과 = 아침 한 번 보고 끝. 전영업일 종가는 그 뒤에 도착한다.
#             refresh.log 에 「이미 최신이에요」가 09-10 부터 09-22 까지 열 줄.
#
# ── 이 변경이 하는 일과 그 대가 ─────────────────────────────────────────────
#
# 적재가 도착한 **그 회차에** 백엔드가 한 번 재기동된다. 대가는 그 순간의
# 짧은 끊김과 그 뒤 캐시가 다시 구워지는 동안의 느린 첫 요청들(계획면 25계열
# 40~66초 — refresh.ps1 이 재기동 확인 뒤 스스로 찔러 둔다). 그 대가를 하루
# 한 번 치르고, 대신 화면이 전영업일 종가를 든다.
#
# ── 태스크 이력에서 읽는 법 ─────────────────────────────────────────────────
#
# `LastTaskResult` 가 하루의 대부분 **2** 로 보이는 것이 정상이다 —
# 2 = 「SQL 이 아직 기대 전영업일을 안 들고 있다」. 0 = 할 일 없었다 또는 갱신 성공.
# 1 = 판정 자체를 못 구했다(파이썬·자격증명). 3 = 재기동했는데 날짜가 안 왔다.
#
# ── ⚠ 이 파일은 **BOM 이 있는 UTF-8** 이어야 한다 ───────────────────────────
#
# Windows PowerShell 5.1 은 BOM 없는 .ps1 을 ANSI(여기서는 cp949)로 읽는다.
# 이 파일을 처음 BOM 없이 저장했을 때 한글 문자열의 인용이 깨져 **`-Apply` 가드
# 블록이 통째로 무력화됐다** — 가드 본문이 코드가 아니라 텍스트로 출력되고
# 실행이 아래로 흘렀다. 태스크가 실제로 안 바뀐 것은 운이었다.
# 그래서 아래 구조도 같이 바꿨다: 바꾸는 코드를 `if ($Apply)` **안쪽**에 둔다.
# 가드가 깨지면 변경도 같이 죽는다 — 가드 뒤에 두면 가드만 죽는다.
# 리포의 다른 .ps1 둘(refresh.ps1 · serve.ps1)도 BOM 이 있다.

param(
  [string]$TaskName = "SauronV2Refresh",
  [string]$At = "07:00",
  [int]$EveryMinutes = 30,
  [int]$ForHours = 12,
  # 반복을 떼고 하루 한 번으로 되돌린다.
  [switch]$Revert,
  # 안 주면 **아무것도 안 바꾸고** 지금 상태만 찍는다. 이 스크립트는 데스크가
  # 보는 백엔드의 재기동 정책을 바꾸므로 기본값이 «보기» 다.
  [switch]$Apply
)

$ErrorActionPreference = "Stop"

function Show-Triggers($label) {
  $t = Get-ScheduledTask -TaskName $TaskName
  Write-Host "--- $label ---"
  foreach ($g in $t.Triggers) {
    $rep = "(반복 없음)"
    if ($g.Repetition -and $g.Repetition.Interval) {
      $rep = "반복 $($g.Repetition.Interval) / $($g.Repetition.Duration)"
    }
    Write-Host ("  " + $g.CimClass.CimClassName + "  start=" + $g.StartBoundary + "  " + $rep)
  }
  $i = $t | Get-ScheduledTaskInfo
  Write-Host ("  last=" + $i.LastRunTime + "  result=" + $i.LastTaskResult + "  next=" + $i.NextRunTime)
}

Show-Triggers "지금"

if ($Apply) {
  $daily = New-ScheduledTaskTrigger -Daily -At $At

  if (-not $Revert) {
    # ⚠ `New-ScheduledTaskTrigger -Daily` 는 `-RepetitionInterval` 을 안 받는다.
    # 받는 것은 `-Once` 뿐이라, Once 트리거를 하나 만들어 **Repetition 만** 옮긴다.
    # 아래 Show-Triggers 가 실제로 붙었는지 확인한다 — 「보냈다」는 「됐다」가 아니다.
    $tmp = New-ScheduledTaskTrigger -Once -At $At `
             -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) `
             -RepetitionDuration (New-TimeSpan -Hours $ForHours)
    $daily.Repetition = $tmp.Repetition
  }

  Set-ScheduledTask -TaskName $TaskName -Trigger $daily | Out-Null

  Show-Triggers "바꾼 뒤"
  Write-Host ""
  if ($Revert) {
    Write-Host "되돌렸습니다 — 하루 한 번 $At."
  } else {
    Write-Host "걸었습니다 — $At 부터 $EveryMinutes 분마다 $ForHours 시간."
    Write-Host "되돌리려면: powershell -File backend/refresh_schedule.ps1 -Revert -Apply"
  }
} else {
  Write-Host ""
  Write-Host "보기만 했습니다. 바꾸려면 -Apply 를 주세요."
}

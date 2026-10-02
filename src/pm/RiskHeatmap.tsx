'use client';

/* Risk Management — 거래 간 손익 상관 히트맵 [OWNER 2026-10-02] ────────────────
 *
 * > [OWNER] 「거래별 Correlation 계산해주는거 가능?」 …
 * >         「그냥 포트폴리오 탭에 Risk Management 로 해서 Heatmap 으로」
 *
 * ── ★이 화면이 답하는 질문: **내 거래들이 사실 같은 베팅인가** ────────────────
 * 실측(2026-10-02 산 장부)이 그 값을 보여 준다: 1st Trade = IRS 5Y receive +
 * 10Y pay(5s10s 스티프너), 2nd Trader = IRS 2Y receive + 10Y pay(2s10s 스티프너).
 * **둘 다 10Y pay 를 공유하는 커브 스티프너**라 ρ = +0.67 이 나온다. 분산이 아니라
 * 집중이고, 테너 사다리가 그걸 그대로 말한다(10Y 에 순 DV01 +2,000만/bp 가 몰림).
 *
 * ── 수는 **서버가 센다**(§16) ──────────────────────────────────────────────
 * 상관도 창도 n 도 `/api/paper/risk` 가 낸다. 화면은 칠하고 적기만 한다 — 「무엇의
 * 상관인가」라는 말(`basis`)까지 서버 것을 옮긴다. 두 층이 각자 「상관」을 정의하면
 * 같은 북에 두 수가 선다.
 *
 * ── 색 규율 ────────────────────────────────────────────────────────────────
 * 상관은 **0 을 가운데 둔 발산 축**이다 — 캐논의 `tintFor`(두 색조 `--sr-up` /
 * `--sr-down` + 중성 0 = 카드 면)를 그대로 쓴다. 그 파일이 이미 농도의 상·하한을
 * 대비 실측으로 묶어 두었다(다크 55% 에서 5.7:1). 스케일은 **1** 이다 — |ρ| ≤ 1 이
 * 자연 상한이라 표마다 기준이 달라지지 않는다(표 안에서 최댓값으로 정규화하면
 * 「+0.2 뿐인 북」이 「+0.9 인 북」과 같은 진하기로 보인다).
 *
 * ★**색만으로 말하지 않는다** — 칸마다 수를 찍는다. 틴트 위 글자는 **잉크**다
 * (`tint.ts` 의 그 규율: 같은 색조로 칠하면 글자가 배경에 먹힌다 — 실측으로
 * 어떤 농도에서도 4.5:1 을 못 넘었다).
 */

import { useCallback, useEffect, useState } from 'react';

import { Box, HStack, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';

import { BacktestUnavailable } from '@/lib/api';
import { tintFor } from '@/theme/tint';

import { fetchRisk, type PaperRisk, type RiskWindow } from './api';

const WINDOWS: { id: RiskWindow; label: string }[] = [
  { id: '3m', label: '3개월' },
  { id: '6m', label: '6개월' },
  { id: '1y', label: '1년' },
];

/** 상관 표기 — 소수 둘. `null` 은 «—» 다(0 이 아니라 **못 쟀다**). */
function rho(v: number | null): string {
  return v == null ? '—' : v.toFixed(2);
}

export function RiskHeatmap() {
  const [win, setWin] = useState<RiskWindow>('1y');
  const [got, setGot] = useState<PaperRisk | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback((w: RiskWindow, signal?: AbortSignal) => {
    setBusy(true);
    setErr(null);
    fetchRisk(w, signal)
      .then((r) => {
        setGot(r);
        setErr(null);
      })
      .catch((e: unknown) => {
        if (signal?.aborted) return;
        setErr(e instanceof BacktestUnavailable
          ? '실행 중인 백엔드가 필요해요 — 엔진을 창만큼 다시 돌려야 해서 구워 둘 수 없어요.'
          : e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!signal?.aborted) setBusy(false);
      });
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    load(win, ac.signal);
    return () => ac.abort();
  }, [load, win]);

  const trades = got?.trades ?? [];
  /* 「믿을 만한가」를 머리에서 말한다 — 표본이 문턱 아래면 칸이 전부 «—» 가 되므로
     왜 비었는지를 수로 적어 둬야 한다(이 리포의 공란 정책). */
  const thin = got != null && got.n < got.minN;

  return (
    <VStack className="sr-card" flexShrink={0} width="100%">
      <HStack alignItems="baseline" justifyContent="space-between" gap={1}
        paddingX={2} paddingTop={1.5} paddingBottom={0.5} flexWrap="wrap">
        <HStack alignItems="baseline" gap={1} flexWrap="wrap">
          <Text font="label1" as="h2" noWrap>Risk Management — 거래 간 상관</Text>
          <Text font="legal" as="span" color="fgMuted">
            {got
              ? `${got.basis} · n=${got.n}${got.to ? ` · ${got.since} ~ ${got.to}` : ''}`
              : busy ? '재는 중…' : ''}
          </Text>
        </HStack>
        <HStack gap={0.5} alignItems="center">
          {WINDOWS.map((w) => (
            <button
              key={w.id}
              type="button"
              className="sr-pillbtn"
              data-on={win === w.id || undefined}
              aria-pressed={win === w.id}
              onClick={() => setWin(w.id)}
            >
              {w.label}
            </button>
          ))}
        </HStack>
      </HStack>

      {err ? (
        <Box paddingX={2} paddingBottom={2}>
          <Text font="body" as="p" color="fgMuted">{err}</Text>
        </Box>
      ) : trades.length < 2 ? (
        <Box paddingX={2} paddingBottom={2}>
          <Text font="body" as="p" color="fgMuted">
            {busy
              ? '재는 중이에요…'
              : '상관은 거래가 둘 이상이어야 말할 수 있어요 — 지금은 '
                + `${trades.length}개예요.`}
          </Text>
        </Box>
      ) : (
        <>
          <Box paddingX={2}>
            {/* 손 표 — 이 앱의 격자 문법(`.sr-rv-table`)이다. CDS `Table` 은 셀당
                32px 이라 N×N 격자에서 한 화면을 못 쓴다(RankingTable 머리의 사유). */}
            <table className="sr-rv-table sr-corr">
              <thead>
                <tr>
                  <th className="sr-rv-th sr-rv-left">거래</th>
                  {trades.map((t) => (
                    <th key={t.key} className="sr-rv-th">{t.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map((row, i) => (
                  <tr key={row.key}>
                    <td className="sr-rv-td sr-rv-left">
                      <div className="sr-name-stack">
                        <Text font="label1" as="span" noWrap>{row.label}</Text>
                        <Text font="legal" as="span" color="fgMuted" noWrap>
                          {`다리 ${row.legs.join('·')}`}
                        </Text>
                      </div>
                    </td>
                    {trades.map((col, j) => {
                      const v = got?.matrix?.[i]?.[j] ?? null;
                      /* 대각선은 **안 칠한다** — 자기 자신과의 상관 1 은 사실이
                         아니라 항등식이고, 칠하면 제일 진한 칸 둘이 아무 뜻 없이
                         눈을 먼저 끈다. */
                      const self = i === j;
                      return (
                        <td
                          key={col.key}
                          className="sr-rv-td"
                          style={self ? undefined : { background: tintFor(v ?? 0, 1) }}
                          title={self
                            ? `${row.label} — 자기 자신`
                            : `${row.label} ↔ ${col.label} · ρ ${rho(v)}`
                              + (got ? ` · n=${got.n} · ${got.basis}` : '')}
                        >
                          <Text font="body" as="span" color={self ? 'fgMuted' : undefined}
                            tabularNumbers noWrap>
                            {self ? '1.00' : rho(v)}
                          </Text>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </Box>
          <VStack gap={0.5} paddingX={2} paddingTop={1} paddingBottom={2}>
            {thin ? (
              <Text font="legal" as="p" color="fgMuted">
                {`공통 영업일이 ${got?.n}일뿐이라 상관을 안 매겼어요 — ${got?.minN}일은 있어야 해요.`}
                {' '}표본이 적은 상관은 점추정이 그럴듯해도 구간이 거의 전구간이에요.
              </Text>
            ) : null}
            <Text font="legal" as="p" color="fgMuted" maxWidth={860}>
              + 면 같이 움직이는 거래예요 — 분산이 아니라 같은 베팅을 두 번 들고 있는
              거예요. 창을 바꿔도 수가 안 변하면 그건 우연이 아니라 구조고, 다리를 보면
              왜인지 보여요(같은 테너를 공유하면 높게 나와요).
            </Text>
            {(got?.excluded ?? []).length > 0 ? (
              <VStack gap={0.25}>
                {(got?.excluded ?? []).map((e) => (
                  <Text key={e.key} font="legal" as="span" color="fgMuted">
                    {`${e.label} — ${e.why}`}
                  </Text>
                ))}
              </VStack>
            ) : null}
          </VStack>
        </>
      )}
    </VStack>
  );
}

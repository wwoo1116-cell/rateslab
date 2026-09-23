import { expect, test, type Page } from '@playwright/test';

/**
 * 폭·간격의 **픽셀 가드** — T1~T5 [OWNER 2026-09-23 · Phase C].
 *
 * ── 왜 vitest 가 아니라 여기인가 ────────────────────────────────────────────
 *
 * 이 리포의 가드는 거의 다 **소스 텍스트·DOM 구조**를 읽는다. 그 선택에는 근거가
 * 있었다 — jsdom 은 CDS 스타일시트를 안 싣고 레이아웃도 안 한다(`ch-context` 와
 * `control-value-font` 가 같은 판단을 적어 뒀다). 다만 그 대가가 있었다:
 *
 *   **T1(죽은 폭)·T3(안쪽 여백)·T4(단독 줄바꿈)은 아무도 안 재고 있었다.**
 *
 * 그래서 「✕ 가 혼자 다음 줄에 선다」가 2026-08 부터 2026-09-23 까지 살아 있었다.
 * 눈으로 본 사람은 있었고(오너가 신고했다) 재는 것이 없었을 뿐이다.
 *
 * ── ★재는 방법은 **페이지 안에서 한 번에** ────────────────────────────────
 *
 * 첫 판은 Playwright locator 로 칸을 하나씩 집으려 했고 다섯 검정이 타임아웃으로
 * 죽었다 — CDS 의 생성 클래스(`width-ws51euf`)와 중첩 때문에 «그 칸» 을 밖에서
 * 집는 규칙이 안 선다. 브라우저 콘솔에서 되던 방식을 그대로 옮긴다: **행을 찾고
 * 칸을 재는 일을 전부 `evaluate` 안에서** 하고, 밖으로는 판정에 필요한 수만
 * 나온다. 덤으로 빠르다(왕복이 한 번이다).
 *
 * ── 재는 것 다섯 ────────────────────────────────────────────────────────────
 *
 *   T1  죽은 폭 ≤ 16px   — **가장 넓은 «가능한» 내용**에서. 지금 값이 아니다.
 *   T2  칸↔칸 ≥ 12 · 라벨→컨트롤 ≥ 4
 *   T3  컨테이너 안쪽 여백보다 가까운 내용이 없다
 *   T4  **혼자 접히는 요소가 없다** — 접힘은 묶음 단위다
 *   T5  한 행에서 같은 관계는 같은 틈 — **글자 틈**으로 잰다(눈이 보는 것)
 *
 * ⚠ 기준은 **미리 선언한 값**이고 데이터를 보고 느슨하게 고치지 않는다.
 */

/** 창이 고정폭(`min(1020px,100vw)`)이라 1024 와 1440 은 같은 regime 이다 —
 *  그래도 둘 다 돈다. 「같다」는 것도 검정이 말해야 하는 사실이다. */
const VIEWPORTS = [
  { name: '1024', width: 1024, height: 900 },
  { name: '1440', width: 1440, height: 900 },
];

/** 기준(px). 미리 선언하고 안 움직인다. */
const T1_DEAD_MAX = 16;
const T2_FIELD_MIN = 12;
const T2_LABEL_MIN = 4;
const T2_CAPTION_MIN = 8;

/** 입력의 편집 여유 — `src/ui/fit.tsx::EDIT_CH` 와 같은 수(두 글자). */
const EDIT_CH = 2;

type RowReport = {
  found: boolean;
  /** 칸 이름 → 죽은 폭(px). 최장 내용을 모르는 칸은 빠진다. */
  dead: Record<string, number>;
  /** 칸↔칸 상자 틈(px), 양수만. */
  fieldGaps: number[];
  /** 라벨 바닥 → 컨트롤 윗변(px). */
  labelGap: number | null;
  /** 바닥이 같은 것끼리 묶은 줄. 이 리포의 행은 **바닥 정렬**이라 top 으로
   *  세면 라벨 있는 칸과 없는 칸이 다른 줄로 잡혀 거짓 실패가 난다. */
  lines: string[][];
  /** 컨테이너 안쪽 여백과 행의 좌·우 여유. */
  pad: number | null;
  edgeLeft: number | null;
  edgeRight: number | null;
};

/**
 * 한 행을 통째로 잰다 — 앵커 라벨로 행을 찾고, 자식 칸마다 죽은 폭과 틈을 낸다.
 *
 * `longest` 는 칸 이름 → **그 칸이 가질 수 있는 가장 넓은 값**이다. 지금 값으로
 * 재면 값이 바뀔 때마다 통과/실패가 뒤집혀 가드가 거짓말을 한다.
 */
async function measureRow(
  page: Page,
  anchor: string,
  longest: Record<string, string>,
  minChildren: number,
): Promise<RowReport> {
  return page.evaluate(
    ({ anchor: a, longest: L, minChildren: m, editCh }) => {
      const empty: RowReport = {
        found: false, dead: {}, fieldGaps: [], labelGap: null,
        lines: [], pad: null, edgeLeft: null, edgeRight: null,
      };
      const leaf = Array.from(document.querySelectorAll('*')).find(
        (e) => e.children.length === 0 && e.textContent?.trim() === a,
      ) as HTMLElement | undefined;
      if (!leaf) return empty;
      /* ★행은 «`flexWrap: wrap` 을 가진 flex row» 다. 자식 수로 찾으면 안 된다 —
         백테스트 북은 2026-09-23 부터 **묶음으로 중첩**돼 있어(무엇을 / 얼마나·
         언제 / 그래서 얼마·지우기) 안쪽 묶음의 자식이 셋뿐이다. 접히는 단위를
         바꾼 그 수리가 곧 이 가드가 행을 못 찾던 이유였다. */
      let row: HTMLElement | null = leaf;
      while (
        row &&
        !(
          getComputedStyle(row).display === 'flex' &&
          getComputedStyle(row).flexWrap === 'wrap' &&
          row.children.length >= 2
        )
      ) {
        row = row.parentElement;
      }
      if (!row) return empty;

      const cv = document.createElement('canvas').getContext('2d');
      /* 한 겹 편다 — 묶음은 칸이 아니라 «칸들의 자루» 다. 자루째 재면 죽은 폭도
         틈도 뜻이 없어지고, 줄바꿈 판정은 자루 하나를 한 요소로 세어 **단독
         줄바꿈을 못 본다**(바로 그 결함을 잡으려고 만든 가드다). */
      const kids = (Array.from(row.children) as HTMLElement[]).flatMap((c) => {
        const cs2 = getComputedStyle(c);
        const nested =
          cs2.display === 'flex' && cs2.flexDirection === 'row' && c.children.length >= 2;
        return nested ? (Array.from(c.children) as HTMLElement[]) : [c];
      });
      if (kids.length < m) return empty;
      const nameOf = (el: HTMLElement) =>
        (el.innerText || '').split('\n')[0].trim() || '✕';

      const dead: Record<string, number> = {};
      let labelGap: number | null = null;
      for (const box of kids) {
        const name = nameOf(box);
        const want = L[name];
        if (!want || !cv) continue;
        let ctl: HTMLElement | null = null;
        for (const n of Array.from(box.querySelectorAll<HTMLElement>('*'))) {
          if (parseFloat(getComputedStyle(n).borderTopWidth) > 0) { ctl = n; break; }
        }
        if (!ctl) continue;
        const cr = ctl.getBoundingClientRect();
        const cs = getComputedStyle(ctl);
        const input = box.querySelector('input');
        if (input) {
          const is = getComputedStyle(input);
          cv.font = is.font;
          /* 크롬은 **실제로** 잰다 — 상수와 어긋나면 그 자체가 결함이다. */
          const chrome =
            cr.width - input.clientWidth +
            parseFloat(is.paddingLeft) + parseFloat(is.paddingRight);
          dead[name] = cr.width - chrome - editCh * cv.measureText('0').width
            - cv.measureText(want).width;
          if (labelGap === null) {
            const lab = Array.from(box.querySelectorAll<HTMLElement>('*')).find(
              (e) => e.children.length === 0 && e.textContent?.trim() === name,
            );
            if (lab) labelGap = cr.top - lab.getBoundingClientRect().bottom;
          }
        } else {
          /* 셰브론 = 오른끝에 붙은 24~40px 짜리 칸. */
          const cand = Array.from(ctl.querySelectorAll<HTMLElement>('*')).filter((e) => {
            const w = e.getBoundingClientRect().width;
            return w >= 24 && w <= 40 && e.children.length <= 1;
          });
          const last = cand[cand.length - 1];
          const chev =
            last && cr.right - last.getBoundingClientRect().right < 20
              ? last.getBoundingClientRect().width : 0;
          const valueLeaf = Array.from(ctl.querySelectorAll<HTMLElement>('*')).find(
            (e) => e.children.length === 0 && e.textContent?.trim(),
          );
          cv.font = getComputedStyle(valueLeaf ?? ctl).font;
          const chrome =
            parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) +
            parseFloat(cs.borderLeftWidth) + parseFloat(cs.borderRightWidth) + chev;
          dead[name] = cr.width - chrome - cv.measureText(want).width;
        }
      }

      const fieldGaps = kids
        .slice(1)
        .map((b, i) => b.getBoundingClientRect().x - kids[i].getBoundingClientRect().right)
        .filter((g) => g > 0.5)
        .map((g) => Math.round(g * 10) / 10);

      const byBottom = new Map<number, string[]>();
      for (const k of kids) {
        const b = Math.round(k.getBoundingClientRect().bottom);
        const list = byBottom.get(b) ?? [];
        list.push(nameOf(k));
        byBottom.set(b, list);
      }

      let card: HTMLElement | null = row;
      while (card && getComputedStyle(card).paddingLeft === '0px') card = card.parentElement;
      const pad = card ? parseFloat(getComputedStyle(card).paddingLeft) : null;
      const cr = card ? card.getBoundingClientRect() : null;
      const rr = row.getBoundingClientRect();

      return {
        found: true,
        dead: Object.fromEntries(
          Object.entries(dead).map(([k, v]) => [k, Math.round(v * 10) / 10]),
        ),
        fieldGaps,
        labelGap: labelGap === null ? null : Math.round(labelGap * 10) / 10,
        lines: Array.from(byBottom.values()),
        pad,
        edgeLeft: cr ? Math.round((rr.x - cr.x) * 10) / 10 : null,
        edgeRight: cr ? Math.round((cr.right - rr.right) * 10) / 10 : null,
      };
    },
    { anchor, longest, minChildren, editCh: EDIT_CH },
  );
}

/** 웹폰트가 온 뒤 폭이 한 번 더 계산된다 — 그 프레임까지 기다린다. */
async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(500);
}

/** 백테스트 북 한 줄의 칸 → **가장 넓은 가능한 내용**. */
const BOOK_LONGEST: Record<string, string> = {
  종류: '현금채권',
  종목: '캐피탈채 AA-',
  만기: '1.5Y',
  '규모 (억)': '9,999',
  진입일: '2026-09-23',
  청산일: '2026-09-23',
};

for (const vp of VIEWPORTS) {
  test.describe(`백테스트 북 · ${vp.name}`, () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(
        '/?g=outright&bt=' + encodeURIComponent('CB:KTB:3M,1,10000000000,2026-08-24'),
      );
      await page.getByText('청산일', { exact: true }).first().waitFor();
      await settle(page);
    });

    test('T1·T2·T3·T4 — 한 행의 폭과 틈', async ({ page }) => {
      const r = await measureRow(page, '청산일', BOOK_LONGEST, 4);
      expect(r.found, '북 한 줄을 못 찾았어요').toBe(true);

      /* T1 — 죽은 폭. 여섯 칸 전부 기준 안에. */
      const fat = Object.entries(r.dead).filter(([, v]) => v > T1_DEAD_MAX);
      expect(
        fat.map(([k, v]) => `${k} ${v}`),
        `죽은 폭이 ${T1_DEAD_MAX}px 을 넘는 칸`,
      ).toEqual([]);
      expect(Object.keys(r.dead).length, '잰 칸이 너무 적어요').toBeGreaterThanOrEqual(5);

      /* T2 — 칸↔칸, 라벨→컨트롤. */
      expect(Math.min(...r.fieldGaps)).toBeGreaterThanOrEqual(T2_FIELD_MIN);
      expect(r.labelGap ?? 0).toBeGreaterThanOrEqual(T2_LABEL_MIN);

      /* T3 — 창 안쪽 여백보다 가까운 내용이 없다. */
      expect(r.edgeLeft ?? -1).toBeGreaterThanOrEqual((r.pad ?? 0) - 1);
      expect(r.edgeRight ?? -1).toBeGreaterThanOrEqual((r.pad ?? 0) - 1);

      /* T4 — 혼자 접히는 요소가 없다. */
      expect(
        r.lines.filter((l) => l.length === 1),
        '혼자 선 줄 — 접힘은 묶음 단위여야 해요',
      ).toEqual([]);
    });

    test('T5 — 버튼 줄의 **글자** 틈이 같다', async ({ page }) => {
      const ink = await page.evaluate(() => {
        const add = Array.from(document.querySelectorAll('button')).find(
          (b) => b.textContent?.trim() === '줄 추가',
        );
        if (!add?.parentElement) return null;
        const kids = Array.from(add.parentElement.children) as HTMLElement[];
        const edge = (el: HTMLElement, side: 'L' | 'R') => {
          const leaves = Array.from(el.querySelectorAll<HTMLElement>('*')).filter(
            (n) => n.children.length === 0 && n.textContent?.trim(),
          );
          const t = leaves.length ? (side === 'L' ? leaves[0] : leaves[leaves.length - 1]) : el;
          const rg = document.createRange();
          rg.selectNodeContents(t);
          const b = rg.getBoundingClientRect();
          return side === 'L' ? b.left : b.right;
        };
        return kids.slice(1).map((e, i) => Math.round(edge(e, 'L') - edge(kids[i], 'R')));
      });
      expect(ink, '버튼 줄을 못 찾았어요').not.toBeNull();
      expect(Math.min(...ink!)).toBeGreaterThanOrEqual(T2_CAPTION_MIN);
      /* 같은 행의 같은 관계는 같은 틈이다 — 값이 하나여야 한다. */
      expect(new Set(ink!).size, `글자 틈이 여럿이에요: ${ink!.join(' · ')}`).toBe(1);
    });
  });
}

const PM_LONGEST: Record<string, string> = {
  계기: '국채선물',
  만기: '1.5Y',
  방향: '리시브',
  '체결 금리(%)': '9.9999',
  '명목(억)': '9,999.9',
  체결일: '2026-09-23',
  묶음: 'BSS 2Y 스티프너',
  '룩백 (일)': '600',
  '진입 σ': '20.0',
  '청산 σ': '20.0',
  '손절 σ': '20.0',
  '진입 규칙': '밴드 복귀',
};

for (const vp of VIEWPORTS) {
  test(`포트폴리오 담는 줄 · ${vp.name} — 열두 칸의 폭과 틈`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/?g=portfolio');
    await page.getByText('룩백 (일)', { exact: true }).waitFor();
    await settle(page);
    const r = await measureRow(page, '룩백 (일)', PM_LONGEST, 6);
    expect(r.found, '담는 줄을 못 찾았어요').toBe(true);
    const fat = Object.entries(r.dead).filter(([, v]) => v > T1_DEAD_MAX);
    expect(fat.map(([k, v]) => `${k} ${v}`)).toEqual([]);
    expect(Object.keys(r.dead).length).toBeGreaterThanOrEqual(10);
    expect(Math.min(...r.fieldGaps)).toBeGreaterThanOrEqual(T2_FIELD_MIN);
    expect(r.labelGap ?? 0).toBeGreaterThanOrEqual(T2_LABEL_MIN);
    expect(r.lines.filter((l) => l.length === 1)).toEqual([]);
  });
}

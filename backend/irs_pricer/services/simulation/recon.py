"""IRS 일별 손익 대사표 — chart.build_chart_data 에서 추출 (2026-08-10).

영업일마다: 그날의 쇼크 par 커브를 부트스트랩하고 KRD_TENORS 를 범프해
포트폴리오 KRD 를 재계산, 전일(start-of-day) KRD × 당일 Δbp 선형 추정을
FM 엔진의 실제 증분과 나란히 적는다. 행의 `pvbp` 도 **그 추정에 쓴 전일
KRD 그대로**다 [OWNER, 2026-08-11 — "전일걸 가져와서 붙이는게 대사하기
편하지 않을까"]: 한 블록 안에서 KRD × Δbp = 손익이 닫히고, 눈이 전일
블록으로 오갈 일이 없다. 마지막 날의 종가 KRD(다음 영업일로 들고 가는
리스크)는 표 끝의 이월 앵커 행(`carryover: True`, 손익 필드는 전부
None — 아직 없는 날의 손익을 0 이라고 말하지 않는다)이 싣는다. 응답의
`irsDailyReconciliation` 이 이 함수의 반환값 그대로다.

**바이트 동일 이식**: 로직·라운딩·필드 전부 chart.py 에 있던 그대로다.
골든 픽스처(test_simulate_api)가 결과 불변을 못박는다. 추출로 달라진 것
하나는 **계산 시점**이다 — IRS_Trade 사전 빌드와 평균 float 유도가 종전엔
skip_recon=True(분포 밴드 런)에서도 돌았는데, 이제 대사표를 만들 때만
돈다. 산출물에는 안 닿는 순수 낭비 제거다.

curve_cache 계약(chart.py 모듈 주석과 동일): 부트스트랩은 반드시
`qe.bootstrap_zero_curve` 모듈 속성 조회로 — 메모 래퍼가 끼어들 자리다.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from ...engine import quant_engine as qe
from .kr_calendar import next_kr_business_day
from .models import FrontendPosition
from .swap_schedule import resolve_swap_horizon


def build_pos_trades(
    irs_positions: list[FrontendPosition],
    base_date: date,
    base_date_str: str,
) -> list[tuple]:
    """포지션별 IRS_Trade 사전 빌드 (불변 스케줄, 대사 루프 밖에서 1회).

    반환: [(IRS_Trade | None, float_rate_pct)] — 만기가 시작일보다 이르면
    None(대사에서 제외). startDate 가 없으면 다음 변동일에서 분기(3M)를
    역산해 시작일을 근사한다.
    """
    pos_trades: list[tuple] = []
    for _rp in irs_positions:
        _rt0, _t_nxt_r = resolve_swap_horizon(_rp.remainingDays, _rp.nextFixingDate, base_date_str)
        _flt_r = float(_rp.currentFloatRate or 0.0)
        _fr_r  = float(_rp.couponRate or 0.0)
        _dir_r = int(_rp.direction or 1)
        _N_r   = float(_rp.notional or 0.0)
        _sec_r = _rp.sector or "IRS"

        _mat_dt_r = qe._modfol_bd(base_date + timedelta(days=round(_rt0 * 365)))
        _freq_m_r = 3   # quarterly (float_freq=0.25)
        _start_dt_r = None
        _sdate_str  = str(_rp.startDate)[:10] if _rp.startDate else ""
        if _sdate_str:
            try:
                _start_dt_r = date.fromisoformat(_sdate_str)
            except Exception:
                pass
        if _start_dt_r is None:
            _nxt_raw_r  = base_date + timedelta(days=max(round(_t_nxt_r * 365), 1))
            _nxt_adj_r  = qe._next_business_day(_nxt_raw_r)
            _start_dt_r = qe._modfol_bd(qe._subtract_months(_nxt_adj_r, _freq_m_r))

        if _mat_dt_r > _start_dt_r:
            _trade_r = qe.IRS_Trade(_start_dt_r, _mat_dt_r, _fr_r, _dir_r, _N_r, sector=_sec_r)
        else:
            _trade_r = None
        pos_trades.append((_trade_r, _flt_r))
    return pos_trades


def build_irs_daily_recon(
    *,
    irs_positions: list[FrontendPosition],
    par_rates: list[tuple[float, float]],
    base_date: date,
    base_date_str: str,
    sim_days: int,
    shock_type: str,
    irs_sc_t: np.ndarray,
    irs_sc_bp: np.ndarray,
    path_factor_arr: "np.ndarray | None",
    funding_events: list[dict],
    bizday_schedule: list[tuple],
    irs_fm_mtm: np.ndarray,
    irs_fm_mtm_theta: np.ndarray,
    irs_daily_scf: np.ndarray,
    irs_fm_carry_cash: np.ndarray | None = None,
) -> list[dict]:
    """IRS 일별 손익 대사 — 정확한 일별 KRD 재계산.

    전략: 선형 에이징 완전 폐기 → IRS_Trade 기반 실시간 KRD.
    최적화: 일당 12개 범프 커브 1회 빌드 + 배치 DF LUT → 종목별 순수 NPV
    차분만 수행.

    ── 이 표는 다시 **스왑만** 센다 [OWNER, 2026-08-25 — 엔진 단위 분리] ──

    2026-08-21 판은 혼합 북의 채권 성분(평가·캐리·조달)을 이 표의 스왑 열에
    합산했다 — 표합이 헤드라인과 닫히게 하려고. 그 판이 드러낸 것이 채권
    다리에는 롤다운 항 자체가 없다는 사실이었고(스왑 = unchanged term
    structure, 채권 = unchanged yields 의 비대칭), 오너 룰링으로 채권 대사는
    자기 엔진 레인(`bond_recon.build_bond_daily_recon` + chart.py 의
    bondRolldown 누적기)으로 독립했다. 스왑 표는 v1 계약 그대로 돌아온다:
    조달 필드 없음, 채권 몫 없음. 호출자는 스왑과 par 커브가 있을 때만
    이 표를 세운다 — 채권만 북의 대사는 채권 표가 진다.
    """
    _recon_names  = qe.KRD_NAMES
    _recon_tenors = qe.KRD_TENORS

    # ── BOK 이벤트 목록 (계단식 충격 모델에 사용) ───────────────────────────
    # 1D/3M: BOK 이벤트 누적 bp (계단식)
    # 3M~6M: BOK ↔ IRS ramp 선형 보간
    # 6M+:   IRS shock_curve × 누적 factor (기존 ramp/step)
    try:
        _bok_evts_r = sorted(
            [{"day": (date.fromisoformat(ev["date"]) - base_date).days,
              "bp":  float(ev.get("shiftBp", 0))}
             for ev in (funding_events or [])
             if ev.get("date") and 0 <= (date.fromisoformat(ev["date"]) - base_date).days <= sim_days],
            key=lambda x: x["day"],
        )
    except Exception:
        _bok_evts_r = []

    def _cum_bok_r(day: int) -> float:
        """BOK 이벤트 누적 bp (day 이하 이벤트 합산, 계단식)."""
        return sum(e["bp"] for e in _bok_evts_r if e["day"] <= day)

    # 램프 충격을 영업일 기준으로 정규화(주말 skip) — simulate_irs_path_fm
    # (irs_fm_mtm)과 동일한 기준을 써야 "추정"과 "실제"가 일관된다. 캘린더
    # 일수로 나누면 월요일에 토+일+월 3일치가 한꺼번에 반영되어 부풀어 보인다.
    _biz_ranks_r  = qe.biz_day_ranks(base_date, sim_days)
    _biz_total_r  = int(_biz_ranks_r[-1]) if _biz_ranks_r[-1] > 0 else max(sim_days, 1)

    def _ramp_factor_r(day: int) -> float:
        return float(_biz_ranks_r[min(max(day, 0), len(_biz_ranks_r) - 1)]) / _biz_total_r

    def _cum_shock_r(tau: float, day: int) -> float:
        """테너별 누적 충격 bp (계단식 1D/3M → 선형 소멸 at 1Y → ramp 1Y+).

        SIM2-4: 경로 정합이 활성화된 요청은 1Y+ ramp 성분이 biz-ranked ramp
        대신 설계 경로 팩터를 따른다 — FM 엔진(irs_fm_mtm)과 같은 기준을 써야
        "추정"과 "실제"가 일관된다는 기존 원칙 그대로다.
        """
        if path_factor_arr is not None:
            _fac = float(path_factor_arr[min(max(day, 0), sim_days)])
        else:
            _fac = _ramp_factor_r(day) if shock_type == "ramp" else (1.0 if day > 0 else 0.0)
        _ramp_bp = float(np.interp(tau, irs_sc_t, irs_sc_bp)) * _fac
        if not _bok_evts_r:
            return _ramp_bp
        _bok_bp = _cum_bok_r(day)
        if tau <= 0.25:          # 1D, 3M: BOK 계단식 100% 직결
            return _bok_bp
        elif tau < 1.0:          # 3M~1Y: BOK 선형 소멸 (6M≈67%, 9M≈33%)
            w = (tau - 0.25) / 0.75
            return _bok_bp * (1.0 - w) + _ramp_bp * w
        else:                    # 1Y+: IRS shock_curve ramp만 적용
            return _ramp_bp

    # ── 포지션별 IRS_Trade + Day 0 평균 float ───────────────────────────────
    _pos_trades = build_pos_trades(irs_positions, base_date, base_date_str)
    _flts_r    = [flt for (_, flt) in _pos_trades if flt > 0]
    _avg_flt0  = float(np.mean(_flts_r)) / 100.0 if _flts_r else 0.03   # Day 0 기준 float (소수)

    # ── 일자 t 의 쇼크 커브 + 포트폴리오 KRD (루프 본문과 시드가 공유) ─────
    # 마켓 컨벤션: "N일자 KRD/PVBP"는 N의 결제일(다음 영업일) 기준으로 재평가한
    # 값을 보고한다 — irs_fm_mtm(simulate_irs_path_fm 내부에서 이미 동일 규칙
    # 적용됨)과 일관되도록 여기서도 val_date를 결제일로 한 번 밀어서 넘긴다.
    def _krd_at(_vd: date, _cd: int) -> dict[str, float]:
        # par 커브 구성: 6M+ ramp + 1D/3M BOK 계단 앙커. 6M+ par 노드는
        # ramp 충격 그대로, 1D/3M 앙커는 기본 float rate + BOK 누적 bp.
        _par_day: list[tuple[float, float]] = [
            (t_p, r_p + float(np.interp(t_p, irs_sc_t, irs_sc_bp))
             * (_ramp_factor_r(_cd) if shock_type == "ramp" else (1.0 if _cd > 0 else 0.0))
             * 1e-4)
            for t_p, r_p in par_rates
        ]
        _par_anch = qe._inject_short_anchors(_par_day, _avg_flt0 + _cum_bok_r(_cd) * 1e-4)
        # 기준 + KRD_TENORS 범프 커브 (일당 1회 빌드) → 포트폴리오 KRD 합산
        _zc_b = qe.bootstrap_zero_curve(_par_anch)
        return qe.portfolio_krd_day(_pos_trades, next_kr_business_day(_vd), _zc_b, qe.build_bumped_curves(_par_anch))

    # ── 전일(start-of-day) KRD 시드 [OWNER, 2026-08-10 — 교과서 관행 정합] ──
    # 선형 추정은 **전일 KRD × 당일 Δbp** 다. 종전에는 당일(end-of-day) KRD 를
    # 썼는데, P&L explain 의 민감도 방식 표준은 "어제의 민감도 × 오늘의 변동"
    # 이다(외부 검증 2026-08-10) — 이벤트·리픽싱으로 KRD 가 점프하는 날에는
    # 이동 후 민감도로 이동분을 설명하는 순서 역전이 된다. 행의 `pvbp` 도
    # **같은 전일 KRD** 다 [OWNER, 2026-08-11 — 표시가 그날 KRD 이던 동안은
    # 한 블록의 KRD × Δbp 가 손익 줄과 안 맞아 눈이 전일 블록으로 오가야
    # 했다]. 그날 종가 KRD 는 다음 행이(마지막 날 것은 이월 앵커 행이)
    # 보여준다. 시드는 day 0(기준일, 쇼크 전) 의 KRD 다.
    _pvbp_prev_r = _krd_at(base_date, 0)

    # ── 세타 귀속: 평가일 기준 **포워드** [OWNER, 2026-08-11 — "금요일날
    # 토일월의 캐리롤다운이 반영되어야 … 금요일에 튀어야" · "같이 맞춰"] ──
    # 행 t 의 캐리/롤다운/세타 = (t → 다음 영업일) 구간의 **그 행의** 몫 — 금요일
    # 행이 주말 사흘치를 싣는다. 평가(마켓무브)는 여전히 전일 대비(백워드,
    # 실제 증분 − 백워드 세타). 그날 손익(totalActual)은 평가 + 포워드 세타
    # — 백테스트 recon(app/backtest.py _book_recon)과 같은 데스크 관행이고,
    # 마지막 행은 호라이즌이 끝나 이월할 밤이 없으므로 세타 0 이다. D+0 행이
    # 새로 선다(백테스트의 진입일 행과 같은 것): 평가·추정 0, 첫날 밤 세타,
    # KRD 는 시드(쇼크 전 커브)의 수준값. settleCf/npvChange 는 그날 실제로
    # 정산된 현금의 장부 사실이라 백워드 그대로 둔다.
    _cals = [c for (_d, c, _dt) in bizday_schedule]

    def _fwd_theta(j: int) -> tuple[int, int, int]:
        """행 j 의 (theta, carry, rolldown) — **그 행의 밤** 몫.

        ★2026-10-16 (프로덕트 전수조사 셋째 판) — 종전에는 `(cal_j → cal_{j+1})`
        증분이었다. 그런데 이 궤적들은 **결제일(T+1) 기준**이다
        (`carry_split.base_cash_carry_path` 의 `settle_d = next_kr_business_day(...)`
        와 엔진의 세타 궤적이 같은 기준): 색인 `cal_j` 의 값이 이미 「영업일
        d_{j+1} 시점의 액크루얼」이라, 그 차분은 **다음 행의 밤**이었다.

        요일이 그것을 드러냈다 — 주말 사흘치가 금요일이 아니라 **목요일** 행에
        섰다(100억 3Y 0bp 90일 실측: 목 평균 609,606 대 나머지 ~225,000).
        [OWNER 2026-08-11] 규약은 「결제일 기준이 **아니라** 평가일 기준 … 금요일에
        튀어야」이고, 백테스트(`app/backtest._book_recon`)와 **이 응답의 채권 표**가
        둘 다 금요일에 선다. 시뮬의 스왑 표 하나만 어긋나 있었고, 이 함수의 머리
        주석은 그 규약을 인용하면서 반대로 내고 있었다.

        수리 = **한 행 당기기**. 행 j 의 밤 = V(d_{j+1}) − V(d_j)
        = `A[cal_j] − A[cal_{j-1}]` (A = 그 궤적, cal_{-1} = 0).

        ★합은 보존된다 — 이동이라 망원경 합이 그대로 `A[cal_{m-1}]` 이다. 그래서
        헤드라인·차트·일별 분해·세로합(`test_simulate_mixed_recon` 의 그 단언)은
        **한 자도 안 움직이고** 표의 날짜만 맞는다. 첫 행(j=0)은 `A[cal_0] − 0`
        (= 발효일의 밤)이고, D+0 앵커 행은 **0** 이다(아래 그 자리의 주석).
        """
        if j >= len(_cals):
            return 0, 0, 0
        a = _cals[j - 1] if j >= 1 else 0
        b = _cals[j]
        theta = round(float(irs_fm_mtm_theta[b] - irs_fm_mtm_theta[a]))
        carry = (
            round(float(irs_fm_carry_cash[b] - irs_fm_carry_cash[a]))
            if irs_fm_carry_cash is not None
            else 0
        )
        return theta, carry, theta - carry

    irs_daily_recon: list[dict] = []
    # D+0 앵커 행 — 위 주석 참조. 세타는 **0** 이다 [2026-10-16]: 이 행의 밤은
    # 거래일 → 발효일(T+1) 한 밤이고, 스왑은 아직 시작하지 않아 쌓이는 것이
    # 없다(백테스트의 `startup` 과 같은 자리 — 「평가도 캐리도 아닌 한 밤」).
    # 종전에는 여기가 `A[cal_0] − A[0]`(= 발효일의 밤)을 싣고 있었고, 그래서
    # 표 전체가 한 행 앞서 있었다. 그 몫은 이제 첫 영업일 행이 진다.
    if _cals:
        _t0 = 0
        _c0 = 0
        irs_daily_recon.append({
            "date":         base_date.isoformat(),
            "day":          0,
            "pvbp":         {_n: round(_pvbp_prev_r[_n]) for _n in _recon_names},
            "cumulativeBp": {_n: 0.0 for _n in _recon_names},
            "dailyDbp":     {_n: 0.0 for _n in _recon_names},
            "pnl":          {_n: 0 for _n in _recon_names},
            "totalEstPnl":  0,
            "totalActual":  _t0,
            "settleCf":     0,
            "npvChange":    0,
            "residual":     0,
            "thetaPnl":     _t0,
            "valuationPnl": 0,
            "carryPnl":     _c0,
            "rolldownPnl":  _t0 - _c0,
        })

    _prev_cal_r = 0
    for _row_j, (_val_date_r, _cal_day, _dt_cal) in enumerate(bizday_schedule):
        # ── 테너별 누적 충격 bp 계산 (계단식 1D/3M + ramp 6M+) ─────────────
        _cum_r    = {_n: _cum_shock_r(_tau, _cal_day)    for _n, _tau in zip(_recon_names, _recon_tenors)}
        _cum_prev = {_n: _cum_shock_r(_tau, _prev_cal_r) for _n, _tau in zip(_recon_names, _recon_tenors)}
        _daily_dbp_r = {_n: _cum_r[_n] - _cum_prev[_n] for _n in _recon_names}

        _pvbp_r = _krd_at(_val_date_r, _cal_day)   # 오늘 종가 KRD — 다음 행의 전일 KRD

        _pnl_r       = {_n: -_pvbp_prev_r[_n] * _daily_dbp_r[_n] for _n in _recon_names}
        _total_est   = round(sum(_pnl_r.values()))
        _settle      = round(float(np.sum(irs_daily_scf[_prev_cal_r + 1:_cal_day + 1])))
        _total_act   = round(float(irs_fm_mtm[_cal_day] - irs_fm_mtm[_prev_cal_r]))
        _npv_change  = _total_act - _settle
        # 평가손익(=마켓무브, 백워드): 실제 증분에서 **백워드** 세타(전일 →
        # 오늘, 커브 고정 궤적의 같은 구간 변화)를 뺀 나머지 — 이 정의는
        # 종전과 동일하다. 표시되는 세타 3필드만 포워드다(위 주석).
        _theta_back  = round(float(irs_fm_mtm_theta[_cal_day] - irs_fm_mtm_theta[_prev_cal_r]))
        _valuation_pnl = _total_act - _theta_back
        # [OWNER, 2026-08-11] 포워드 세타 (오늘 → 다음 영업일) + 3분해:
        # 캐리(동결 커브 순액크루얼+정산, carry_split.py) / 롤다운(잔차 —
        # 표시 정밀도 가산성 보존).
        _theta_pnl, _carry_pnl, _rolldown_pnl = _fwd_theta(_row_j)
        irs_daily_recon.append({
            "date":         _val_date_r.isoformat(),
            "day":          _cal_day,
            "pvbp":         {_n: round(_pvbp_prev_r[_n]) for _n in _recon_names},
            "cumulativeBp": {_n: round(_cum_r[_n], 3) for _n in _recon_names},
            "dailyDbp":     {_n: round(_daily_dbp_r[_n], 4) for _n in _recon_names},
            "pnl":          {_n: round(_pnl_r[_n]) for _n in _recon_names},
            "totalEstPnl":  _total_est,
            # 그날 손익 = 평가(백워드) + 세타(포워드) — 데스크 관행 데일리.
            # 누적 궤적의 증분(구 정의)과는 세타 타이밍이 하루 어긋난다.
            "totalActual":  _valuation_pnl + _theta_pnl,
            "settleCf":     _settle,
            "npvChange":    _npv_change,
            # 선형화 잔차: 추정이 설명하는 대상은 평가(커브무브)뿐이다 —
            # 백테스트 recon 과 같은 정의로 정렬(세타를 섞어 빼지 않는다).
            "residual":     _valuation_pnl - _total_est,
            "thetaPnl":     _theta_pnl,
            "valuationPnl": _valuation_pnl,
            "carryPnl":     _carry_pnl,
            "rolldownPnl":  _rolldown_pnl,
        })
        _prev_cal_r  = _cal_day
        _pvbp_prev_r = _pvbp_r

    # ── 이월 앵커 행 [OWNER, 2026-08-11 — 이월 리스크 앵커] ────────────────
    # 행의 pvbp 가 전일 KRD 가 되면서 마지막 날의 종가 KRD(다음 영업일로
    # 들고 가는 리스크)가 표에서 사라진다 — 그 값을 D+0 앵커와 대칭인 끝
    # 앵커가 싣는다. 커브는 호라이즌 종점의 것이 그대로 서 있으므로
    # cumulativeBp 는 마지막 행 값의 이월이고, 손익 필드는 전부 None 이다
    # (아직 오지 않은 날의 손익을 0 이라고 말하지 않는다 — 공란 정책).
    if bizday_schedule:
        _co_date = next_kr_business_day(_val_date_r)
        irs_daily_recon.append({
            "date":         _co_date.isoformat(),
            "day":          (_co_date - base_date).days,
            "pvbp":         {_n: round(_pvbp_prev_r[_n]) for _n in _recon_names},
            "cumulativeBp": {_n: round(_cum_r[_n], 3) for _n in _recon_names},
            "dailyDbp":     {},
            "pnl":          {},
            "totalEstPnl":  None,
            "totalActual":  None,
            "settleCf":     None,
            "npvChange":    None,
            "residual":     None,
            "thetaPnl":     None,
            "valuationPnl": None,
            "carryPnl":     None,
            "rolldownPnl":  None,
            "carryover":    True,
        })

    return irs_daily_recon

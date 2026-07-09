"""
algorithm.py — 라오어 무한매수법 V2.2 알고리즘 엔진

시뮬레이션 기반으로 1회차부터 자동 추적하며,
매수/매도 LOC 가격 및 추천을 계산합니다.
"""

import json
import os
import math
from datetime import datetime
from typing import Optional

# 시뮬레이션 상태 파일 경로
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")


def _ensure_state_dir():
    """상태 디렉토리 생성"""
    os.makedirs(STATE_DIR, exist_ok=True)


def _state_file(ticker: str) -> str:
    """종목별 상태 파일 경로"""
    return os.path.join(STATE_DIR, f"{ticker}_state.json")


def load_state(ticker: str) -> dict:
    """
    종목의 현재 시뮬레이션 상태를 로드합니다.
    파일이 없으면 초기 상태를 반환합니다.

    Returns:
        {
            "ticker": str,
            "current_round": int,       # 현재 회차 (1~40)
            "total_invested": float,     # 총 투자액 ($)
            "total_shares": float,       # 총 보유 주수
            "avg_price": float,          # 평단가
            "history": [...],            # 매수/매도 이력
            "status": str,              # "active" | "completed" | "stopped"
            "created_at": str,
            "updated_at": str
        }
    """
    _ensure_state_dir()
    filepath = _state_file(ticker)

    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    # 초기 상태
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "ticker": ticker,
        "current_round": 0,
        "total_invested": 0.0,
        "total_shares": 0.0,
        "avg_price": 0.0,
        "history": [],
        "status": "waiting",  # 아직 첫 매수 전
        "created_at": now,
        "updated_at": now,
    }


def save_state(state: dict):
    """상태를 파일에 저장합니다."""
    _ensure_state_dir()
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filepath = _state_file(state["ticker"])
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def calculate_round_budget(seed_money: float, total_rounds: int = 40) -> float:
    """
    1회차당 매수 시도액을 계산합니다.

    Args:
        seed_money: 해당 종목에 배정된 총 시드머니
        total_rounds: 전체 분할 회차 (기본 40)

    Returns:
        1회차당 매수액
    """
    return seed_money / total_rounds


class InfiniteBuyV22:
    """
    라오어 무한매수법 V2.2 알고리즘 엔진

    핵심 규칙:
    ─────────────────────────────────────────────
    [매수 규칙]
    - 원금 40분할, 매일 1회차씩 LOC 주문
    - 1회차: 시장가 매수 (RSI < 60 시 진입 권장)
    - 2~19회차:
        · LOC 평단매수 (50%): 평단가로 LOC 주문
        · LOC 큰수매수 (50%): 현재가 +10~15% (단, 평단가 +5% 초과 금지)
    - 20~40회차:
        · 평단가 이하에서만 매수 (큰수매수 중단)

    [매도 규칙]
    - 1~19회차: 보유 전량, 평단가 +10% 지정가 매도
    - 20~40회차: 절반은 평단가 +5%, 나머지 절반은 평단가 +10% 분할 매도

    [쿼터 손절]
    - 40회차 소진 시: 보유 물량의 1/4 손절하여 시드 재확보
    ─────────────────────────────────────────────
    """

    def __init__(self, config: dict):
        self.seed_money = config.get("seed_money_per_ticker", 4000)
        self.total_rounds = config.get("total_rounds", 40)
        self.sell_target_early = config.get("sell_target_pct_early", 10.0)
        self.sell_target_late_high = config.get("sell_target_pct_late_high", 10.0)
        self.sell_target_late_low = config.get("sell_target_pct_late_low", 5.0)
        self.loc_big_buy_premium = config.get("loc_big_buy_premium_pct", 10.0)
        self.loc_big_buy_cap = config.get("loc_big_buy_cap_above_avg_pct", 5.0)
        self.late_phase_start = config.get("late_phase_start_round", 20)
        self.rsi_entry_threshold = config.get("rsi_entry_threshold", 60)
        self.round_budget = calculate_round_budget(self.seed_money, self.total_rounds)

    def get_recommendation(self, ticker: str, current_price: float, rsi: Optional[float] = None) -> dict:
        """
        현재 상태와 가격을 기반으로 오늘의 매수/매도 추천을 생성합니다.

        Args:
            ticker: 종목 코드
            current_price: 현재 가격
            rsi: RSI 값 (없으면 진입 판단 생략)

        Returns:
            추천 딕셔너리
        """
        state = load_state(ticker)
        current_round = state["current_round"]
        avg_price = state["avg_price"]
        total_shares = state["total_shares"]
        total_invested = state["total_invested"]

        recommendation = {
            "ticker": ticker,
            "current_price": current_price,
            "current_round": current_round,
            "avg_price": round(avg_price, 4),
            "total_shares": round(total_shares, 4),
            "total_invested": round(total_invested, 2),
            "remaining_budget": round(self.seed_money - total_invested, 2),
            "round_budget": round(self.round_budget, 2),
            "status": state["status"],
            "rsi": rsi,
            "actions": [],
            "sell_orders": [],
            "summary": "",
        }

        # ── 상태별 분기 ──

        # 1) 시뮬레이션 완료 또는 중단 상태
        if state["status"] in ("completed", "stopped"):
            recommendation["summary"] = "🏁 시뮬레이션 완료. 새 사이클을 시작하려면 상태를 리셋하세요."
            return recommendation

        # 2) 첫 매수 전 (waiting)
        if state["status"] == "waiting" or current_round == 0:
            return self._recommend_first_buy(recommendation, current_price, rsi)

        # 3) 40회차 소진 — 쿼터 손절
        if current_round >= self.total_rounds:
            return self._recommend_quarter_stop(recommendation, current_price, avg_price, total_shares)

        # 4) 2~19회차 (초기 페이즈)
        if current_round < self.late_phase_start:
            return self._recommend_early_phase(recommendation, current_price, avg_price, total_shares)

        # 5) 20~40회차 (후기 페이즈)
        return self._recommend_late_phase(recommendation, current_price, avg_price, total_shares)

    def _recommend_first_buy(self, rec: dict, price: float, rsi: Optional[float]) -> dict:
        """1회차: 첫 매수 추천"""
        budget = self.round_budget

        # RSI 체크
        rsi_ok = rsi is None or rsi < self.rsi_entry_threshold
        shares_to_buy = math.floor((budget / price) * 10000) / 10000  # 소수점 4자리

        if rsi_ok:
            rec["actions"].append({
                "type": "BUY",
                "method": "시장가 (1회차 첫 매수)",
                "price": round(price, 2),
                "budget": round(budget, 2),
                "estimated_shares": shares_to_buy,
                "note": "장중 아무 시점에 1회차 분량 시장가 매수",
            })
            rec["summary"] = f"🟢 1회차 진입 신호! RSI={rsi or 'N/A'} | 시장가 매수 추천 (${budget:.0f})"
        else:
            rec["actions"].append({
                "type": "WAIT",
                "method": "대기",
                "note": f"RSI({rsi:.1f}) ≥ {self.rsi_entry_threshold} → 고점 진입 위험. 대기 권장.",
            })
            rec["summary"] = f"🟡 RSI={rsi:.1f} 과열 → 진입 대기. RSI {self.rsi_entry_threshold} 미만 시 시작."

        return rec

    def _recommend_early_phase(self, rec: dict, price: float, avg_price: float, total_shares: float) -> dict:
        """2~19회차: LOC 평단매수(50%) + LOC 큰수매수(50%) + 평단가+10% 매도"""
        budget = self.round_budget
        half_budget = budget / 2
        current_round = rec["current_round"]

        # ── 매수 주문 ──

        # 장중 가격이 평단가보다 낮으면 전량 시장가 매수도 가능
        if price < avg_price:
            shares = math.floor((budget / price) * 10000) / 10000
            rec["actions"].append({
                "type": "BUY",
                "method": "장중 시장가 (평단가 이하 → 전량 매수 가능)",
                "price": round(price, 2),
                "budget": round(budget, 2),
                "estimated_shares": shares,
                "note": f"현재가(${price:.2f}) < 평단가(${avg_price:.2f}) → 장중 전량 매수 가능",
            })
        else:
            # LOC 평단매수 (절반)
            loc_avg_shares = math.floor((half_budget / avg_price) * 10000) / 10000
            rec["actions"].append({
                "type": "BUY",
                "method": "LOC 평단매수 (50%)",
                "price": round(avg_price, 2),
                "budget": round(half_budget, 2),
                "estimated_shares": loc_avg_shares,
                "note": f"평단가(${avg_price:.2f})로 LOC 주문",
            })

            # LOC 큰수매수 (절반) — 현재가 +10~15%, 단 평단가+5% 초과 불가
            big_buy_price = price * (1 + self.loc_big_buy_premium / 100)
            cap_price = avg_price * (1 + self.loc_big_buy_cap / 100)
            final_big_price = min(big_buy_price, cap_price)

            loc_big_shares = math.floor((half_budget / final_big_price) * 10000) / 10000
            rec["actions"].append({
                "type": "BUY",
                "method": "LOC 큰수매수 (50%)",
                "price": round(final_big_price, 2),
                "budget": round(half_budget, 2),
                "estimated_shares": loc_big_shares,
                "note": f"종가+{self.loc_big_buy_premium}% 또는 평단+{self.loc_big_buy_cap}% 중 낮은 가격(${final_big_price:.2f})",
            })

        # ── 매도 주문 ──
        sell_price = avg_price * (1 + self.sell_target_early / 100)
        rec["sell_orders"].append({
            "method": f"지정가 매도 (평단+{self.sell_target_early}%)",
            "price": round(sell_price, 2),
            "shares": round(total_shares, 4),
            "note": f"보유 전량({total_shares:.4f}주) → 평단가+{self.sell_target_early}%=${sell_price:.2f}",
        })

        rec["summary"] = (
            f"📊 {current_round}회차 | 평단가 ${avg_price:.2f} | "
            f"매수 LOC ${avg_price:.2f} / ${min(big_buy_price if price >= avg_price else price, cap_price if price >= avg_price else price):.2f} | "
            f"매도 ${sell_price:.2f}"
        )
        return rec

    def _recommend_late_phase(self, rec: dict, price: float, avg_price: float, total_shares: float) -> dict:
        """20~40회차: 평단가 이하에서만 매수 + 분할 매도"""
        budget = self.round_budget
        current_round = rec["current_round"]

        # ── 매수: 평단가 이하에서만 ──
        if price <= avg_price:
            shares = math.floor((budget / price) * 10000) / 10000
            rec["actions"].append({
                "type": "BUY",
                "method": "LOC 평단매수 (후기 — 평단가 이하만)",
                "price": round(avg_price, 2),
                "budget": round(budget, 2),
                "estimated_shares": shares,
                "note": f"20회차 이후: 평단가(${avg_price:.2f}) 이하에서만 매수",
            })
        else:
            rec["actions"].append({
                "type": "WAIT",
                "method": "매수 대기 (후기 페이즈)",
                "note": f"현재가(${price:.2f}) > 평단가(${avg_price:.2f}) → 20회차 이후 큰수매수 중단. 하락 대기.",
            })

        # ── 매도: 분할 매도 ──
        half_shares = math.floor((total_shares / 2) * 10000) / 10000
        remaining_shares = round(total_shares - half_shares, 4)

        sell_price_low = avg_price * (1 + self.sell_target_late_low / 100)
        sell_price_high = avg_price * (1 + self.sell_target_late_high / 100)

        rec["sell_orders"].append({
            "method": f"1차 분할 매도 (평단+{self.sell_target_late_low}%)",
            "price": round(sell_price_low, 2),
            "shares": half_shares,
            "note": f"보유의 절반({half_shares}주) → ${sell_price_low:.2f}",
        })
        rec["sell_orders"].append({
            "method": f"2차 분할 매도 (평단+{self.sell_target_late_high}%)",
            "price": round(sell_price_high, 2),
            "shares": remaining_shares,
            "note": f"나머지 절반({remaining_shares}주) → ${sell_price_high:.2f}",
        })

        rec["summary"] = (
            f"⚠️ {current_round}회차 (후기) | 평단가 ${avg_price:.2f} | "
            f"{'매수 가능 ✅' if price <= avg_price else '매수 대기 🔴'} | "
            f"매도 ${sell_price_low:.2f} / ${sell_price_high:.2f}"
        )
        return rec

    def _recommend_quarter_stop(self, rec: dict, price: float, avg_price: float, total_shares: float) -> dict:
        """40회차 소진 — 쿼터 손절 추천"""
        quarter_shares = math.floor((total_shares / 4) * 10000) / 10000
        loss_pct = ((price - avg_price) / avg_price) * 100

        rec["actions"].append({
            "type": "SELL",
            "method": "쿼터 손절 (보유량의 1/4 매도)",
            "price": round(price, 2),
            "shares": quarter_shares,
            "note": (
                f"40회차 소진! 보유 {total_shares:.4f}주 중 1/4({quarter_shares}주) 시장가 매도. "
                f"손실률: {loss_pct:+.1f}%"
            ),
        })

        # 손절 후 남은 물량으로 매도 주문은 계속 유지
        remaining = round(total_shares - quarter_shares, 4)
        sell_price = avg_price * (1 + self.sell_target_late_low / 100)
        rec["sell_orders"].append({
            "method": "잔여 물량 매도 주문 유지",
            "price": round(sell_price, 2),
            "shares": remaining,
            "note": f"나머지 {remaining}주는 평단+{self.sell_target_late_low}%(${sell_price:.2f}) 매도 주문 유지",
        })

        rec["summary"] = (
            f"🔴 40회차 소진! 쿼터 손절 발동 | "
            f"{quarter_shares}주 손절 매도 → 시드 재확보 후 재진입"
        )
        return rec

    def simulate_buy(self, ticker: str, price: float, shares: float, method: str = "시장가"):
        """
        매수 체결을 시뮬레이션합니다 (상태 업데이트).

        Args:
            ticker: 종목 코드
            price: 체결 가격
            shares: 체결 주수
            method: 매수 방식
        """
        state = load_state(ticker)

        cost = price * shares
        state["total_invested"] += cost
        state["total_shares"] += shares
        state["current_round"] += 1

        # 평단가 재계산
        if state["total_shares"] > 0:
            state["avg_price"] = state["total_invested"] / state["total_shares"]

        state["status"] = "active"
        state["history"].append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": "BUY",
            "round": state["current_round"],
            "price": round(price, 4),
            "shares": round(shares, 4),
            "cost": round(cost, 2),
            "method": method,
            "avg_price_after": round(state["avg_price"], 4),
        })

        save_state(state)
        return state

    def simulate_sell(self, ticker: str, price: float, shares: float, method: str = "지정가"):
        """
        매도 체결을 시뮬레이션합니다 (상태 업데이트).

        Args:
            ticker: 종목 코드
            price: 체결 가격
            shares: 체결 주수
            method: 매도 방식
        """
        state = load_state(ticker)

        proceeds = price * shares
        state["total_shares"] -= shares
        state["total_shares"] = max(0, state["total_shares"])

        # 전량 매도 시 사이클 완료
        if state["total_shares"] <= 0.0001:
            state["total_shares"] = 0
            state["total_invested"] = 0
            state["avg_price"] = 0
            state["current_round"] = 0
            state["status"] = "completed"

        state["history"].append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": "SELL",
            "price": round(price, 4),
            "shares": round(shares, 4),
            "proceeds": round(proceeds, 2),
            "method": method,
            "profit_pct": round(((price - state["avg_price"]) / state["avg_price"]) * 100, 2) if state["avg_price"] > 0 else 0,
        })

        save_state(state)
        return state

    def reset_state(self, ticker: str):
        """종목의 시뮬레이션 상태를 리셋합니다."""
        state = load_state(ticker)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reset_state = {
            "ticker": ticker,
            "current_round": 0,
            "total_invested": 0.0,
            "total_shares": 0.0,
            "avg_price": 0.0,
            "history": [],
            "status": "waiting",
            "created_at": now,
            "updated_at": now,
        }
        save_state(reset_state)
        return reset_state

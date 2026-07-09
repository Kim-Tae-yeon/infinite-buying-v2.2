"""
main.py — 무한매수법 V2.2 시스템 메인 오케스트레이터

GitHub Actions에서 호출되어:
1. 주가 데이터 수집
2. V2.2 알고리즘 기반 매수/매도 추천 계산
3. 차트 생성
4. README.md 동적 업데이트
"""

import json
import os
import sys
import argparse
from datetime import datetime
import pytz

from data_fetcher import get_ticker_summary, get_market_status
from algorithm import InfiniteBuyV22, load_state
from chart_generator import generate_all_charts

# 프로젝트 루트 경로
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config() -> dict:
    """config.json 로드"""
    config_path = os.path.join(ROOT_DIR, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_readme(config: dict, recommendations: dict, summaries: dict, chart_files: dict):
    """
    README.md를 동적으로 생성합니다.

    Args:
        config: 설정
        recommendations: {ticker: recommendation_dict}
        summaries: {ticker: summary_dict}
        chart_files: {ticker: filepath}
    """
    kst = pytz.timezone("Asia/Seoul")
    now = datetime.now(kst)
    update_time = now.strftime("%Y-%m-%d %H:%M KST")
    update_date = now.strftime("%Y-%m-%d")

    market = get_market_status()

    lines = []

    # ── 헤더 ──
    lines.append("# 📈 무한매수법 V2.2 자동 추천 시스템")
    lines.append("")
    lines.append("> 라오어 무한매수법 V2.2 알고리즘 기반 매일 자동 매수/매도 추천")
    lines.append("> ")
    lines.append("> ⚠️ **투자 참고용이며, 투자의 책임은 본인에게 있습니다.**")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 시장 상태 ──
    market_emoji = "🟢" if market["is_open"] else "🔴"
    lines.append(f"## {market_emoji} 시장 상태")
    lines.append("")
    lines.append(f"| 항목 | 상태 |")
    lines.append(f"|------|------|")
    lines.append(f"| 미국 시장 | {market_emoji} {'개장중' if market['is_open'] else '폐장'} |")
    lines.append(f"| 현재 시간 (ET) | {market['current_time_et']} |")
    lines.append(f"| 요일 | {market['weekday']}요일 |")
    lines.append(f"| 마지막 갱신 | {update_time} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 종목별 추천 ──
    lines.append("## 🎯 오늘의 매수/매도 추천")
    lines.append("")
    lines.append(f"> 📅 **{update_date}** 기준 추천 내역")
    lines.append("")

    for ticker in config["tickers"]:
        rec = recommendations.get(ticker, {})
        summary = summaries.get(ticker, {})
        state = load_state(ticker)

        lines.append(f"### 💹 {ticker}")
        lines.append("")

        # 현재 가격 요약
        if summary:
            change_emoji = "📈" if summary.get("change_pct", 0) >= 0 else "📉"
            change_sign = "+" if summary.get("change_pct", 0) >= 0 else ""
            lines.append(f"**현재가:** ${summary.get('current_price', 'N/A')} "
                         f"{change_emoji} {change_sign}{summary.get('change_pct', 0):.1f}% | "
                         f"**RSI:** {summary.get('rsi_14', 'N/A')} | "
                         f"**거래량:** {summary.get('volume', 0):,}")
            lines.append("")

        # 시뮬레이션 상태
        lines.append(f"#### 📊 시뮬레이션 상태")
        lines.append("")
        lines.append(f"| 항목 | 값 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 현재 회차 | {state['current_round']} / {config['total_rounds']} |")
        lines.append(f"| 평단가 | ${state['avg_price']:.2f} |")
        lines.append(f"| 보유 수량 | {state['total_shares']:.4f}주 |")
        lines.append(f"| 총 투자액 | ${state['total_invested']:.2f} |")
        lines.append(f"| 잔여 시드 | ${config['seed_money_per_ticker'] - state['total_invested']:.2f} |")
        lines.append(f"| 상태 | {_status_emoji(state['status'])} {state['status']} |")
        lines.append("")

        # T값 진행 바
        t_value = state['current_round']
        t_bar = _progress_bar(t_value, config['total_rounds'])
        lines.append(f"**T값 진행:** {t_bar} `T={t_value}`")
        lines.append("")

        # 추천 요약
        if rec.get("summary"):
            lines.append(f"#### 💡 추천 요약")
            lines.append("")
            lines.append(f"> {rec['summary']}")
            lines.append("")

        # 매수 주문
        if rec.get("actions"):
            lines.append(f"#### 🛒 매수 주문")
            lines.append("")
            lines.append(f"| 방식 | 주문가 | 금액 | 예상 수량 | 비고 |")
            lines.append(f"|------|--------|------|-----------|------|")
            for action in rec["actions"]:
                if action["type"] == "WAIT":
                    lines.append(f"| ⏸️ {action['method']} | - | - | - | {action.get('note', '')} |")
                else:
                    lines.append(
                        f"| {'🟢' if action['type'] == 'BUY' else '🔴'} {action['method']} | "
                        f"${action.get('price', 'N/A')} | "
                        f"${action.get('budget', 'N/A')} | "
                        f"{action.get('estimated_shares', 'N/A')}주 | "
                        f"{action.get('note', '')} |"
                    )
            lines.append("")

        # 매도 주문
        if rec.get("sell_orders"):
            lines.append(f"#### 💰 매도 주문")
            lines.append("")
            lines.append(f"| 방식 | 지정가 | 수량 | 비고 |")
            lines.append(f"|------|--------|------|------|")
            for sell in rec["sell_orders"]:
                lines.append(
                    f"| 📤 {sell['method']} | ${sell['price']} | {sell['shares']}주 | {sell.get('note', '')} |"
                )
            lines.append("")

        # 차트 이미지
        chart_file = chart_files.get(ticker)
        if chart_file:
            rel_path = os.path.relpath(chart_file, ROOT_DIR).replace("\\", "/")
            lines.append(f"#### 📉 차트")
            lines.append("")
            lines.append(f"![{ticker} Chart]({rel_path})")
            lines.append("")

        lines.append("---")
        lines.append("")

    # ── 무한매수법 V2.2 규칙 요약 ──
    lines.append("## 📖 무한매수법 V2.2 규칙 요약")
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>📋 클릭하여 규칙 확인</summary>")
    lines.append("")
    lines.append("### 매수 규칙")
    lines.append("- **원금 40분할**: 총 시드머니를 40회차로 나누어 운용")
    lines.append("- **1회차**: 장중 시장가 매수 (RSI < 60 시 진입 권장)")
    lines.append("- **2~19회차**: LOC 평단매수(50%) + LOC 큰수매수(50%)")
    lines.append("  - 평단매수: 현재 평단가로 LOC 주문")
    lines.append("  - 큰수매수: 현재가+10~15% (단, 평단+5% 초과 금지)")
    lines.append("- **20~40회차**: 평단가 이하에서만 매수 (큰수매수 중단)")
    lines.append("")
    lines.append("### 매도 규칙")
    lines.append("- **1~19회차**: 보유 전량 → 평단가+10% 지정가 매도")
    lines.append("- **20~40회차**: 절반 → 평단가+5%, 나머지 → 평단가+10% 분할 매도")
    lines.append("")
    lines.append("### 쿼터 손절")
    lines.append("- **40회차 소진 시**: 보유 물량의 1/4 시장가 매도로 시드 재확보")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    # ── 푸터 ──
    lines.append("---")
    lines.append("")
    lines.append(f"🤖 *자동 생성됨 | {update_time} | GitHub Actions*")
    lines.append("")
    lines.append("⚠️ **면책 조항**: 본 시스템은 교육/참고 목적이며, 실제 투자 손익에 대한 책임은 사용자에게 있습니다.")
    lines.append("")

    # README 파일 작성
    readme_path = os.path.join(ROOT_DIR, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ README.md 업데이트 완료: {readme_path}")
    return readme_path


def _status_emoji(status: str) -> str:
    """상태에 따른 이모지"""
    return {
        "waiting": "⏳",
        "active": "🔄",
        "completed": "✅",
        "stopped": "🛑",
    }.get(status, "❓")


def _progress_bar(current: int, total: int, length: int = 20) -> str:
    """텍스트 프로그레스 바 생성"""
    filled = int(length * current / total)
    bar = "█" * filled + "░" * (length - filled)
    pct = (current / total) * 100
    return f"`[{bar}]` {pct:.0f}%"


def run_chart_update(config: dict):
    """매시간 차트 갱신 작업"""
    print("=" * 60)
    print("📊 차트 갱신 시작...")
    print("=" * 60)

    tickers = config["tickers"]

    # 종목별 상태 로드
    states = {}
    for ticker in tickers:
        states[ticker] = load_state(ticker)

    # 차트 생성
    chart_files = generate_all_charts(tickers, states)

    print("\n✅ 차트 갱신 완료!")
    return chart_files


def run_daily_recommendation(config: dict):
    """매일 추천 리포트 생성 작업"""
    print("=" * 60)
    print("🎯 일일 추천 리포트 생성 시작...")
    print("=" * 60)

    engine = InfiniteBuyV22(config)
    tickers = config["tickers"]
    recommendations = {}
    summaries = {}

    for ticker in tickers:
        print(f"\n── {ticker} ──")
        try:
            # 종목 요약 가져오기
            summary = get_ticker_summary(ticker)
            summaries[ticker] = summary
            print(f"  현재가: ${summary['current_price']} | RSI: {summary['rsi_14']} | 변동: {summary['change_pct']:+.1f}%")

            # 추천 계산
            rec = engine.get_recommendation(
                ticker=ticker,
                current_price=summary["current_price"],
                rsi=summary["rsi_14"],
            )
            recommendations[ticker] = rec
            print(f"  추천: {rec['summary']}")

        except Exception as e:
            print(f"  ❌ {ticker} 처리 실패: {e}")
            recommendations[ticker] = {"summary": f"❌ 오류: {e}", "actions": [], "sell_orders": []}
            summaries[ticker] = {}

    # 차트 생성
    states = {t: load_state(t) for t in tickers}
    chart_files = generate_all_charts(tickers, states)

    # README 생성
    generate_readme(config, recommendations, summaries, chart_files)

    print("\n" + "=" * 60)
    print("✅ 일일 추천 리포트 생성 완료!")
    print("=" * 60)

    return recommendations


def run_simulate_buy(config: dict, ticker: str, price: float = None):
    """
    수동 매수 시뮬레이션: 현재 가격으로 1회차 매수를 기록합니다.
    """
    engine = InfiniteBuyV22(config)

    if price is None:
        summary = get_ticker_summary(ticker)
        price = summary["current_price"]

    budget = engine.round_budget
    shares = budget / price

    state = engine.simulate_buy(ticker, price, shares, method="시뮬레이션 매수")
    print(f"✅ {ticker} 매수 시뮬레이션 완료:")
    print(f"   회차: {state['current_round']} | 체결가: ${price:.2f} | "
          f"수량: {shares:.4f}주 | 평단가: ${state['avg_price']:.2f}")
    return state


def main():
    parser = argparse.ArgumentParser(description="무한매수법 V2.2 자동 추천 시스템")
    parser.add_argument("--mode", choices=["chart", "recommend", "full", "simulate-buy", "reset"],
                        default="full", help="실행 모드")
    parser.add_argument("--ticker", type=str, help="종목 코드 (simulate-buy, reset 모드에서 사용)")
    parser.add_argument("--price", type=float, help="시뮬레이션 매수 가격 (없으면 현재가 사용)")
    parser.add_argument("--dry-run", action="store_true", help="테스트 모드 (실제 파일 수정 없음)")

    args = parser.parse_args()
    config = load_config()

    if args.dry_run:
        print("🧪 DRY-RUN 모드: 데이터 수집 및 계산만 수행합니다.")

    if args.mode == "chart":
        run_chart_update(config)

    elif args.mode == "recommend":
        run_daily_recommendation(config)

    elif args.mode == "full":
        run_daily_recommendation(config)

    elif args.mode == "simulate-buy":
        if not args.ticker:
            print("❌ --ticker 옵션이 필요합니다.")
            sys.exit(1)
        run_simulate_buy(config, args.ticker, args.price)

    elif args.mode == "reset":
        if not args.ticker:
            print("❌ --ticker 옵션이 필요합니다.")
            sys.exit(1)
        engine = InfiniteBuyV22(config)
        engine.reset_state(args.ticker)
        print(f"✅ {args.ticker} 상태 리셋 완료!")

    print("\n🏁 작업 완료!")


if __name__ == "__main__":
    main()

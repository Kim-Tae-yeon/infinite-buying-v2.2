"""
chart_generator.py — 주가 차트 이미지 생성 모듈

매시간/매일 갱신되는 캔들차트를 생성하여 charts/ 디렉토리에 저장합니다.
"""

import os
import matplotlib
matplotlib.use("Agg")  # GUI 없는 환경용

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

from data_fetcher import fetch_daily_data, calculate_rsi, calculate_moving_averages

# 차트 저장 디렉토리
CHART_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "charts")


def _ensure_chart_dir():
    os.makedirs(CHART_DIR, exist_ok=True)


def _setup_dark_style():
    """다크 테마 스타일 설정"""
    plt.rcParams.update({
        "figure.facecolor": "#0d1117",
        "axes.facecolor": "#161b22",
        "axes.edgecolor": "#30363d",
        "axes.labelcolor": "#c9d1d9",
        "text.color": "#c9d1d9",
        "xtick.color": "#8b949e",
        "ytick.color": "#8b949e",
        "grid.color": "#21262d",
        "grid.alpha": 0.6,
        "figure.dpi": 150,
        "font.size": 10,
        "font.family": "DejaVu Sans",
    })


def generate_candlestick_chart(ticker: str, avg_price: float = None, sell_prices: list = None) -> str:
    """
    종목의 캔들차트 + 이동평균 + RSI + 거래량 차트를 생성합니다.

    Args:
        ticker: 종목 코드
        avg_price: 현재 평단가 (표시용, 없으면 생략)
        sell_prices: 매도 가격 목록 (표시용)

    Returns:
        생성된 차트 파일 경로
    """
    _ensure_chart_dir()
    _setup_dark_style()

    # 데이터 가져오기
    df = fetch_daily_data(ticker, period="3mo")
    df = calculate_moving_averages(df)
    rsi = calculate_rsi(df)

    # 최근 60거래일만 표시
    df = df.tail(60).copy()
    rsi = rsi.tail(60).copy()

    # ── 4-패널 차트: 캔들 + MA | 거래량 | RSI ──
    fig, (ax_price, ax_vol, ax_rsi) = plt.subplots(
        3, 1,
        figsize=(14, 10),
        gridspec_kw={"height_ratios": [5, 1.5, 2]},
        sharex=True,
    )
    fig.subplots_adjust(hspace=0.05)

    dates = df.index
    opens = df["Open"].values
    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values
    volumes = df["Volume"].values

    # ── 1) 캔들차트 ──
    colors_candle = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(opens, closes)]
    colors_wick = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(opens, closes)]

    # 캔들 바디
    bar_width = 0.6
    for i, (date, o, h, l, c) in enumerate(zip(dates, opens, highs, lows, closes)):
        color = colors_candle[i]
        # 심지
        ax_price.plot([date, date], [l, h], color=colors_wick[i], linewidth=0.8)
        # 바디
        body_low = min(o, c)
        body_high = max(o, c)
        body_height = body_high - body_low
        if body_height < 0.01:
            body_height = 0.01
        ax_price.bar(date, body_height, bottom=body_low, width=bar_width,
                     color=color, edgecolor=color, linewidth=0.5)

    # 이동평균선
    if "MA5" in df.columns:
        ax_price.plot(dates, df["MA5"].values, color="#ff9800", linewidth=1.2, label="MA5", alpha=0.9)
    if "MA20" in df.columns:
        ax_price.plot(dates, df["MA20"].values, color="#2196f3", linewidth=1.2, label="MA20", alpha=0.9)
    if "MA60" in df.columns:
        valid_ma60 = df["MA60"].dropna()
        if not valid_ma60.empty:
            ax_price.plot(valid_ma60.index, valid_ma60.values, color="#9c27b0", linewidth=1.2, label="MA60", alpha=0.9)

    # 평단가 수평선
    if avg_price and avg_price > 0:
        ax_price.axhline(y=avg_price, color="#ffd54f", linestyle="--", linewidth=1.5, alpha=0.8)
        ax_price.text(dates[-1], avg_price, f"  평단 ${avg_price:.2f}",
                      color="#ffd54f", fontsize=9, va="center", fontweight="bold")

    # 매도 가격 수평선
    if sell_prices:
        sell_colors = ["#00e676", "#69f0ae"]
        for i, sp in enumerate(sell_prices):
            c = sell_colors[i % len(sell_colors)]
            ax_price.axhline(y=sp, color=c, linestyle=":", linewidth=1.2, alpha=0.7)
            ax_price.text(dates[-1], sp, f"  매도 ${sp:.2f}",
                          color=c, fontsize=8, va="center")

    ax_price.set_ylabel("Price ($)", fontsize=11)
    ax_price.legend(loc="upper left", fontsize=9, framealpha=0.3)
    ax_price.grid(True, alpha=0.3)

    # 타이틀
    current_close = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else current_close
    change = current_close - prev_close
    change_pct = (change / prev_close) * 100
    change_color = "#26a69a" if change >= 0 else "#ef5350"
    change_sign = "+" if change >= 0 else ""

    title_text = f"{ticker}  ${current_close:.2f}  {change_sign}{change:.2f} ({change_sign}{change_pct:.1f}%)"
    ax_price.set_title(title_text, fontsize=14, fontweight="bold", color=change_color, pad=15)

    # ── 2) 거래량 ──
    vol_colors = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(opens, closes)]
    ax_vol.bar(dates, volumes, color=vol_colors, alpha=0.6, width=bar_width)
    ax_vol.set_ylabel("Vol", fontsize=9)
    ax_vol.grid(True, alpha=0.2)
    ax_vol.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:.0f}M" if x >= 1e6 else f"{x/1e3:.0f}K"))

    # ── 3) RSI ──
    valid_rsi = rsi.dropna()
    if not valid_rsi.empty:
        ax_rsi.plot(valid_rsi.index, valid_rsi.values, color="#ab47bc", linewidth=1.5)
        ax_rsi.fill_between(valid_rsi.index, valid_rsi.values, 50,
                            where=(valid_rsi.values >= 50), color="#26a69a", alpha=0.15)
        ax_rsi.fill_between(valid_rsi.index, valid_rsi.values, 50,
                            where=(valid_rsi.values < 50), color="#ef5350", alpha=0.15)

    ax_rsi.axhline(70, color="#ef5350", linestyle="--", linewidth=0.8, alpha=0.5)
    ax_rsi.axhline(30, color="#26a69a", linestyle="--", linewidth=0.8, alpha=0.5)
    ax_rsi.axhline(60, color="#ffd54f", linestyle=":", linewidth=0.8, alpha=0.4)
    ax_rsi.set_ylabel("RSI", fontsize=9)
    ax_rsi.set_ylim(0, 100)
    ax_rsi.grid(True, alpha=0.2)

    # RSI 값 표시
    if not valid_rsi.empty:
        last_rsi = valid_rsi.iloc[-1]
        rsi_color = "#ef5350" if last_rsi >= 70 else "#26a69a" if last_rsi <= 30 else "#ab47bc"
        ax_rsi.text(valid_rsi.index[-1], last_rsi, f"  {last_rsi:.1f}",
                    color=rsi_color, fontsize=10, fontweight="bold", va="center")

    # X축 날짜 포맷
    ax_rsi.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax_rsi.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    plt.xticks(rotation=45, fontsize=8)

    # 갱신 시간 표시
    kst = pytz.timezone("Asia/Seoul")
    update_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")
    fig.text(0.99, 0.01, f"Updated: {update_time}", fontsize=7, color="#8b949e",
             ha="right", va="bottom", style="italic")

    # 저장
    filepath = os.path.join(CHART_DIR, f"chart_{ticker}.png")
    fig.savefig(filepath, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)

    return filepath


def generate_all_charts(tickers: list, states: dict = None) -> dict:
    """
    모든 종목의 차트를 생성합니다.

    Args:
        tickers: 종목 코드 리스트
        states: {ticker: state_dict} 종목별 상태 (평단가/매도가 표시용)

    Returns:
        {ticker: filepath} 딕셔너리
    """
    results = {}
    for ticker in tickers:
        avg_price = None
        sell_prices = None

        if states and ticker in states:
            st = states[ticker]
            avg_price = st.get("avg_price", 0)
            # 매도가 계산 (간이)
            if avg_price and avg_price > 0:
                sell_prices = [
                    round(avg_price * 1.05, 2),
                    round(avg_price * 1.10, 2),
                ]

        try:
            filepath = generate_candlestick_chart(ticker, avg_price, sell_prices)
            results[ticker] = filepath
            print(f"  ✅ {ticker} 차트 생성: {filepath}")
        except Exception as e:
            print(f"  ❌ {ticker} 차트 생성 실패: {e}")
            results[ticker] = None

    return results

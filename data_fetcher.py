"""
data_fetcher.py — 주가 데이터 수집 및 기술 지표 계산 모듈

yfinance를 활용하여 타겟 ETF의 가격 데이터를 가져오고,
RSI 등 무한매수법에 필요한 기술 지표를 계산합니다.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz


def fetch_daily_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """
    일봉 데이터를 가져옵니다.

    Args:
        ticker: 종목 코드 (예: 'TQQQ')
        period: 데이터 기간 (예: '6mo', '1y')

    Returns:
        OHLCV DataFrame
    """
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval="1d")
    if df.empty:
        raise ValueError(f"[ERROR] {ticker}: 데이터를 가져올 수 없습니다.")
    return df


def fetch_intraday_data(ticker: str, period: str = "5d", interval: str = "1h") -> pd.DataFrame:
    """
    시간봉 데이터를 가져옵니다 (차트용).

    Args:
        ticker: 종목 코드
        period: 데이터 기간
        interval: 봉 간격 (예: '1h', '15m')

    Returns:
        OHLCV DataFrame
    """
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"[ERROR] {ticker}: 시간봉 데이터를 가져올 수 없습니다.")
    return df


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    RSI (Relative Strength Index) 계산.

    Args:
        df: OHLCV DataFrame
        period: RSI 기간 (기본 14일)

    Returns:
        RSI Series
    """
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Wilder's smoothing for subsequent values
    for i in range(period, len(avg_gain)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    이동평균선 계산 (5일, 20일, 60일).

    Args:
        df: OHLCV DataFrame

    Returns:
        MA 컬럼이 추가된 DataFrame
    """
    df = df.copy()
    df["MA5"] = df["Close"].rolling(window=5).mean()
    df["MA20"] = df["Close"].rolling(window=20).mean()
    df["MA60"] = df["Close"].rolling(window=60).mean()
    return df


def get_current_price(ticker: str) -> float:
    """
    현재가 (또는 최근 종가)를 가져옵니다.

    Args:
        ticker: 종목 코드

    Returns:
        현재 가격 (float)
    """
    stock = yf.Ticker(ticker)
    info = stock.fast_info
    return float(info.get("lastPrice", info.get("previousClose", 0)))


def get_market_status() -> dict:
    """
    미국 시장 개장 여부를 확인합니다.

    Returns:
        {'is_open': bool, 'next_open': str, 'next_close': str}
    """
    eastern = pytz.timezone("US/Eastern")
    now = datetime.now(eastern)
    weekday = now.weekday()  # 0=월, 6=일

    # 기본 개장 시간: 9:30 ~ 16:00 ET
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

    is_open = (weekday < 5) and (market_open <= now <= market_close)

    return {
        "is_open": is_open,
        "current_time_et": now.strftime("%Y-%m-%d %H:%M:%S ET"),
        "weekday": ["월", "화", "수", "목", "금", "토", "일"][weekday],
    }


def get_ticker_summary(ticker: str) -> dict:
    """
    종목의 전체 요약 정보를 반환합니다.

    Args:
        ticker: 종목 코드

    Returns:
        요약 딕셔너리
    """
    df = fetch_daily_data(ticker, period="3mo")
    rsi = calculate_rsi(df)
    df = calculate_moving_averages(df)

    current_price = df["Close"].iloc[-1]
    prev_close = df["Close"].iloc[-2] if len(df) >= 2 else current_price
    change_pct = ((current_price - prev_close) / prev_close) * 100

    return {
        "ticker": ticker,
        "current_price": round(float(current_price), 2),
        "prev_close": round(float(prev_close), 2),
        "change_pct": round(float(change_pct), 2),
        "rsi_14": round(float(rsi.iloc[-1]), 2) if not pd.isna(rsi.iloc[-1]) else None,
        "ma5": round(float(df["MA5"].iloc[-1]), 2) if not pd.isna(df["MA5"].iloc[-1]) else None,
        "ma20": round(float(df["MA20"].iloc[-1]), 2) if not pd.isna(df["MA20"].iloc[-1]) else None,
        "ma60": round(float(df["MA60"].iloc[-1]), 2) if not pd.isna(df["MA60"].iloc[-1]) else None,
        "high_52w": round(float(df["Close"].max()), 2),
        "low_52w": round(float(df["Close"].min()), 2),
        "volume": int(df["Volume"].iloc[-1]),
        "data_date": df.index[-1].strftime("%Y-%m-%d"),
    }

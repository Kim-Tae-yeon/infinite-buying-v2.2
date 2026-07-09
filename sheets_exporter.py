"""
sheets_exporter.py — Google Sheets 자동 연동 모듈

무한매수법 V2.2 시뮬레이션 데이터를 Google 스프레드시트에
자동으로 동기화합니다. 스크린샷처럼 한눈에 볼 수 있는 대시보드를 구성합니다.
"""

import json
import os
import csv
from datetime import datetime
from typing import Optional

import pytz

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

from data_fetcher import get_ticker_summary, get_market_status
from algorithm import InfiniteBuyV22, load_state

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(ROOT_DIR, "reports")

# Google Sheets API 범위
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _ensure_csv_dir():
    os.makedirs(CSV_DIR, exist_ok=True)


def _get_signal_text(rsi: float, price: float, avg_price: float, current_round: int) -> str:
    """신호 텍스트 생성"""
    if current_round == 0:
        if rsi and rsi < 60:
            return "🟢 진입"
        else:
            return "🟡 대기"
    elif price < avg_price * 0.95:
        return "🔴 급락"
    elif price < avg_price:
        return "🟢 매수적기"
    elif price > avg_price * 1.10:
        return "💰 매도구간"
    elif price > avg_price * 1.05:
        return "🟡 매도근접"
    else:
        return "⏸️ 보유"


def _get_phase_text(current_round: int, late_start: int = 20) -> str:
    """현재 페이즈"""
    if current_round == 0:
        return "대기"
    elif current_round < late_start:
        return f"초기({current_round}R)"
    elif current_round <= 40:
        return f"후기({current_round}R)"
    else:
        return "소진"


def build_dashboard_data(config: dict) -> list[dict]:
    """
    스프레드시트 대시보드용 데이터를 생성합니다.

    Returns:
        각 종목의 데이터 딕셔너리 리스트
    """
    engine = InfiniteBuyV22(config)
    tickers = config["tickers"]
    rows = []

    for ticker in tickers:
        try:
            summary = get_ticker_summary(ticker)
            state = load_state(ticker)
            rec = engine.get_recommendation(
                ticker=ticker,
                current_price=summary["current_price"],
                rsi=summary.get("rsi_14"),
            )

            current_price = summary["current_price"]
            avg_price = state["avg_price"]
            total_shares = state["total_shares"]
            total_invested = state["total_invested"]
            current_round = state["current_round"]
            rsi = summary.get("rsi_14", 0)

            # 수익률 계산
            if avg_price > 0 and total_shares > 0:
                current_value = current_price * total_shares
                pnl_pct = ((current_price - avg_price) / avg_price) * 100
                pnl_dollar = current_value - total_invested
            else:
                current_value = 0
                pnl_pct = 0
                pnl_dollar = 0

            # LOC 매수가 계산
            loc_avg_price = avg_price if avg_price > 0 else current_price
            loc_big_price = min(
                current_price * 1.10,
                avg_price * 1.05 if avg_price > 0 else current_price * 1.10
            )

            # 매도 목표가
            if current_round < 20:
                sell_target_1 = avg_price * 1.10 if avg_price > 0 else 0
                sell_target_2 = 0
            else:
                sell_target_1 = avg_price * 1.05 if avg_price > 0 else 0
                sell_target_2 = avg_price * 1.10 if avg_price > 0 else 0

            # 신호
            signal = _get_signal_text(rsi, current_price, avg_price, current_round)
            phase = _get_phase_text(current_round)

            row = {
                "종목코드": ticker,
                "신호": signal,
                "페이즈": phase,
                "현재가($)": round(current_price, 2),
                "전일대비%": round(summary.get("change_pct", 0), 2),
                "평단가($)": round(avg_price, 2),
                "LOC평단매수($)": round(loc_avg_price, 2),
                "LOC큰수매수($)": round(loc_big_price, 2) if current_round < 20 else "-",
                "매도목표1($)": round(sell_target_1, 2) if sell_target_1 > 0 else "-",
                "매도목표2($)": round(sell_target_2, 2) if sell_target_2 > 0 else "-",
                "보유수량": round(total_shares, 4),
                "총투자액($)": round(total_invested, 2),
                "평가액($)": round(current_value, 2),
                "수익률%": round(pnl_pct, 2),
                "수익금($)": round(pnl_dollar, 2),
                "T값": f"{current_round}/40",
                "잔여시드($)": round(config["seed_money_per_ticker"] - total_invested, 2),
                "RSI": round(rsi, 1) if rsi else "-",
                "MA5($)": summary.get("ma5", "-"),
                "MA20($)": summary.get("ma20", "-"),
                "거래량": f"{summary.get('volume', 0):,}",
                "추천요약": rec.get("summary", ""),
                "데이터일자": summary.get("data_date", ""),
            }
            rows.append(row)

        except Exception as e:
            rows.append({
                "종목코드": ticker,
                "신호": "❌ 오류",
                "페이즈": "-",
                "현재가($)": f"오류: {e}",
                "전일대비%": "-",
                "평단가($)": "-",
                "LOC평단매수($)": "-",
                "LOC큰수매수($)": "-",
                "매도목표1($)": "-",
                "매도목표2($)": "-",
                "보유수량": "-",
                "총투자액($)": "-",
                "평가액($)": "-",
                "수익률%": "-",
                "수익금($)": "-",
                "T값": "-",
                "잔여시드($)": "-",
                "RSI": "-",
                "MA5($)": "-",
                "MA20($)": "-",
                "거래량": "-",
                "추천요약": str(e),
                "데이터일자": "-",
            })

    return rows


def export_to_csv(config: dict) -> str:
    """
    대시보드 데이터를 CSV로 내보냅니다.

    Returns:
        생성된 CSV 파일 경로
    """
    _ensure_csv_dir()
    rows = build_dashboard_data(config)

    if not rows:
        print("  ⚠️ 내보낼 데이터가 없습니다.")
        return ""

    kst = pytz.timezone("Asia/Seoul")
    timestamp = datetime.now(kst).strftime("%Y%m%d_%H%M")

    # 최신 파일 (고정 이름)
    latest_path = os.path.join(CSV_DIR, "dashboard_latest.csv")

    headers = list(rows[0].keys())

    with open(latest_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  ✅ CSV 내보내기 완료: {latest_path}")
    return latest_path


def export_to_google_sheets(config: dict, creds_json: Optional[str] = None, spreadsheet_id: Optional[str] = None):
    """
    대시보드 데이터를 Google Sheets에 동기화합니다.

    Args:
        config: 애플리케이션 설정
        creds_json: 서비스 계정 JSON 문자열 (환경변수에서 전달)
        spreadsheet_id: 기존 스프레드시트 ID (없으면 새로 생성)

    Returns:
        스프레드시트 URL
    """
    if not GSPREAD_AVAILABLE:
        print("  ❌ gspread 라이브러리가 설치되지 않았습니다.")
        return None

    # 인증
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        # 로컬 파일
        creds_path = os.path.join(ROOT_DIR, "credentials.json")
        if not os.path.exists(creds_path):
            print("  ❌ credentials.json 파일이 없습니다. Google Cloud 서비스 계정 키를 다운로드하세요.")
            return None
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)

    gc = gspread.authorize(creds)

    # 데이터 빌드
    rows = build_dashboard_data(config)
    if not rows:
        print("  ⚠️ 내보낼 데이터가 없습니다.")
        return None

    headers = list(rows[0].keys())
    values = [headers] + [[str(row.get(h, "")) for h in headers] for row in rows]

    kst = pytz.timezone("Asia/Seoul")
    update_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")

    # 스프레드시트 열기 또는 생성
    if spreadsheet_id:
        sh = gc.open_by_key(spreadsheet_id)
    else:
        sh = gc.create("무한매수법 V2.2 대시보드")
        # 공개 읽기 권한 부여
        sh.share("", perm_type="anyone", role="reader")
        print(f"  📊 새 스프레드시트 생성됨: {sh.url}")

    # ── 1) 대시보드 시트 업데이트 ──
    try:
        ws_dashboard = sh.worksheet("📊 대시보드")
    except gspread.WorksheetNotFound:
        ws_dashboard = sh.add_worksheet(title="📊 대시보드", rows=50, cols=25)

    ws_dashboard.clear()

    # 타이틀 행
    title_row = [f"무한매수법 V2.2 — 업데이트: {update_time}"]
    ws_dashboard.update("A1", [title_row])

    # 데이터
    ws_dashboard.update("A3", values)

    # ── 서식 적용 ──
    _apply_formatting(ws_dashboard, len(values))

    # ── 2) 매수/매도 이력 시트 ──
    _update_history_sheet(sh, config)

    print(f"  ✅ Google Sheets 동기화 완료: {sh.url}")
    return sh.url


def _apply_formatting(ws, data_rows: int):
    """Google Sheets 서식 적용 (색상, 조건부 서식 등)"""
    try:
        # 헤더 행 굵게
        ws.format("A3:V3", {
            "backgroundColor": {"red": 0.15, "green": 0.15, "blue": 0.2},
            "textFormat": {"bold": True, "foregroundColor": {"red": 0.9, "green": 0.85, "blue": 0.6}},
            "horizontalAlignment": "CENTER",
        })

        # 타이틀 굵게 + 크게
        ws.format("A1", {
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": {"red": 0.3, "green": 0.8, "blue": 0.5}},
        })

        # 수익률% 열 조건부 서식은 gspread batch_update로 처리 가능하나 복잡하므로 생략
        # 대신 데이터 행 전체에 기본 스타일 적용
        if data_rows > 1:
            end_row = data_rows + 3
            ws.format(f"A4:V{end_row}", {
                "backgroundColor": {"red": 0.1, "green": 0.1, "blue": 0.13},
                "textFormat": {"foregroundColor": {"red": 0.8, "green": 0.83, "blue": 0.85}},
                "horizontalAlignment": "CENTER",
            })

    except Exception as e:
        print(f"  ⚠️ 서식 적용 중 오류 (무시됨): {e}")


def _update_history_sheet(sh, config: dict):
    """매수/매도 이력 시트 업데이트"""
    try:
        ws_history = sh.worksheet("📜 매매이력")
    except gspread.WorksheetNotFound:
        ws_history = sh.add_worksheet(title="📜 매매이력", rows=500, cols=15)

    all_history = []
    for ticker in config["tickers"]:
        state = load_state(ticker)
        for entry in state.get("history", []):
            row = {
                "종목": ticker,
                "일자": entry.get("date", ""),
                "유형": entry.get("type", ""),
                "회차": entry.get("round", "-"),
                "체결가($)": entry.get("price", ""),
                "수량": entry.get("shares", ""),
                "금액($)": entry.get("cost", entry.get("proceeds", "")),
                "방식": entry.get("method", ""),
                "체결후평단($)": entry.get("avg_price_after", "-"),
            }
            all_history.append(row)

    if all_history:
        headers = list(all_history[0].keys())
        values = [headers] + [[str(row.get(h, "")) for h in headers] for row in all_history]
    else:
        values = [["종목", "일자", "유형", "회차", "체결가($)", "수량", "금액($)", "방식", "체결후평단($)"],
                  ["(아직 매매 이력이 없습니다)", "", "", "", "", "", "", "", ""]]

    ws_history.clear()
    ws_history.update("A1", values)

    try:
        ws_history.format("A1:I1", {
            "backgroundColor": {"red": 0.15, "green": 0.15, "blue": 0.2},
            "textFormat": {"bold": True, "foregroundColor": {"red": 0.9, "green": 0.85, "blue": 0.6}},
            "horizontalAlignment": "CENTER",
        })
    except Exception:
        pass


# ── 기존 시트 삭제 후 첫 시트 정리 유틸 ──
def init_spreadsheet(config: dict, creds_json: Optional[str] = None) -> str:
    """
    새 스프레드시트를 생성하고 초기 구조를 잡습니다.
    
    Returns:
        spreadsheet_id
    """
    if not GSPREAD_AVAILABLE:
        print("  ❌ gspread가 필요합니다: pip install gspread google-auth")
        return ""

    url = export_to_google_sheets(config, creds_json=creds_json)
    if url:
        # URL에서 ID 추출
        sid = url.split("/d/")[1].split("/")[0] if "/d/" in url else ""
        print(f"\n  📌 스프레드시트 ID: {sid}")
        print(f"  📌 이 ID를 config.json의 'spreadsheet_id'에 추가하세요.")
        return sid
    return ""

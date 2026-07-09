# 🔧 Google Sheets 자동 연동 설정 가이드

## 1단계: Google Cloud 서비스 계정 생성

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. **새 프로젝트** 생성 (예: `infinite-buying`)
3. **API 및 서비스 > 라이브러리** → "Google Sheets API" 검색 → **사용 설정**
4. **API 및 서비스 > 라이브러리** → "Google Drive API" 검색 → **사용 설정**
5. **API 및 서비스 > 사용자 인증 정보** → **사용자 인증 정보 만들기** → **서비스 계정**
   - 이름: `sheets-bot`
   - 역할: **편집자**
6. 생성된 서비스 계정 클릭 → **키** 탭 → **키 추가** → **JSON** 선택 → 다운로드

## 2단계: GitHub Secrets 등록

1. GitHub 저장소 → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭:
   - **Name**: `GOOGLE_SHEETS_CREDS`
   - **Value**: 다운로드한 JSON 파일의 **전체 내용**을 붙여넣기

## 3단계: 스프레드시트 생성 및 공유

### 방법 A: 자동 생성 (권장)
- GitHub Actions가 처음 실행될 때 자동으로 스프레드시트를 생성합니다.
- 생성 후 로그에서 스프레드시트 ID를 확인하세요.

### 방법 B: 수동 생성
1. [Google Sheets](https://sheets.google.com)에서 새 스프레드시트 생성
2. 서비스 계정 이메일 (예: `sheets-bot@프로젝트.iam.gserviceaccount.com`)을 **편집자**로 공유
3. URL에서 스프레드시트 ID를 복사:
   - URL: `https://docs.google.com/spreadsheets/d/여기가_스프레드시트_ID/edit`
4. GitHub Secrets에 추가:
   - **Name**: `SPREADSHEET_ID`
   - **Value**: 복사한 스프레드시트 ID

## 4단계: 확인

- GitHub Actions가 실행되면 자동으로 스프레드시트가 갱신됩니다.
- 수동 실행: 저장소 → **Actions** → **🎯 매일 추천 리포트** → **Run workflow**

## 로컬에서 테스트

```bash
# CSV만 생성 (Google 인증 없이)
python main.py --mode sheets

# Google Sheets 연동 테스트 (credentials.json이 프로젝트 루트에 있어야 함)
python main.py --mode sheets
```

## 스프레드시트 구성

### 📊 대시보드 시트
| 종목코드 | 신호 | 페이즈 | 현재가 | 전일대비% | 평단가 | LOC매수가 | 매도목표 | 보유수량 | 수익률% | T값 | RSI | ... |
|----------|------|--------|--------|-----------|--------|-----------|----------|----------|---------|-----|-----|-----|

### 📜 매매이력 시트
| 종목 | 일자 | 유형 | 회차 | 체결가 | 수량 | 금액 | 방식 | 체결후평단 |
|------|------|------|------|--------|------|------|------|-----------|

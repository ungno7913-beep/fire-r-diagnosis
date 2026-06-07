
# FIRE-R v5: 데이터 기반 건축재생 진단 프로그램

## 핵심 개념

FIRE-R v5는 노후 건축물의 화재 취약성을 공공데이터 기반으로 진단하고,
건축재생 관점의 개선 방향을 제안하는 Streamlit 기반 웹 애플리케이션입니다.

## 주요 기능

- 주소 입력 기반 검색
- 도로명주소 검색API 연동
- 건축물대장 표제부 OpenAPI 연동
- 사용승인일, 구조, 용도, 층수, 연면적 자동 조회
- 데이터 기반 자동 진단
  - 건축물 노후도
  - 구조 위험도
  - 용도 혼합 위험도
  - 층수·피난 난이도
  - 연면적 규모 위험도
- 최소 현장 확인 항목
  - 외장재
  - 전기설비 상태
  - 소화설비
  - 피난 동선
- 최종 화재 취약성 점수 산정
- 건축재생 유형 도출
- 개선 우선순위 제안
- 보고서 요약문 자동 생성

## 실행 전 인증키 설정

이 프로그램은 이용자가 인증키를 입력하지 않도록 설계되었습니다.
개발자는 `.streamlit/secrets.toml` 파일에 인증키를 넣어야 합니다.

```toml
JUSO_API_KEY = "주소검색_API_승인키"
BUILDING_API_KEY = "건축물대장_API_일반인증키"
```

주의: 실제 인증키가 들어간 `secrets.toml`은 GitHub에 올리지 마세요.

## 실행 방법

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Streamlit Cloud 배포

GitHub에는 아래 파일만 올립니다.

```text
app.py
requirements.txt
README.md
.streamlit/secrets.example.toml
```

실제 인증키는 Streamlit Cloud의 App settings > Secrets에 아래 형식으로 넣습니다.

```toml
JUSO_API_KEY = "주소검색_API_승인키"
BUILDING_API_KEY = "건축물대장_API_일반인증키"
```

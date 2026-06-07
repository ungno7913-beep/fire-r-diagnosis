
import streamlit as st
import pandas as pd
import requests
import re
from datetime import datetime

st.set_page_config(
    page_title="FIRE-R v5 데이터 기반 건축재생 진단",
    page_icon="🔥",
    layout="wide"
)

# ============================================================
# FIRE-R v5
# 주소 기반 자동조회 + 데이터 기반 화재 취약성 진단 + 건축재생 전략 도출
# ============================================================

MAX_SCORE = 100

# 데이터 기반 자동 진단 항목 점수
AUTO_SCORE_TABLE = {
    "건축물 노후도": {
        "노후도 높음": 18,
        "노후도 보통": 10,
        "노후도 낮음": 4,
        "판정 불가": 10,
    },
    "구조 위험도": {
        "높음": 18,
        "보통": 10,
        "낮음": 4,
        "판정 불가": 10,
    },
    "용도 혼합 위험도": {
        "높음": 14,
        "보통": 8,
        "낮음": 3,
        "판정 불가": 8,
    },
    "층수·피난 난이도": {
        "높음": 14,
        "보통": 8,
        "낮음": 3,
        "판정 불가": 8,
    },
    "연면적 규모 위험도": {
        "높음": 10,
        "보통": 6,
        "낮음": 2,
        "판정 불가": 6,
    },
}

# 현장 확인 항목 점수
FIELD_SCORE_TABLE = {
    "외장재": {
        "가연성 마감재": 10,
        "준불연 마감재": 6,
        "불연 마감재": 2,
        "확인 불가": 8,
    },
    "전기설비 상태": {
        "노후": 8,
        "보통": 5,
        "양호": 2,
        "확인 불가": 6,
    },
    "소화설비": {
        "없음": 8,
        "일부 있음": 5,
        "충분히 있음": 2,
    },
    "피난 동선": {
        "불명확": 8,
        "1방향 피난": 6,
        "2방향 피난": 2,
    },
}


# ============================================================
# API 키
# ============================================================

def get_api_keys():
    try:
        juso_key = st.secrets["JUSO_API_KEY"]
        building_key = st.secrets["BUILDING_API_KEY"]
        return juso_key, building_key, None
    except Exception:
        return None, None, "API 인증키 설정 파일이 없습니다. 프로그램 폴더의 .streamlit/secrets.toml 파일에 인증키를 넣어야 합니다."


# ============================================================
# 유틸 함수
# ============================================================

def pad4(value):
    value = str(value).strip()
    if value == "":
        return "0000"
    return value.zfill(4)


def safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def format_date_yyyymmdd(date_text):
    text = str(date_text or "").strip()
    if len(text) >= 8:
        return f"{text[:4]}.{text[4:6]}.{text[6:8]}"
    return "-"


def building_age(use_apr_day):
    text = str(use_apr_day or "").strip()
    try:
        year = int(text[:4])
        return datetime.now().year - year
    except Exception:
        return None


# ============================================================
# 주소검색 API
# ============================================================

def search_address_juso(confm_key, keyword):
    url = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
    params = {
        "confmKey": confm_key,
        "currentPage": "1",
        "countPerPage": "10",
        "keyword": keyword,
        "resultType": "json"
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    results = data.get("results", {})
    common = results.get("common", {})
    error_code = common.get("errorCode")

    if error_code != "0":
        error_msg = common.get("errorMessage", "주소검색 API 오류")
        raise RuntimeError(f"{error_code}: {error_msg}")

    return results.get("juso", [])


# ============================================================
# 건축물대장 API
# ============================================================

def fetch_building_title(service_key, sigungu_cd, bjdong_cd, bun, ji):
    url = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
    params = {
        "serviceKey": service_key,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "platGbCd": "0",
        "bun": pad4(bun),
        "ji": pad4(ji),
        "numOfRows": "10",
        "pageNo": "1",
        "_type": "json"
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    body = data.get("response", {}).get("body", {})
    total_count = safe_int(body.get("totalCount"), 0)

    if total_count == 0:
        return None, data

    item = body.get("items", {}).get("item", [])
    if isinstance(item, list):
        return item[0], data
    return item, data


def address_result_to_bld_params(juso_item):
    adm_cd = str(juso_item.get("admCd", "")).strip()
    sigungu_cd = adm_cd[:5]
    bjdong_cd = adm_cd[5:]

    bun = juso_item.get("lnbrMnnm", "")
    ji = juso_item.get("lnbrSlno", "")

    # 일부 결과에서 본번/부번이 비어 있으면 지번주소 끝에서 추출
    if not bun:
        jibun = juso_item.get("jibunAddr", "")
        match = re.search(r"(\d+)(?:-(\d+))?$", jibun.strip())
        if match:
            bun = match.group(1)
            ji = match.group(2) or "0"

    return {
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "bun": pad4(bun),
        "ji": pad4(ji),
        "admCd": adm_cd,
    }


# ============================================================
# 데이터 기반 진단 로직
# ============================================================

def diagnose_age(item):
    age = building_age(item.get("useAprDay"))
    if age is None:
        return "판정 불가", "사용승인일 정보가 없어 노후도를 보수적으로 판단했습니다."

    if age >= 30:
        return "노후도 높음", f"사용승인 후 약 {age}년 경과했습니다. 설비·마감·피난 체계의 노후 가능성이 높습니다."
    elif age >= 20:
        return "노후도 보통", f"사용승인 후 약 {age}년 경과했습니다. 부분적인 설비 점검과 성능 개선이 필요할 수 있습니다."
    else:
        return "노후도 낮음", f"사용승인 후 약 {age}년 경과했습니다. 전면 재생보다는 유지관리·부분 보완 중심 검토가 적합합니다."


def diagnose_structure(item):
    text = str(item.get("strctCdNm", "") or "")

    if "목" in text:
        return "높음", f"구조가 {text}로 확인되어 화재 시 구조적 취약성과 연소 확산 가능성을 우선 검토해야 합니다."
    elif "조적" in text or "벽돌" in text or "블록" in text:
        return "높음", f"구조가 {text}로 확인되어 균열, 내화성, 보강 가능성 검토가 필요합니다."
    elif "철골" in text:
        return "보통", f"구조가 {text}로 확인되어 고온 시 내력 저하에 대비한 내화피복 상태 검토가 필요합니다."
    elif "철근콘크리트" in text or "철콘" in text:
        return "낮음", f"구조가 {text}로 확인되어 상대적으로 구조 위험도는 낮게 판정했습니다."
    else:
        return "판정 불가", "구조 정보가 명확하지 않아 보수적으로 중간 수준의 위험도를 적용했습니다."


def diagnose_use_mix(item):
    main_purps = str(item.get("mainPurpsCdNm", "") or "")
    etc_purps = str(item.get("etcPurps", "") or "")
    text = f"{main_purps} {etc_purps}"

    residential = any(k in text for k in ["단독주택", "다가구", "다세대", "다중주택", "공동주택", "주택"])
    commercial = any(k in text for k in ["근린생활", "판매", "음식", "소매", "상점", "업무시설", "위락", "숙박"])
    public = any(k in text for k in ["공공", "문화", "교육", "복지", "종교"])

    if residential and commercial:
        return "높음", f"용도가 '{main_purps}'이며 기타용도에 '{etc_purps}'가 포함되어 주거와 상업 기능이 혼재된 것으로 판단됩니다."
    elif commercial:
        return "보통", f"상업·근린생활 기능이 확인되어 전기·가스 사용과 이용자 변동성을 고려해야 합니다."
    elif residential:
        return "낮음", f"주거 중심 용도로 확인되어 용도 혼합에 따른 위험은 낮게 판단했습니다."
    elif public:
        return "보통", f"공공·교육·문화 기능이 확인되어 이용자 밀도와 피난 계획 검토가 필요합니다."
    else:
        return "판정 불가", "용도 정보가 명확하지 않아 보수적으로 중간 수준의 위험도를 적용했습니다."


def diagnose_floor(item):
    floors = safe_int(item.get("grndFlrCnt"), 0)

    if floors >= 6:
        return "높음", f"지상 {floors}층 건축물로 확인되어 수직 피난, 계단실, 방화문, 비상조명 검토가 중요합니다."
    elif floors >= 4:
        return "보통", f"지상 {floors}층 건축물로 확인되어 피난 동선과 계단실 상태를 확인해야 합니다."
    elif floors >= 1:
        return "낮음", f"지상 {floors}층 건축물로 확인되어 층수에 따른 피난 난이도는 비교적 낮습니다."
    else:
        return "판정 불가", "층수 정보가 명확하지 않아 보수적으로 중간 수준의 위험도를 적용했습니다."


def diagnose_area(item):
    total_area = safe_float(item.get("totArea"), 0.0)

    if total_area >= 5000:
        return "높음", f"연면적이 약 {total_area:,.1f}㎡로 규모가 커서 피난 관리와 소방설비 점검 범위가 넓습니다."
    elif total_area >= 1000:
        return "보통", f"연면적이 약 {total_area:,.1f}㎡로 중간 규모의 건축물입니다. 공용부와 계단실 관리가 중요합니다."
    elif total_area > 0:
        return "낮음", f"연면적이 약 {total_area:,.1f}㎡로 규모에 따른 위험도는 낮게 판단했습니다."
    else:
        return "판정 불가", "연면적 정보가 명확하지 않아 보수적으로 중간 수준의 위험도를 적용했습니다."


def make_auto_diagnosis(item):
    diagnosis = {
        "건축물 노후도": diagnose_age(item),
        "구조 위험도": diagnose_structure(item),
        "용도 혼합 위험도": diagnose_use_mix(item),
        "층수·피난 난이도": diagnose_floor(item),
        "연면적 규모 위험도": diagnose_area(item),
    }

    rows = []
    total = 0

    for key, (level, reason) in diagnosis.items():
        score = AUTO_SCORE_TABLE[key][level]
        total += score
        rows.append({
            "진단 항목": key,
            "자동 판정": level,
            "점수": score,
            "판정 근거": reason,
        })

    return rows, total


def get_grade(total_score):
    if total_score <= 30:
        return "A등급", "화재 취약성 낮음", "정기 점검 중심"
    elif total_score <= 55:
        return "B등급", "부분 개선 필요", "부분 보완형 재생"
    elif total_score <= 75:
        return "C등급", "화재 취약성 높음", "안전 보강형 재생"
    else:
        return "D등급", "재생 우선 검토 필요", "집중 개선형 재생"


def get_grade_color(total_score):
    if total_score <= 30:
        return "#2E7D32"
    elif total_score <= 55:
        return "#F9A825"
    elif total_score <= 75:
        return "#EF6C00"
    return "#C62828"


def determine_regeneration_type(auto_rows, field_inputs):
    high_items = [r["진단 항목"] for r in auto_rows if r["자동 판정"] in ["높음", "노후도 높음"]]

    # 현장 입력 기반 조건
    exterior_risk = field_inputs.get("외장재") in ["가연성 마감재", "확인 불가"]
    electric_risk = field_inputs.get("전기설비 상태") in ["노후", "확인 불가"]
    fire_equipment_risk = field_inputs.get("소화설비") in ["없음", "일부 있음"]
    evacuation_risk = field_inputs.get("피난 동선") in ["불명확", "1방향 피난"]

    if "구조 위험도" in high_items or "건축물 노후도" in high_items:
        return "구조·설비 보강형 재생", "노후도 또는 구조 위험이 크게 나타나므로 철거보다 우선적으로 구조 안전성, 전기설비, 내화성능을 점검하고 보강하는 전략이 적합합니다."

    if "용도 혼합 위험도" in high_items:
        return "용도 혼합 관리형 재생", "주거와 상업 기능이 혼재되어 있어 방화구획, 출입 동선 분리, 공용부 소방설비 보강이 핵심 전략입니다."

    if "층수·피난 난이도" in high_items or evacuation_risk:
        return "피난 체계 개선형 재생", "층수 또는 피난 조건에서 위험이 나타나므로 계단실, 방화문, 유도등, 비상조명, 피난 안내 체계를 우선 개선해야 합니다."

    if exterior_risk:
        return "외피 성능 개선형 재생", "외장재 위험이 확인되어 외벽 마감재의 불연화, 개구부 주변 방화 성능 개선이 우선됩니다."

    if electric_risk or fire_equipment_risk:
        return "설비 우선 개선형 재생", "전기설비와 초기 소화설비를 중심으로 한 저비용·고효율 안전 개선이 적합합니다."

    return "유지관리형 재생", "치명적인 위험 요소가 두드러지지 않아 정기 점검과 부분 보완 중심의 유지관리형 재생이 적합합니다."


def make_recommendations(auto_rows, field_inputs):
    recs = []

    auto_levels = {r["진단 항목"]: r["자동 판정"] for r in auto_rows}

    if auto_levels.get("건축물 노후도") == "노후도 높음":
        recs.append(("1순위", "노후 설비·마감 종합 점검", "사용승인 후 장기간 경과한 건축물은 전기, 소방, 방수, 마감재 상태를 종합 점검합니다."))

    if auto_levels.get("구조 위험도") == "높음":
        recs.append(("1순위", "구조 및 내화성능 보강 검토", "목조·조적조 등 화재에 취약한 구조는 내화성능과 보강 가능성을 우선 검토합니다."))

    if auto_levels.get("용도 혼합 위험도") == "높음":
        recs.append(("우선", "방화구획 및 출입 동선 정비", "주거와 근린생활시설이 혼재된 경우 공용부 방화구획, 계단실, 출입 동선을 명확히 정비합니다."))

    if auto_levels.get("층수·피난 난이도") == "높음":
        recs.append(("우선", "수직 피난 체계 개선", "계단실 방화문, 유도등, 비상조명, 피난 안내 표지를 점검하고 보강합니다."))

    if field_inputs["외장재"] in ["가연성 마감재", "확인 불가"]:
        recs.append(("우선", "외장재 불연화 검토", "외벽 마감재의 화재 확산 가능성을 확인하고 불연 또는 준불연 재료로 개선합니다."))

    if field_inputs["전기설비 상태"] in ["노후", "확인 불가"]:
        recs.append(("우선", "전기설비 점검 및 교체", "노후 배선, 분전반, 콘센트, 과부하 가능성을 점검하고 필요한 경우 교체합니다."))

    if field_inputs["소화설비"] in ["없음", "일부 있음"]:
        recs.append(("우선", "초기 소화설비 보강", "소화기, 단독경보형 감지기, 공용부 감지기 등 초기 대응 설비를 보강합니다."))

    if field_inputs["피난 동선"] in ["불명확", "1방향 피난"]:
        recs.append(("우선", "피난 경로 시각화", "대피 방향, 출입구, 계단실을 명확히 인지할 수 있도록 안내 사인과 비상조명을 개선합니다."))

    if not recs:
        recs.append(("유지관리", "정기 안전 점검", "현재 위험도는 낮지만 정기적인 소방·전기·피난 점검 체계를 유지합니다."))

    return recs


# ============================================================
# 세션 상태 초기화
# ============================================================

defaults = {
    "address_results": [],
    "selected_juso": None,
    "bld_params": None,
    "api_item": None,
    "auto_rows": None,
    "auto_score": 0,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# 화면 구성
# ============================================================

juso_key, building_key, key_error = get_api_keys()

st.title("🔥 FIRE-R v5")
st.subheader("데이터 기반 노후 건축물 화재 취약성 및 건축재생 전략 진단 프로그램")

st.markdown(
    """
    주소를 입력하면 공공데이터 API로 건축물 정보를 자동 조회하고,  
    **노후도·구조·용도혼합·층수·규모**를 데이터 기반으로 진단한 뒤  
    최소한의 현장 확인 항목을 더해 **화재 취약성 점수와 건축재생 전략**을 제안합니다.
    """
)

if key_error:
    st.error(key_error)
    st.code(
        """
.streamlit/secrets.toml 파일을 만들고 아래 내용을 입력하세요.

JUSO_API_KEY = "주소검색_API_승인키"
BUILDING_API_KEY = "건축물대장_API_일반인증키"
        """.strip()
    )
    st.stop()

st.divider()

# 주소 입력
st.header("1. 주소 입력")

col_addr, col_btn = st.columns([4, 1])

with col_addr:
    keyword = st.text_input("진단할 건축물 주소", value="동소문로46길 18", label_visibility="collapsed")

with col_btn:
    address_search_btn = st.button("주소 조회", type="primary", use_container_width=True)

if address_search_btn:
    if not keyword:
        st.error("주소를 입력하세요.")
    else:
        try:
            results = search_address_juso(juso_key, keyword)
            st.session_state.address_results = results
            st.session_state.selected_juso = None
            st.session_state.api_item = None
            st.session_state.auto_rows = None
            st.session_state.auto_score = 0

            if len(results) == 0:
                st.warning("주소 검색 결과가 없습니다. 주소를 더 구체적으로 입력하세요.")
            else:
                st.success(f"주소 검색 결과 {len(results)}건")
        except Exception as e:
            st.error(f"주소 검색 오류: {e}")

if st.session_state.address_results:
    options = []
    for idx, item in enumerate(st.session_state.address_results):
        road = item.get("roadAddr", "")
        jibun = item.get("jibunAddr", "")
        options.append(f"{idx+1}. {road} / 지번: {jibun}")

    selected_label = st.selectbox("검색 결과 선택", options)
    selected_index = options.index(selected_label)
    st.session_state.selected_juso = st.session_state.address_results[selected_index]

    if st.button("선택한 주소로 건축물 정보 불러오기", type="primary"):
        try:
            bld_params = address_result_to_bld_params(st.session_state.selected_juso)
            st.session_state.bld_params = bld_params

            item, raw = fetch_building_title(
                building_key,
                bld_params["sigunguCd"],
                bld_params["bjdongCd"],
                bld_params["bun"],
                bld_params["ji"]
            )

            if item is None:
                st.warning("건축물대장 조회 결과가 없습니다. 선택한 주소의 지번 정보를 확인하세요.")
                st.session_state.api_item = None
                st.session_state.auto_rows = None
                st.session_state.auto_score = 0
            else:
                st.session_state.api_item = item
                auto_rows, auto_score = make_auto_diagnosis(item)
                st.session_state.auto_rows = auto_rows
                st.session_state.auto_score = auto_score
                st.success("건축물 정보 및 데이터 기반 진단 완료")
        except Exception as e:
            st.error(f"건축물대장 조회 오류: {e}")

st.divider()

left, right = st.columns([1, 1])

with left:
    st.header("2. 공공데이터 자동 조회")

    if st.session_state.selected_juso:
        juso = st.session_state.selected_juso
        selected_df = pd.DataFrame([
            ["도로명주소", juso.get("roadAddr", "-")],
            ["지번주소", juso.get("jibunAddr", "-")],
        ], columns=["항목", "값"])
        st.subheader("선택한 주소")
        st.dataframe(selected_df, use_container_width=True, hide_index=True)

    item = st.session_state.api_item

    if item:
        building_name = item.get("bldNm") or "건물명 없음"
        building_address = item.get("newPlatPlc") or item.get("platPlc") or "주소 정보 없음"

        bld_df = pd.DataFrame([
            ["건물명", building_name],
            ["건축물대장 주소", building_address],
            ["사용승인일", format_date_yyyymmdd(item.get("useAprDay"))],
            ["구조", item.get("strctCdNm", "-")],
            ["주용도", item.get("mainPurpsCdNm", "-")],
            ["기타용도", item.get("etcPurps", "-")],
            ["지상층수", item.get("grndFlrCnt", "-")],
            ["지하층수", item.get("ugrndFlrCnt", "-")],
            ["건축면적", f"{item.get('archArea', '-')}㎡"],
            ["연면적", f"{item.get('totArea', '-')}㎡"],
        ], columns=["항목", "값"])
        st.subheader("건축물대장 표제부")
        st.dataframe(bld_df, use_container_width=True, hide_index=True)
    else:
        building_name = "조회 전 건축물"
        building_address = "-"
        st.info("주소를 검색하고 건축물 정보를 불러오면 자동 조회 결과가 표시됩니다.")

with right:
    st.header("3. 데이터 기반 자동 진단")

    if st.session_state.auto_rows:
        auto_df = pd.DataFrame(st.session_state.auto_rows)
        st.dataframe(auto_df, use_container_width=True, hide_index=True)

        st.metric("공공데이터 기반 점수", f"{st.session_state.auto_score}점 / 74점")
        st.caption("건축물대장 기반으로 노후도, 구조, 용도 혼합, 층수, 규모를 자동 판정합니다.")
    else:
        st.info("건축물 정보 조회 후 자동 진단 결과가 표시됩니다.")

st.divider()

# 현장 확인 항목
st.header("4. 최소 현장 확인 항목")
st.caption("공공데이터로 확인하기 어려운 항목만 사용자가 확인합니다.")

field_col1, field_col2 = st.columns(2)

with field_col1:
    field_inputs = {}
    field_inputs["외장재"] = st.selectbox("외장재", list(FIELD_SCORE_TABLE["외장재"].keys()))
    field_inputs["전기설비 상태"] = st.selectbox("전기설비 상태", list(FIELD_SCORE_TABLE["전기설비 상태"].keys()))

with field_col2:
    field_inputs["소화설비"] = st.selectbox("소화설비", list(FIELD_SCORE_TABLE["소화설비"].keys()))
    field_inputs["피난 동선"] = st.selectbox("피난 동선", list(FIELD_SCORE_TABLE["피난 동선"].keys()))

run_btn = st.button("화재 취약성 및 재생 전략 진단하기", type="primary", use_container_width=True)

if run_btn:
    st.divider()
    st.header("5. 진단 결과")

    if st.session_state.auto_rows is None:
        st.error("먼저 주소 검색과 건축물 정보 조회를 완료하세요.")
    else:
        auto_rows = st.session_state.auto_rows
        auto_score = st.session_state.auto_score

        field_rows = []
        field_score = 0

        for category, selected in field_inputs.items():
            score = FIELD_SCORE_TABLE[category][selected]
            field_score += score
            field_rows.append({
                "진단 항목": category,
                "입력값": selected,
                "점수": score,
                "입력 방식": "현장 확인"
            })

        total_score = auto_score + field_score
        grade, risk_text, regen_label = get_grade(total_score)
        grade_color = get_grade_color(total_score)
        regen_type, regen_desc = determine_regeneration_type(auto_rows, field_inputs)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("최종 화재 취약성 점수", f"{total_score} / {MAX_SCORE}점")
        with col2:
            st.markdown(
                f"""
                <div style="
                    padding: 18px;
                    border-radius: 12px;
                    background-color: {grade_color};
                    color: white;
                    text-align: center;
                    font-size: 24px;
                    font-weight: bold;">
                    {grade}
                </div>
                """,
                unsafe_allow_html=True
            )
        with col3:
            st.metric("위험도", risk_text)
        with col4:
            st.metric("재생 방향", regen_label)

        st.progress(min(total_score / MAX_SCORE, 1.0))

        st.subheader("재생 유형")
        st.success(f"{regen_type}")
        st.write(regen_desc)

        st.subheader("점수 상세")
        detail_auto_df = pd.DataFrame(auto_rows)
        detail_auto_df["입력 방식"] = "공공데이터 자동"

        detail_field_df = pd.DataFrame(field_rows)
        detail_field_df = detail_field_df.rename(columns={"입력값": "자동 판정"})
        detail_field_df["판정 근거"] = "-"

        detail_df = pd.concat([
            detail_auto_df[["진단 항목", "자동 판정", "점수", "판정 근거", "입력 방식"]],
            detail_field_df[["진단 항목", "자동 판정", "점수", "판정 근거", "입력 방식"]],
        ], ignore_index=True)

        st.dataframe(detail_df, use_container_width=True, hide_index=True)

        st.subheader("건축재생 개선 우선순위")
        rec_df = pd.DataFrame(make_recommendations(auto_rows, field_inputs), columns=["우선순위", "개선 제안", "설명"])
        st.dataframe(rec_df, use_container_width=True, hide_index=True)

        st.subheader("보고서 요약문")
        high_risks = detail_df.sort_values(by="점수", ascending=False).head(3)["진단 항목"].tolist()

        summary = f"""
[{building_name}]의 화재 취약성 진단 결과, 최종 점수는 {total_score}점이며 {grade}으로 평가되었다.
본 진단은 도로명주소 검색API와 국토교통부 건축물대장 OpenAPI를 활용하여 건축물의 사용승인일, 구조, 용도, 층수, 연면적 정보를 자동 조회하고,
이를 바탕으로 건축물 노후도, 구조 위험도, 용도 혼합 위험도, 층수·피난 난이도, 연면적 규모 위험도를 산정하였다.
추가로 외장재, 전기설비, 소화설비, 피난 동선 등 현장 확인 항목을 반영하여 최종 화재 취약성 점수를 도출하였다.
주요 취약 요소는 {', '.join(high_risks)} 항목이며, 이에 따른 적정 재생 유형은 '{regen_type}'으로 판단된다.
따라서 본 건축물은 단순 철거 여부가 아니라, 취약 요소를 우선적으로 개선하여 안전한 건축재생이 가능한 방향으로 검토할 필요가 있다.
        """
        st.text_area("복사해서 발표자료나 설명서에 사용할 수 있는 요약문", summary.strip(), height=220)

st.divider()
st.caption("FIRE-R v5.0 | 데이터 기반 화재 취약성 및 건축재생 전략 진단 | Python + Streamlit")

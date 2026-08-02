import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import datetime
import re
import pytz
import os
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from sklearn.cluster import DBSCAN
import numpy as np
import json
import folium
import platform

# OS에 따른 한글 폰트 설정
if platform.system() == 'Windows':
    plt.rc('font', family='Malgun Gothic')  # 윈도우: 맑은 고딕
elif platform.system() == 'Darwin':
    plt.rc('font', family='AppleGothic')    # 맥: 애플 고딕
else:
    plt.rc('font', family='NanumBarunGothic') # 리눅스

# 마이너스 기호 깨짐 방지
plt.rc('axes', unicode_minus=False)

#1단계 할리스 매장 크롤링

BASE_URL = "https://www.hollys.co.kr/store/korea/korStore2.do"

# =====================================================
# 1) pagination 정보 파싱 (페이지번호 + 다음블록 여부)
# =====================================================
def parse_paging_info(soup):
    paging_div = soup.select_one("div.paging")
    if paging_div is None:
        return [], None

    page_numbers = []

    for tag in paging_div.select("a, strong"):
            txt = tag.get_text(strip=True)
            if txt.isdigit():
                page_numbers.append(int(txt))

    next_block_page = None
    
    for a in paging_div.select("a[onclick]"):
        onclick_text = a.get("onclick")
    
        match = re.search(r"paging\((\d+)\s*,\s*1\)", onclick_text)
        if match:
            next_block_page = int(match.group(1))
            break
    
    return page_numbers, next_block_page

# =====================================================
# 2) 총 페이지 수를 블록 이동하면서 끝까지 확인
# =====================================================
def get_total_pages():
    page = 1
    max_page = 1

    while True:
        print(f"총페이지 탐색중... (현재 확인 페이지: {page})")

        params = {"pageNo": page}
        res = requests.get(BASE_URL, params=params)
        soup = BeautifulSoup(res.text, "html.parser")

        page_numbers, next_block_page = parse_paging_info(soup)

        if page_numbers:
            max_page = max(max_page, max(page_numbers))

        if next_block_page is None:
            break

        page = next_block_page
        time.sleep(0.2)

    print("최종 확인된 총 페이지 수:", max_page)
    return max_page

# =====================================================
# 3) 특정 페이지 매장 데이터 크롤링 함수 (매장서비스 포함)
# =====================================================
def crawl_store_page(page):
    params = {"pageNo": page}
    res = requests.get(BASE_URL, params=params)

    if res.status_code != 200:
        print(f"{page}페이지 요청 실패:", res.status_code)
        return []

    soup = BeautifulSoup(res.text, "html.parser")

    tbody = soup.select_one("table.tb_store tbody")
    if tbody is None:
        return []

    rows = tbody.select("tr")
    page_result = []

    for row in rows:
        tds = row.select("td")

        # Hollys 테이블은 td 6개 구조임
        if len(tds) < 6:
            continue

        area = tds[0].get_text(strip=True)     # 지역
        name = tds[1].get_text(strip=True)     # 매장명
        status = tds[2].get_text(strip=True)   # 현황
        addr = tds[3].get_text(strip=True)     # 주소

        # 매장서비스는 무조건 5번째 칸 (index=4)
        service_td = tds[4]

        service_list = []
        for img in service_td.select("img"):
            alt = img.get("alt")
            if alt:
                service_list.append(alt.strip())

        store_service = "/".join(service_list)

        phone = tds[5].get_text(strip=True)    # 전화번호

        page_result.append([area, name, status, addr, store_service, phone])

    return page_result

# =====================================================
# 4) 실행부
# =====================================================
if __name__ == "__main__":

    total_pages = get_total_pages()

    all_data = []

    for page in range(1, total_pages + 1):
        print(f"매장 수집중: {page}/{total_pages}")

        page_data = crawl_store_page(page)
        all_data.extend(page_data)

        time.sleep(0.3)

    df = pd.DataFrame(all_data, columns=["지역", "매장명", "현황", "주소", "매장서비스", "전화번호"])

    print("\n최종 매장 수:", len(df))
    print(df.head())

    to_now = datetime.datetime.now(pytz.timezone('Asia/Seoul'))
    to_now = to_now.strftime('%Y-%m-%d %H:%M:%S')

    #filename = '%s-hollys_store_all.csv' % (to_now)
    #filename ='{}-hollys_store.csv'.format(to_now)
    #df.to_csv(filename, index=False, encoding="utf-8")
    df.to_csv('source/hollys_store.csv', index=False, encoding="utf-8")
    print("저장 완료:  hollys_store.csv")

# ### 2단계: 주소 → 위도(latitude)/ 경도(longitude) 변환 (Geocoding)
# - 정확도는  Kakao > Google > Nominatim
# - 특히 한국 주소는 카카오가 훨씬 강력합니다.
# - 좌표 변환은 여러 방법이 있지만, 무료로 쉽게 되는 방식은:
#   -  OpenStreetMap 기반 Nominatim (geopy 사용)

# 위의 소스 실행된 결과를 보면 위도 / 경도 출력값이 생성된 것도 있고 없는 것도 있다.
#
# ✅ 위도/경도가 안 나오는 주요 원인
# 1) 주소가 너무 길거나 불완전한 경우
#
#    예를 들어 주소에 이런 요소가 들어가면 실패 확률이 커집니다.
#
#  - "1~3층"
#
#  - "○○캠퍼스 청운관 1층"
#
#  - "(명지동)"
#
#  - "휴게소 4층"
#
#  - "." 같은 불필요 문자
#
# ➡️ Nominatim(OpenStreetMap)은 정확한 도로명 주소 형태를 가장 잘 인식합니다.
#
# 2) 도로명/지번 주소 인식 문제
#
#     어떤 주소는 지번 기반이거나 애매한 표기라서 검색이 안 됩니다.
#
# 3) Nominatim 자체 데이터에 없는 주소
#
#    Nominatim은 Google 지도처럼 모든 주소를 갖고 있지 않습니다.
#    (특히 건물 내부, 휴게소 시설, 캠퍼스 내부 매장 등)
#
# 4) 너무 많은 요청 → 차단 또는 응답 실패
#
#    454개 주소를 1초 간격으로 요청하면 시간이 오래 걸리고,
#    중간에 서버가 응답을 거부하거나 제한할 수도 있습니다.
#
# ✅ 해결 방법 (실무용 Best 방법)
# 방법 1) 주소 전처리(불필요 문구 제거) 후 검색
#
# 예:
#
#  - "1층", "2층", "지하", "(...)" 제거
#
#  - 쉼표 뒤 제거
#
#  - "휴게소점"이면 휴게소 이름만 검색

# [REST API키 생성]
# https://developers.kakao.com/
# 앱 > 앱 생성 >  생성한 앱 선택 > 앱 > 플랫폼키 > REST API키
# 클라이언트 시크릿에서 카카오 로그인과 비지니스 인증 활성화 ON

# [주소로 좌표변환]
# https://developers.kakao.com/docs/ko/local/dev-guide#address-coord

# import pandas as pd
# import requests
from tqdm import tqdm
# import time
# import re

# ---------------------------------
# 1) 카카오 REST API KEY 입력
# ---------------------------------
# KAKAO_API_KEY = "여기에_카카오_REST_API_KEY_입력"

# KAKAO_API_KEY을 .env에 저장함
load_dotenv()
KAKAO_API_KEY = os.getenv('KAKAO_API_KEY')

# ---------------------------------
# 2) 데이터 불러오기
# ---------------------------------
df = pd.read_csv("source/hollys_store.csv")

# ---------------------------------
# 3) 주소 전처리 함수
# ---------------------------------
def clean_address(address):
    if pd.isna(address):
        return ""

    addr = str(address)

    # ( ... ) 괄호 내용 제거
    addr = re.sub(r"\(.*?\)", "", addr)

    # 쉼표 뒤 제거
    addr = addr.split(",")[0]

    # 층/호수/지하 등 제거
    remove_patterns = [
        r"\d+\s*층",
        r"\d+\s*호",
        r"지하\s*\d*",
        r"B\d+",
        r"\d+F",
        r"\d+~\d+층",
        r"\d+~\d+",
        r"\s*층",
    ]

    for pattern in remove_patterns:
        addr = re.sub(pattern, "", addr)

    # 특수문자 정리
    addr = addr.replace("·", " ")
    addr = addr.replace(".", " ")
    addr = re.sub(r"\s+", " ", addr)

    return addr.strip()


# ---------------------------------
# 4) 카카오 주소검색 API
#  주소로 좌표 변환
# ---------------------------------
def kakao_address_search(query):
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print("주소검색 요청 실패:", response.status_code, response.text)
        return None, None

    result = response.json()

    if result["documents"]:
        x = result["documents"][0]["x"]  # 경도
        y = result["documents"][0]["y"]  # 위도
        return float(y), float(x)

    return None, None


# ---------------------------------
# 5) 카카오 키워드검색 API (휴게소 해결 핵심)
#  키워드로 장소 검색
# ---------------------------------
def kakao_keyword_search(query):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print("키워드검색 요청 실패:", response.status_code, response.text)
        return None, None

    result = response.json()

    if result["documents"]:
        x = result["documents"][0]["x"]  # 경도
        y = result["documents"][0]["y"]  # 위도
        return float(y), float(x)

    return None, None


# ---------------------------------
# 6) 휴게소점 전용 키워드 추출
# ---------------------------------
def extract_rest_area(store_name):
    rest_name = store_name.replace("(상)", "").replace("(하)", "")
    rest_name = rest_name.replace("휴게소점", "휴게소")
    rest_name = rest_name.strip()
    return rest_name


# ---------------------------------
# 7) 위도/경도 생성 (주소검색 실패 -> 키워드검색)
# ---------------------------------
lat_list = []
lon_list = []
clean_addr_list = []
method_list = []

for store, addr in tqdm(zip(df["매장명"], df["주소"]), total=len(df)):

    # 주소 전처리
    cleaned_addr = clean_address(addr)

    # 저장용
    clean_addr_list.append(cleaned_addr)

    # -----------------------------
    # 1차: 주소검색
    # -----------------------------
    lat, lon = kakao_address_search(cleaned_addr)

    if lat is not None:
        lat_list.append(lat)
        lon_list.append(lon)
        method_list.append("주소검색")
        time.sleep(0.2)
        continue

    # -----------------------------
    # 2차: 키워드검색 (휴게소점이면 휴게소명으로)
    # -----------------------------
    if "휴게소" in store:
        keyword = extract_rest_area(store) + " 할리스"
    else:
        keyword = store + " 할리스"

    lat, lon = kakao_keyword_search(keyword)

    if lat is not None:
        lat_list.append(lat)
        lon_list.append(lon)
        method_list.append("키워드검색")
    else:
        lat_list.append(None)
        lon_list.append(None)
        method_list.append("실패")

    time.sleep(0.2)


# ---------------------------------
# 8) 위도 / 경도 결과 저장
# ---------------------------------
df["주소_전처리"] = clean_addr_list
df["위도"] = lat_list
df["경도"] = lon_list
df["검색방식"] = method_list

print(df.head(10))
print("좌표 변환 성공률:", df["위도"].notnull().mean())


# -----------------------------
# 1) 시도 컬럼 생성
# -----------------------------
if "시도" not in df.columns:
    df["시도"] = df["주소"].astype(str).str.split().str[0]

# -----------------------------
# 2) 시도명 표준화 매핑
# -----------------------------
sido_map = {
    "서울": "서울특별시",
    "서울시": "서울특별시",
    "서울특별시": "서울특별시",

    "부산": "부산광역시",
    "부산시": "부산광역시",
    "부산광역시": "부산광역시",

    "대구": "대구광역시",
    "대구시": "대구광역시",
    "대구광역시": "대구광역시",

    "인천": "인천광역시",
    "인천시": "인천광역시",
    "인천광역시": "인천광역시",

    "광주": "광주광역시",
    "광주시": "광주광역시",
    "광주광역시": "광주광역시",

    "대전": "대전광역시",
    "대전시": "대전광역시",
    "대전광역시": "대전광역시",

    "울산": "울산광역시",
    "울산시": "울산광역시",
    "울산광역시": "울산광역시",

    "세종": "세종특별자치시",
    "세종시": "세종특별자치시",
    "세종특별자치시": "세종특별자치시",

    "경기": "경기도",
    "경기도": "경기도",

    "강원": "강원특별자치도",
    "강원도": "강원특별자치도",
    "강원특별자치도": "강원특별자치도",

    "충북": "충청북도",
    "충청북도": "충청북도",

    "충남": "충청남도",
    "충청남도": "충청남도",

    "전북": "전북특별자치도",
    "전라북도": "전북특별자치도",
    "전북특별자치도": "전북특별자치도",

    "전남": "전라남도",
    "전라남도": "전라남도",

    "경북": "경상북도",
    "경상북도": "경상북도",

    "경남": "경상남도",
    "경상남도": "경상남도",

    "제주": "제주특별자치도",
    "제주도": "제주특별자치도",
    "제주특별자치도": "제주특별자치도"
}

df["시도"] = df["시도"].replace(sido_map)

df.to_csv("source/hollys_store_geo_kakao_final.csv", index=False, encoding="utf-8")
print("저장 완료: ｓource/hollys_store_geo_kakao_final.csv")

# ### 3단계: 시도별 매장 수 계산

# import pandas as pd

df_store = pd.read_csv("source/hollys_store_geo_kakao_final.csv")

store_count = df_store["시도"].value_counts().reset_index()
store_count.columns = ["시도", "매장수"]

print(store_count)

# ### 4단계: 인구 데이터 생성 및 불러오기(population_sido.csv)

import pandas as pd

# -----------------------------
# 0) CSV 불러오기
# -----------------------------
df = pd.read_csv(
    "source/행정구역_시군구_별__성별_인구수.csv",
    encoding="utf-8"
)

# -----------------------------
# 1) 필요 없는 행 제거
# 첫 번째 보조 헤더 행, 전국 합계 행 제거
# -----------------------------
df = df[
    ~df["행정구역(시군구)별"].isin([
        "행정구역(시군구)별",
        "전국"
    ])
].copy()

# -----------------------------
# 2) 필요한 컬럼만 선택
# 2026.06 = 2026년 6월 총인구수
# -----------------------------
df = df[[
    "행정구역(시군구)별",
    "2026.06"
]]

# -----------------------------
# 3) 컬럼명 변경
# -----------------------------
df = df.rename(columns={
    "행정구역(시군구)별": "시도",
    "2026.06": "인구"
})

# -----------------------------
# 4) 숫자형으로 변환
# -----------------------------
df["인구"] = pd.to_numeric(
    df["인구"],
    errors="coerce"
)

# 숫자 변환에 실패한 행 제거
df = df.dropna(subset=["인구"])

# 인구는 정수이므로 int형으로 변경
df["인구"] = df["인구"].astype(int)

# 인덱스 정리
df = df.reset_index(drop=True)

# -----------------------------
# 5) CSV 저장
# -----------------------------
df.to_csv(
    "source/population_sido.csv",
    index=False,
    encoding="utf-8-sig"
)

print("저장 완료: source/population_sido.csv")
print(df)

df_pop = pd.read_csv("source/population_sido.csv")
print(df_pop.head())

# ### 5단계: 인구 대비 매장 수(10만명당 매장 수)

#df_merge = pd.merge(store_count, df_pop, on="시도", how="inner")
df_merge = store_count.merge( df_pop, on="시도", how="inner")
print(df_merge.head())

df_merge["10만명당_매장수"] = (df_merge["매장수"] / df_merge["인구"]) * 100000

df_merge = df_merge.sort_values("10만명당_매장수", ascending=False)

print(df_merge)

df_merge.to_csv("source/hollys_population_analysis.csv", index=False, encoding="utf-8-sig")
print("저장 완료: source/hollys_population_analysis.csv")

# import pandas as pd
# from sklearn.cluster import DBSCAN
# import numpy as np

df = pd.read_csv("source/hollys_store_geo_kakao_final.csv")
df = df.dropna(subset=["위도", "경도"]).reset_index(drop=True)

coords = df[["위도", "경도"]].values

# DBSCAN: eps는 거리기준(단위는 라디안 변환 후 적용)
kms_per_radian = 6371.0088
epsilon = 0.8 / kms_per_radian   # 0.8km 이내 매장 밀집 기준

db = DBSCAN(eps=epsilon, min_samples=5, algorithm='ball_tree', metric='haversine')
df["cluster"] = db.fit_predict(np.radians(coords))

print(df["cluster"].value_counts())
df.to_csv("source/hollys_cluster.csv", index=False, encoding="utf-8-sig")
print("저장 완료: source/hollys_cluster.csv")

# ### 6단계: 기사에서 바로 쓰는 순위표 만들기

# - output폴더를 생성후 실행

df_merge["인구(만명)"] = df_merge["인구"] / 10000

df_report = df_merge[["시도", "매장수", "인구(만명)", "10만명당_매장수"]]
df_report = df_report.round(2)

print(df_report)
df_report.to_csv("output/hollys_report.csv", index=False, encoding="utf-8-sig")

# ### 7단계: 그래프 시각화(막대그래프)

# import matplotlib.pyplot as plt
# import seaborn as sns

plt.figure(figsize=(12,6))

ax = sns.barplot(
    data=df_merge,
    hue='시도',
    x="시도",
    y="10만명당_매장수"

)

plt.xticks(rotation=45)
plt.title("시도별 인구 10만명당 할리스 매장 수")
plt.xlabel("시도")
plt.ylabel("10만명당 매장 수")

# 값 표시
for p in ax.patches:
    ax.text(
        p.get_x() + p.get_width() / 2,
        p.get_height(),
        f"{p.get_height():.2f}",
        ha="center",
        va="bottom",
        fontsize=10
    )

plt.tight_layout()
plt.savefig("output/hollys_barplot.png", dpi=200)
plt.show()

# 할리스는 서울에만 많지 않았다… 인구 대비 매장 밀도 분석 결과
#
# 할리스커피 매장은 서울과 수도권에 집중돼 있다는 인식이 강하다. 그러나 매장 수 자체가 아니라 인구 대비 매장 밀도(10만명당 매장 수)로 분석하면, 서울보다 더 촘촘하게 분포한 지역이 존재하는 것으로 나타났다.
#
# 본 분석은 할리스 공식 홈페이지 매장검색 페이지에서 매장 주소를 수집해 시도별 매장 수를 집계한 뒤, KOSIS 국가통계포털의 시도별 주민등록 인구 데이터와 결합해 '인구 10만명당 할리스 매장 수'를 산출한 결과다.
#
# 분석 결과, 전북특별자치도가 인구 10만명당 1.80개로 전국에서 가장 높은 매장 밀도를 기록했다. 이는 2위인 서울특별시(1.29개)보다도 큰 수치로, 할리스 매장이 단순히 서울 중심으로만 분포해 있다는 통념과는 다른 결과다.
#
# 뒤이어 대전광역시(1.04개), 세종특별자치시(1.02개), 울산광역시(1.01개), 충청북도(1.00개)가 1개 수준을 유지하며 상위권에 포함됐다. 즉, 일부 광역시 및 중부권 지역에서는 인구 규모가 상대적으로 크지 않더라도 매장 밀도가 높게 형성돼 있음을 확인할 수 있다.
#
# 반면 수도권 핵심 지역인 경기도는 0.68개로 중하위권에 그쳤다. 인구가 집중된 지역임에도 매장 밀도가 낮게 나타난 것은, 단순 인구 수만으로 프랜차이즈 입지 전략을 설명하기 어렵다는 점을 보여준다.
#
# 중위권에는 강원특별자치도(0.99개), 충청남도(0.94개), 부산광역시(0.93개), 제주특별자치도(0.90개), 광주광역시(0.79개)가 포함됐다. 특히 광주는 광역시임에도 서울·대전·울산과 비교하면 매장 밀도가 상대적으로 낮은 편이다.
#
# 하위권에는 대구광역시(0.72개), 전라남도(0.67개), 경상남도(0.66개), 인천광역시(0.59개), 경상북도(0.56개)가 위치했다. 인천은 수도권임에도 불구하고 매장 밀도가 전국 최하위권 수준으로 나타났다.
#
# 이번 분석은 프랜차이즈 매장 분포를 해석할 때 '매장 수' 자체보다 인구 대비 매장 밀도가 더 중요한 지표가 될 수 있음을 보여준다. 향후 유동인구 데이터나 스타벅스·이디야 등 경쟁 브랜드 매장 데이터까지 결합한다면, 할리스의 입지 전략을 더욱 정밀하게 분석할 수 있을 것으로 보인다.

# 매장수 vs 인구 관계 (산점도)

plt.figure(figsize=(8,6))
plt.scatter(df_merge["인구"], df_merge["매장수"])

for i, row in df_merge.iterrows():
    plt.text(row["인구"], row["매장수"], row["시도"], fontsize=9)

plt.title("시도별 인구와 할리스 매장 수 관계")
plt.xlabel("인구")
plt.ylabel("매장 수")
plt.tight_layout()
plt.show()

# 서울이 아니었다… 산포도가 보여준 '할리스 매장 집중'의 진짜 이유
#
# 할리스커피 매장은 서울과 수도권에 집중돼 있다는 인식이 강하다. 그러나 시도별 인구와 할리스 매장 수의 관계를 산포도(Scatter Plot)로 분석한 결과, 매장 분포는 단순히 인구 규모만으로 설명되지 않는 것으로 나타났다. 인구가 많을수록 매장 수가 증가하는 경향은 분명했지만, 일부 지역은 인구 대비 매장 수가 유독 많거나 적어 뚜렷한 편차를 드러냈다.
#
# 이번 분석은 할리스 공식 홈페이지 매장검색 페이지에서 매장 주소를 수집해 시도별 매장 수를 집계한 뒤, 시도별 주민등록 인구 데이터와 결합해 시각화한 것이다. 산포도는 각 시도를 하나의 점으로 표시해, 인구(가로축)가 증가할수록 매장 수(세로축)가 어떻게 변하는지 확인할 수 있도록 구성됐다.
#
# 그래프에서 가장 눈에 띄는 지점은 서울특별시와 경기도다. 경기도는 전국에서 가장 많은 인구를 보유한 지역이지만, 매장 수는 서울보다 낮게 나타났다. 반면 서울은 경기도보다 인구 규모가 작음에도 매장 수가 전국 최고 수준으로 표시돼, 인구 대비 매장 집중 현상이 뚜렷했다. 산포도 상에서 서울은 다른 시도들과 비교해 상대적으로 높은 위치에 놓이며, '상권 중심형' 입지 특성이 강하게 나타난 사례로 해석된다.
#
# 또한 산포도에서는 다수의 시도가 좌측 하단에 군집을 이루는 형태도 확인된다. 이는 전국 대부분의 시도가 인구와 매장 수에서 비슷한 범위에 분포해 있음을 의미한다. 즉, 할리스 매장 수는 일정 수준까지는 인구 증가에 비례해 증가하지만, 일정 구간 이후에는 상권 구조에 따라 매장 수가 크게 달라질 수 있음을 보여준다.
#
# 특히 인구 규모가 크지 않은 일부 지역에서도 매장 수가 상대적으로 높게 나타나며, 산포도에서 평균적인 흐름선보다 위쪽에 위치하는 점들이 확인된다. 이는 해당 지역들이 인구 대비 매장 수가 높다는 뜻이며, '인구 중심'이 아닌 '상권 중심' 입점 전략이 작동했을 가능성을 시사한다. 반대로 인구는 많지만 매장 수가 기대 수준보다 낮은 지역들도 존재해, 매장 확장 전략이 지역별로 균일하지 않다는 점을 드러냈다.
#
# 이 같은 결과는 프랜차이즈 매장 분포가 단순히 거주 인구만을 따라 움직이는 것이 아니라, 유동인구·오피스 밀집도·역세권 상권·대학가·관광수요 등 복합적인 요인에 의해 결정된다는 점을 뒷받침한다. 실제로 서울은 거주 인구 외에도 전국 최대 규모의 유동인구와 상업시설이 집중돼 있어, 인구 대비 매장 수가 과밀하게 나타날 수 있는 구조를 갖고 있다. 반면 경기도는 인구가 분산돼 있고 생활권이 넓어, 특정 상권에 매장이 집중되기 어려운 환경일 수 있다.
#
# 산포도 분석은 단순 순위표보다 더 직접적으로 '입지 전략의 비정상적 집중'을 보여준다. 인구가 증가하면 매장 수가 늘어나는 일반적 패턴이 존재함에도, 서울과 같은 특정 지역은 그 패턴에서 벗어나 과도하게 높은 매장 수를 기록했다. 이는 할리스 매장 분포가 인구 기반이 아니라, 상권 중심의 선택적 전략에 의해 강화되고 있음을 시각적으로 확인시켜준다.
#
# 이번 분석은 프랜차이즈 입지 전략을 평가할 때 인구와 매장 수의 단순 비교만으로는 부족하며, 산포도 기반의 관계 분석을 통해 '예외 지역'과 '집중 지역'을 찾아내는 방식이 효과적이라는 점을 보여준다. 향후 유동인구 데이터, 경쟁 브랜드 매장 데이터까지 결합할 경우, 특정 지역의 상권 경쟁 구조와 프랜차이즈 확장 전략을 더욱 정밀하게 분석할 수 있을 것으로 보인다

# ### 8단계: 지도 시각화(Choropleth)

# #### (1) 시도 GeoJSON 확보 방법(실습용)
#
# 방법 A (추천)
#
#   - GitHub에서 "korea sido geojson" 검색 후 다운로드
#   - https://github.com/southkorea/southkorea-maps/blob/master/gadm/json/skorea-geo.json
#
# 대표 키워드:
#
#   - korea administrative boundaries geojson
#
#   - korea sido geojson
#
# 다운로드한 파일명을 korea_sido.geojson로 저장

# #### (2) Choropleth 지도 코드

# import json

with open("source/skorea-provinces-2018-geo.json", encoding="utf-8") as f:
    geo = json.load(f)

print(geo["features"][0]["properties"].keys())
print(geo["features"][0]["properties"])

# import folium
# import json
# import pandas as pd

df = pd.read_csv("source/hollys_population_analysis.csv")

with open("source/skorea-provinces-2018-geo.json", encoding="utf-8") as f:
    geo = json.load(f)

# 광주광역시의 중심 기준 위도·경도
m = folium.Map(location=[35.1595, 126.8526], zoom_start=7)

folium.Choropleth(
    geo_data=geo,
    data=df,
    columns=["시도", "10만명당_매장수"],
    key_on="feature.properties.name",
    fill_opacity=0.7,
    line_opacity=0.3,
    legend_name="10만명당 할리스 매장 수"
).add_to(m)

m.save("output/hollys_density_map.html")
print("저장 완료: output/hollys_density_map.html")
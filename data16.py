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
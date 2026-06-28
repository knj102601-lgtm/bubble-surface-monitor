import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from fredapi import Fred
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta


st.set_page_config(
    page_title="Bubble Surface Tension Monitor",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Bubble Surface Tension Monitor")
st.caption("시장 고점 근접도를 추적하기 위한 개인용 모니터링 대시보드")


def safe_last(series):
    series = pd.Series(series).dropna()
    if len(series) == 0:
        return np.nan
    return series.iloc[-1]


def pct_return(series, periods):
    series = pd.Series(series).dropna()
    if len(series) <= periods:
        return np.nan
    return (series.iloc[-1] / series.iloc[-periods] - 1) * 100


def is_below_ma(series, window):
    series = pd.Series(series).dropna()
    if len(series) < window:
        return False
    ma = series.rolling(window).mean()
    return bool(series.iloc[-1] < ma.iloc[-1])


def format_number(value, suffix=""):
    if pd.isna(value):
        return "N/A"
    return f"{value:.2f}{suffix}"


def add_score(score_items, category, condition, points, message):
    if bool(condition):
        score_items.append({
            "분류": category,
            "점수": points,
            "신호": message
        })


st.sidebar.header("설정")

period = st.sidebar.selectbox(
    "가격 데이터 조회 기간",
    ["1y", "2y", "5y"],
    index=1
)

try:
    default_fred_api_key = st.secrets.get("FRED_API_KEY", "")
except Exception:
    default_fred_api_key = ""

fred_api_key = st.sidebar.text_input(
    "FRED API Key",
    value=default_fred_api_key,
    type="password",
    help="FRED API Key가 없으면 금리·신용 데이터 일부가 표시되지 않습니다."
)

refresh = st.sidebar.button("데이터 새로고침")

st.sidebar.markdown("---")
st.sidebar.caption("※ 이 대시보드는 실시간 매매용이 아니라 시장 위험도 모니터링용입니다.")


TICKERS = {
    "SPY": "S&P500",
    "QQQ": "Nasdaq100",
    "RSP": "S&P500 Equal Weight",
    "IWM": "Russell2000",
    "SOXX": "Semiconductor",
    "EEM": "Emerging Markets",
    "EWY": "Korea",
    "EWT": "Taiwan",
    "EWJ": "Japan",
    "EWG": "Germany",
    "EWQ": "France",
    "INDA": "India",
    "EWW": "Mexico",
    "VGK": "Europe",
    "VNQ": "US REITs"
}

GLOBAL_ETFS = [
    "EEM", "EWY", "EWT", "EWJ", "EWG",
    "EWQ", "INDA", "EWW", "VGK", "VNQ"
]

FRED_SERIES = {
    "DGS10": "미국 10년물 금리",
    "DGS2": "미국 2년물 금리",
    "DFII10": "미국 10년 실질금리",
    "T10YIE": "10년 기대인플레이션",
    "BAMLH0A0HYM2": "하이일드 OAS",
    "BAMLC0A4CBBB": "BBB 회사채 OAS",
    "NFCI": "Chicago Fed NFCI"
}


@st.cache_data(ttl=60 * 60)
def load_price_data(tickers, period):
    raw = yf.download(
        tickers=list(tickers.keys()),
        period=period,
        auto_adjust=True,
        progress=False
    )

    if raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
    else:
        close = raw[["Close"]]
        close.columns = list(tickers.keys())[:1]

    close = close.dropna(how="all")
    return close


@st.cache_data(ttl=60 * 60 * 6)
def load_fred_data(api_key, series_dict):
    result = {}

    if not api_key:
        return result

    try:
        fred = Fred(api_key=api_key)
    except Exception:
        return result

    start_date = (datetime.today() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")

    for code, name in series_dict.items():
        try:
            s = fred.get_series(code, observation_start=start_date)
            s = pd.Series(s)
            s.index = pd.to_datetime(s.index)
            result[code] = s.dropna()
        except Exception:
            result[code] = pd.Series(dtype=float)

    return result


if refresh:
    st.cache_data.clear()

with st.spinner("데이터를 불러오는 중입니다..."):
    prices = load_price_data(TICKERS, period)
    fred_data = load_fred_data(fred_api_key, FRED_SERIES)


if prices.empty:
    st.error("가격 데이터를 불러오지 못했습니다. 인터넷 연결 또는 yfinance 데이터 상태를 확인하세요.")
    st.stop()


returns_table = []

for ticker, name in TICKERS.items():
    if ticker in prices.columns:
        s = prices[ticker]
        returns_table.append({
            "Ticker": ticker,
            "Name": name,
            "1M": pct_return(s, 21),
            "3M": pct_return(s, 63),
            "6M": pct_return(s, 126),
            "12M": pct_return(s, 252),
            "Latest": safe_last(s),
            "Below 50D": is_below_ma(s, 50),
            "Below 200D": is_below_ma(s, 200)
        })

returns_df = pd.DataFrame(returns_table)


def relative_return(a, b, periods):
    if a not in prices.columns or b not in prices.columns:
        return np.nan

    ratio = (prices[a] / prices[b]).dropna()

    if len(ratio) <= periods:
        return np.nan

    return (ratio.iloc[-1] / ratio.iloc[-periods] - 1) * 100


relative_items = [
    ("QQQ/SPY", "Nasdaq100 vs S&P500", "QQQ", "SPY"),
    ("SOXX/SPY", "반도체 vs S&P500", "SOXX", "SPY"),
    ("RSP/SPY", "동일가중 S&P500 vs 시총가중 S&P500", "RSP", "SPY"),
    ("IWM/SPY", "중소형주 vs S&P500", "IWM", "SPY"),
    ("EEM/QQQ", "신흥국 vs Nasdaq100", "EEM", "QQQ"),
    ("EWY/QQQ", "한국 vs Nasdaq100", "EWY", "QQQ"),
    ("EWT/QQQ", "대만 vs Nasdaq100", "EWT", "QQQ"),
    ("VNQ/SPY", "리츠 vs S&P500", "VNQ", "SPY")
]

relative_table = []

for label, desc, a, b in relative_items:
    relative_table.append({
        "Ratio": label,
        "Description": desc,
        "1M": relative_return(a, b, 21),
        "3M": relative_return(a, b, 63),
        "6M": relative_return(a, b, 126)
    })

relative_df = pd.DataFrame(relative_table)


fred_table = []

for code, name in FRED_SERIES.items():
    s = fred_data.get(code, pd.Series(dtype=float))
    latest = safe_last(s)
    clean = s.dropna()

    one_month_change = np.nan
    three_month_change = np.nan

    if len(clean) > 22:
        one_month_change = latest - clean.iloc[-22]

    if len(clean) > 66:
        three_month_change = latest - clean.iloc[-66]

    fred_table.append({
        "Code": code,
        "Name": name,
        "Latest": latest,
        "1M Change": one_month_change,
        "3M Change": three_month_change
    })

fred_df = pd.DataFrame(fred_table)


def fred_latest(code):
    if fred_df.empty or code not in fred_df["Code"].values:
        return np.nan
    return fred_df.loc[fred_df["Code"] == code, "Latest"].values[0]


def fred_change(code, col):
    if fred_df.empty or code not in fred_df["Code"].values:
        return np.nan
    return fred_df.loc[fred_df["Code"] == code, col].values[0]


score_items = []

global_3m_negative_count = 0
global_total = 0

for ticker in GLOBAL_ETFS:
    if ticker in returns_df["Ticker"].values:
        val = returns_df.loc[returns_df["Ticker"] == ticker, "3M"].values[0]
        if not pd.isna(val):
            global_total += 1
            if val < 0:
                global_3m_negative_count += 1

negative_ratio = global_3m_negative_count / global_total if global_total > 0 else 0

add_score(
    score_items,
    "주변부 하락",
    negative_ratio >= 0.3,
    10,
    f"글로벌 주변부 ETF 중 3개월 수익률 음수 비율이 {negative_ratio:.0%}입니다."
)

add_score(
    score_items,
    "주변부 하락",
    negative_ratio >= 0.5,
    10,
    "글로벌 주변부 ETF 절반 이상이 3개월 기준 하락 중입니다."
)

rsp_spy_3m = relative_df.loc[relative_df["Ratio"] == "RSP/SPY", "3M"].values[0]
iwm_spy_3m = relative_df.loc[relative_df["Ratio"] == "IWM/SPY", "3M"].values[0]
qqq_spy_3m = relative_df.loc[relative_df["Ratio"] == "QQQ/SPY", "3M"].values[0]
soxx_spy_3m = relative_df.loc[relative_df["Ratio"] == "SOXX/SPY", "3M"].values[0]

add_score(
    score_items,
    "시장 폭 축소",
    not pd.isna(rsp_spy_3m) and rsp_spy_3m < -2,
    10,
    "동일가중 S&P500이 시총가중 S&P500 대비 3개월 기준 약세입니다."
)

add_score(
    score_items,
    "시장 폭 축소",
    not pd.isna(iwm_spy_3m) and iwm_spy_3m < -5,
    10,
    "러셀2000이 S&P500 대비 3개월 기준 크게 약세입니다."
)

add_score(
    score_items,
    "주도주 쏠림",
    not pd.isna(qqq_spy_3m) and not pd.isna(rsp_spy_3m) and qqq_spy_3m > 5 and rsp_spy_3m < 0,
    10,
    "나스닥100은 강하지만 동일가중 지수는 약해 시장 쏠림이 나타납니다."
)

add_score(
    score_items,
    "주도주 쏠림",
    not pd.isna(soxx_spy_3m) and soxx_spy_3m > 8,
    10,
    "반도체가 S&P500 대비 3개월 기준 크게 앞서가고 있습니다."
)

dgs10 = fred_latest("DGS10")
dfii10 = fred_latest("DFII10")
t10yie_3m = fred_change("T10YIE", "3M Change")

add_score(
    score_items,
    "금리 압박",
    not pd.isna(dgs10) and dgs10 >= 4.7,
    10,
    f"미국 10년물 금리가 {dgs10:.2f}%로 5% 심리선에 접근하고 있습니다."
)

add_score(
    score_items,
    "금리 압박",
    not pd.isna(dgs10) and dgs10 >= 5.0,
    10,
    f"미국 10년물 금리가 {dgs10:.2f}%로 5%를 넘어섰습니다."
)

add_score(
    score_items,
    "실질금리 압박",
    not pd.isna(dfii10) and dfii10 >= 2.0,
    10,
    f"미국 10년 실질금리가 {dfii10:.2f}%로 성장주 밸류에이션에 부담을 줄 수 있습니다."
)

add_score(
    score_items,
    "물가 기대",
    not pd.isna(t10yie_3m) and t10yie_3m > 0.25,
    10,
    "10년 기대인플레이션이 3개월 기준 상승 중입니다."
)

hy_oas_1m = fred_change("BAMLH0A0HYM2", "1M Change")
bbb_oas_1m = fred_change("BAMLC0A4CBBB", "1M Change")
nfci = fred_latest("NFCI")

add_score(
    score_items,
    "신용 스트레스",
    not pd.isna(hy_oas_1m) and hy_oas_1m > 0.30,
    10,
    "하이일드 스프레드가 1개월 기준 확대되고 있습니다."
)

add_score(
    score_items,
    "신용 스트레스",
    not pd.isna(bbb_oas_1m) and bbb_oas_1m > 0.15,
    10,
    "BBB 회사채 스프레드가 1개월 기준 확대되고 있습니다."
)

add_score(
    score_items,
    "금융환경",
    not pd.isna(nfci) and nfci > 0,
    10,
    f"NFCI가 {nfci:.2f}로 평균보다 타이트한 금융환경을 시사합니다."
)

for ticker in ["QQQ", "SOXX"]:
    if ticker in returns_df["Ticker"].values:
        below_50 = bool(returns_df.loc[returns_df["Ticker"] == ticker, "Below 50D"].values[0])
        below_200 = bool(returns_df.loc[returns_df["Ticker"] == ticker, "Below 200D"].values[0])

        add_score(
            score_items,
            "주도주 추세 훼손",
            below_50,
            5,
            f"{ticker}가 50일 이동평균선을 하회하고 있습니다."
        )

        add_score(
            score_items,
            "주도주 추세 훼손",
            below_200,
            10,
            f"{ticker}가 200일 이동평균선을 하회하고 있습니다."
        )

score_df = pd.DataFrame(score_items)

if len(score_df) > 0:
    total_score = int(score_df["점수"].sum())
else:
    total_score = 0

total_score = min(total_score, 100)


def risk_label(score):
    if score < 30:
        return "정상 구간", "🟢"
    elif score < 50:
        return "과열 관찰 구간", "🟡"
    elif score < 70:
        return "고점 경계 구간", "🟠"
    elif score < 85:
        return "위험 구간", "🔴"
    else:
        return "붕괴 가능성 경계 구간", "🟣"


label, emoji = risk_label(total_score)

col1, col2, col3, col4 = st.columns(4)

col1.metric("종합 위험 점수", f"{total_score}/100")
col2.metric("위험 단계", f"{emoji} {label}")
col3.metric("3M 음수 주변부 ETF", f"{global_3m_negative_count}/{global_total}")
col4.metric("미국 10년물", format_number(dgs10, "%"))

st.progress(total_score / 100)

if total_score >= 70:
    st.error("위험 신호가 강하게 나타나고 있습니다. 현금비중, 레버리지, 주도주 집중도를 점검할 필요가 있습니다.")
elif total_score >= 50:
    st.warning("고점 근접 신호가 일부 나타납니다. 주변부 하락 확산과 금리·신용 지표를 집중 점검하세요.")
else:
    st.success("현재 종합 점수 기준으로는 과도한 고점 경고가 강하게 나타나지는 않습니다.")


tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "① 종합 경고",
    "② 글로벌 수익률",
    "③ 상대강도",
    "④ 금리·신용",
    "⑤ 원자료",
    "⑥ FRED 설정"
])


with tab1:
    st.subheader("종합 위험 신호")

    if len(score_df) == 0:
        st.info("현재 조건에 걸린 주요 위험 신호가 없습니다.")
    else:
        st.dataframe(score_df, use_container_width=True)

    st.markdown("""
    ### 해석 기준

    | 점수 | 단계 | 해석 |
    |---:|---|---|
    | 0~29점 | 정상 구간 | 고점 경고가 강하지 않은 상태 |
    | 30~49점 | 과열 관찰 구간 | 일부 과열 또는 쏠림 신호 발생 |
    | 50~69점 | 고점 경계 구간 | 주변부 약화와 쏠림을 주의 깊게 관찰 |
    | 70~84점 | 위험 구간 | 현금비중, 레버리지, 분할매도 검토 필요 |
    | 85점 이상 | 붕괴 가능성 경계 구간 | 방어적 포지션을 우선 검토 |
    """)

    st.markdown("""
    ### 핵심 프레임

    - **김효진 박사 시그널:** 주변부 국가·지수 약화가 계단식으로 확산되는지 확인
    - **이은택 이사 시그널:** 금리·물가·신용환경이 자본 공급자를 멈추게 하는지 확인
    - **종합 판단:** 주도주 쏠림과 신용 스트레스가 동시에 나타날수록 위험도 상승
    """)


with tab2:
    st.subheader("글로벌 ETF 수익률 히트맵")

    heatmap_df = returns_df.set_index("Ticker")[["1M", "3M", "6M", "12M"]]

    fig = px.imshow(
        heatmap_df,
        text_auto=".1f",
        aspect="auto",
        color_continuous_scale="RdYlGn",
        title="ETF별 기간 수익률"
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### 상세 수익률")
    st.dataframe(returns_df, use_container_width=True)

    st.markdown("""
    ### 보는 법

    - **QQQ, SOXX는 강한데 EEM, EWY, EWT, VGK 등이 약해진다:** 주도주 쏠림 가능성
    - **3개월 수익률 음수 ETF 수가 점점 늘어난다:** 계단식 하락 확산 가능성
    - **RSP, IWM이 약하다:** 시장 전체보다는 일부 대형주 중심 상승 가능성
    """)


with tab3:
    st.subheader("상대강도 모니터링")

    rel_heatmap = relative_df.set_index("Ratio")[["1M", "3M", "6M"]]

    fig = px.imshow(
        rel_heatmap,
        text_auto=".1f",
        aspect="auto",
        color_continuous_scale="RdYlGn",
        title="상대강도 수익률"
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### 상대강도 상세")
    st.dataframe(relative_df, use_container_width=True)

    st.markdown("""
    ### 핵심 해석

    | 상대강도 | 의미 |
    |---|---|
    | QQQ/SPY 상승 | 나스닥 대형 기술주 쏠림 |
    | SOXX/SPY 상승 | 반도체 쏠림 |
    | RSP/SPY 하락 | 시장 폭 축소 |
    | IWM/SPY 하락 | 중소형주 소외 |
    | EEM/QQQ 하락 | 신흥국 대비 나스닥 쏠림 |
    | EWY/QQQ 하락 | 한국 대비 나스닥 쏠림 |
    | EWT/QQQ 하락 | 대만 대비 나스닥 쏠림 |
    | VNQ/SPY 하락 | 리츠 약세, 금리 부담 가능성 |
    """)


with tab4:
    st.subheader("금리·신용·금융환경")

    if not fred_api_key:
        st.warning("FRED API Key가 입력되지 않아 금리·신용 데이터가 표시되지 않을 수 있습니다.")
    else:
        st.dataframe(fred_df, use_container_width=True)

        for code, name in FRED_SERIES.items():
            s = fred_data.get(code, pd.Series(dtype=float))

            if len(s) > 0:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=s.index,
                    y=s.values,
                    mode="lines",
                    name=name
                ))

                fig.update_layout(
                    title=name,
                    xaxis_title="Date",
                    yaxis_title="Value",
                    height=350
                )

                st.plotly_chart(fig, use_container_width=True)

    st.markdown("""
    ### 위험한 조합

    - 미국 10년물 금리 상승
    - 실질금리 상승
    - 기대인플레이션 상승
    - 하이일드 스프레드 확대
    - BBB 스프레드 확대
    - NFCI 0 이상 진입

    이 조합이 동시에 나타나면 단순한 금리 상승이 아니라 **자본 공급 환경 악화**로 볼 수 있습니다.
    """)


with tab5:
    st.subheader("가격 원자료")
    st.dataframe(prices.tail(30), use_container_width=True)

    st.subheader("FRED 원자료")

    if len(fred_data) == 0:
        st.info("FRED 데이터가 없습니다. API Key를 입력하면 금리·신용 원자료가 표시됩니다.")
    else:
        selected_code = st.selectbox("FRED 시리즈 선택", list(FRED_SERIES.keys()))
        selected_series = fred_data.get(selected_code, pd.Series(dtype=float))

        if len(selected_series) > 0:
            st.dataframe(
                selected_series.tail(60).to_frame(FRED_SERIES[selected_code]),
                use_container_width=True
            )
        else:
            st.info("해당 FRED 데이터를 불러오지 못했습니다.")

with tab6:
    st.subheader("FRED API Key 및 지표 코드 설정")

    st.markdown("### 1. FRED API Key 상태")

    if fred_api_key:
        masked_key = fred_api_key[:4] + "****" + fred_api_key[-4:] if len(fred_api_key) >= 8 else "****"
        st.success("FRED API Key가 입력되어 있습니다.")
        st.code(masked_key)
    else:
        st.warning("FRED API Key가 입력되지 않았습니다.")
        st.info("API Key가 없으면 미국 금리·신용·금융환경 데이터가 표시되지 않을 수 있습니다.")

    st.markdown("### 2. 현재 연결된 FRED 지표 코드")

    fred_code_table = pd.DataFrame([
        {
            "FRED 코드": code,
            "지표명": name,
            "대시보드 내 역할": (
                "금리 압박 확인" if code in ["DGS10", "DGS2", "DFII10"] else
                "물가 기대 확인" if code == "T10YIE" else
                "신용 스트레스 확인" if code in ["BAMLH0A0HYM2", "BAMLC0A4CBBB"] else
                "금융환경 확인" if code == "NFCI" else
                "기타"
            )
        }
        for code, name in FRED_SERIES.items()
    ])

    st.dataframe(fred_code_table, use_container_width=True)

    st.markdown("### 3. FRED 데이터 연결 상태")

    if len(fred_data) == 0:
        st.warning("현재 FRED 데이터를 불러오지 못했습니다. API Key 입력 여부를 확인하세요.")
    else:
        connection_table = []

        for code, name in FRED_SERIES.items():
            s = fred_data.get(code, pd.Series(dtype=float))

            if len(s) > 0:
                latest_date = s.index[-1].strftime("%Y-%m-%d")
                latest_value = s.iloc[-1]
                status = "연결됨"
            else:
                latest_date = "N/A"
                latest_value = np.nan
                status = "연결 안 됨"

            connection_table.append({
                "FRED 코드": code,
                "지표명": name,
                "상태": status,
                "최근 날짜": latest_date,
                "최근 값": latest_value
            })

        connection_df = pd.DataFrame(connection_table)
        st.dataframe(connection_df, use_container_width=True)

    st.markdown("### 4. 보안 안내")

    st.info(
        "FRED API Key는 증권계좌 비밀번호는 아니지만, 공개 GitHub나 외부에 그대로 노출하지 않는 것이 좋습니다. "
        "대시보드에는 전체 키 대신 앞뒤 일부만 표시하도록 설정했습니다."
    )
st.markdown("---")
st.caption(
    "이 대시보드는 시장 내부 균열, 주도주 쏠림, 금리 압박, 신용 스트레스를 한 화면에서 확인하기 위한 모니터링 도구입니다."
)
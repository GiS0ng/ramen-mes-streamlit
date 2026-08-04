from __future__ import annotations

import pandas as pd
import streamlit as st

from repositories import dashboard as dashboard_repository


st.title("생산 현황 대시보드")
st.markdown('<p class="subtitle">재고, 생산, 출하 및 품질 핵심 지표</p>', unsafe_allow_html=True)

metrics = dashboard_repository.summary_metrics()
columns = st.columns(6)
labels = ["오늘 생산 건", "오늘 생산량", "오늘 불량", "오늘 출하량", "현재 완제품 재고", "안전재고 경보"]
for column, label, value in zip(columns, labels, metrics):
    column.metric(label, f"{value:,.0f}" if isinstance(value, (int, float)) else value)

left, right = st.columns([3, 2])
with left:
    st.subheader("최근 생산 수율")
    recent_yield = dashboard_repository.equipment_yield(days=30)
    st.dataframe(recent_yield, width="stretch", hide_index=True, height=310)

    st.subheader("설비별 생산 수율")
    equipment_yield = dashboard_repository.equipment_yield()
    if equipment_yield.empty:
        st.info("완료된 생산실적이 없어 설비별 수율을 표시할 수 없습니다.")
    else:
        chart_rows = []
        for _, row in equipment_yield.iterrows():
            for category, value in (("양품", row["양품량"]), ("불량", row["불량량"])):
                chart_rows.append(
                    {
                        "설비": row["설비"],
                        "구분": category,
                        "수량": float(value),
                        "총생산량": float(row["총생산량"]),
                        "수율": float(row["수율"]),
                    }
                )

        yield_column, defect_column = st.columns(2)
        yield_column.markdown("**양품·불량 비율**")
        yield_column.vega_lite_chart(
            pd.DataFrame(chart_rows),
            {
                "facet": {"field": "설비", "type": "nominal", "header": {"title": None, "labelFontSize": 13}},
                "columns": 1,
                "spec": {
                    "mark": {"type": "arc", "innerRadius": 42, "outerRadius": 76},
                    "encoding": {
                        "theta": {"field": "수량", "type": "quantitative", "stack": True},
                        "color": {
                            "field": "구분",
                            "type": "nominal",
                            "scale": {"domain": ["양품", "불량"], "range": ["#2E8B57", "#E45756"]},
                            "legend": {"orient": "bottom", "title": None},
                        },
                        "tooltip": [
                            {"field": "설비", "type": "nominal"},
                            {"field": "구분", "type": "nominal"},
                            {"field": "수량", "type": "quantitative", "format": ",.2f"},
                            {"field": "총생산량", "type": "quantitative", "format": ",.2f"},
                            {"field": "수율", "type": "quantitative", "format": ".2f", "title": "수율(%)"},
                        ],
                    },
                },
                "resolve": {"scale": {"theta": "independent"}},
                "config": {"view": {"stroke": None}},
            },
            width="stretch",
        )

        defects = dashboard_repository.equipment_defect_counts()
        defect_column.markdown("**설비별 불량 코드 횟수**")
        if defects.empty:
            defect_column.info("최근 30일 불량 데이터가 없습니다.")
        else:
            defect_column.vega_lite_chart(
                defects,
                {
                    "facet": {"field": "설비", "type": "nominal", "header": {"title": None, "labelFontSize": 13}},
                    "columns": 1,
                    "spec": {
                        "mark": {"type": "arc", "innerRadius": 42, "outerRadius": 76},
                        "encoding": {
                            "theta": {"field": "발생횟수", "type": "quantitative", "stack": True},
                            "color": {"field": "불량명", "type": "nominal", "legend": {"orient": "bottom", "title": None}},
                            "tooltip": [
                                {"field": "설비", "type": "nominal"},
                                {"field": "불량코드", "type": "nominal"},
                                {"field": "불량명", "type": "nominal"},
                                {"field": "발생횟수", "type": "quantitative", "format": ",.0f"},
                                {"field": "불량수량", "type": "quantitative", "format": ",.0f"},
                            ],
                        },
                    },
                    "resolve": {"scale": {"theta": "independent"}},
                    "config": {"view": {"stroke": None}},
                },
                width="stretch",
            )

with right:
    st.subheader("원재료 재고 경보")
    inventory = dashboard_repository.material_inventory()
    st.dataframe(inventory, width="stretch", hide_index=True, height=310)
    if not inventory.empty:
        chart = inventory[["품목", "총재고"]].rename(columns={"총재고": "재고"})
        st.vega_lite_chart(
            chart,
            {
                "mark": {"type": "bar", "cornerRadiusTopLeft": 4, "cornerRadiusTopRight": 4, "color": "#3B82F6"},
                "encoding": {
                    "x": {
                        "field": "품목",
                        "type": "nominal",
                        "sort": "-y",
                        "axis": {"title": None, "labelAngle": 0, "labelLimit": 110, "labelPadding": 8},
                    },
                    "y": {"field": "재고", "type": "quantitative", "axis": {"title": "현재 재고", "format": ",.0f"}},
                    "tooltip": [
                        {"field": "품목", "type": "nominal"},
                        {"field": "재고", "type": "quantitative", "format": ",.2f"},
                    ],
                },
                "height": 250,
            },
            width="stretch",
        )

from typing import Dict, List, Optional, Tuple

import streamlit as st
import pandas as pd


def to_rate(percent: float) -> float:
    return percent / 100.0


def parse_sheet_table(raw: pd.DataFrame) -> Tuple[pd.DataFrame, List[int]]:
    cleaned = raw.dropna(how="all").reset_index(drop=True)
    year_row = cleaned.iloc[0].tolist()

    years: List[int] = []
    year_cols: List[int] = []
    for i, val in enumerate(year_row):
        try:
            y = int(float(val))
            if 1900 <= y <= 2200:
                years.append(y)
                year_cols.append(i)
        except (TypeError, ValueError):
            pass

    if not years:
        raise ValueError("年(YYYY)の行が見つかりません。")

    records: List[Dict] = []
    for _, row in cleaned.iloc[1:].iterrows():
        item = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        if not item:
            continue
        values = []
        for c in year_cols:
            v = row.iloc[c] if c < len(row) else None
            try:
                values.append(float(v))
            except (TypeError, ValueError):
                values.append(0.0)
        records.append({"項目": item, **{str(y): v for y, v in zip(years, values)}})

    return pd.DataFrame(records), years


def classify_row(label: str) -> Optional[str]:
    if any(k in label for k in ["収入", "給与", "年金", "配当", "売却", "賞与"]):
        return "income"
    if any(k in label for k in ["生活費", "支出", "税", "保険", "住宅", "教育"]):
        return "expense"
    return None


def build_projection(df_items: pd.DataFrame, years: List[int], initial_asset: float, leisure_rate: float) -> pd.DataFrame:
    rows = []
    for _, r in df_items.iterrows():
        kind = classify_row(str(r["項目"]))
        if not kind:
            continue
        for y in years:
            rows.append({"年": y, "種類": kind, "金額": float(r.get(str(y), 0.0))})

    if not rows:
        raise ValueError("収入/支出として分類できる行がありません。項目名を見直してください。")

    long = pd.DataFrame(rows)
    summary = long.groupby(["年", "種類"], as_index=False)["金額"].sum().pivot(index="年", columns="種類", values="金額").fillna(0)
    summary["必須収支"] = summary.get("income", 0) - summary.get("expense", 0)

    balance = initial_asset
    out = []
    for y in years:
        income = float(summary.loc[y, "income"]) if y in summary.index and "income" in summary.columns else 0.0
        expense = float(summary.loc[y, "expense"]) if y in summary.index and "expense" in summary.columns else 0.0
        mandatory = income - expense
        leisure = max(0.0, balance * leisure_rate)
        if mandatory < 0:
            leisure = max(0.0, leisure + mandatory)
        net = mandatory - leisure
        end_balance = balance + net
        out.append({
            "年": y,
            "年初資産": balance,
            "収入合計": income,
            "支出合計": expense,
            "必須収支": mandatory,
            "余暇予算(可変)": leisure,
            "年間収支": net,
            "年末資産": end_balance,
        })
        balance = end_balance

    return pd.DataFrame(out)


def default_plan_table() -> pd.DataFrame:
    # 初期テンプレート: 一度だけ参照した数値をここに固定して使う想定
    return pd.DataFrame([
        {"項目": "給与収入", "2026": 600, "2027": 620, "2028": 620},
        {"項目": "年金収入", "2026": 0, "2027": 0, "2028": 0},
        {"項目": "基本生活費", "2026": 300, "2027": 310, "2028": 320},
        {"項目": "税・社会保険", "2026": 90, "2027": 95, "2028": 100},
    ])


def main() -> None:
    st.set_page_config(page_title="DWZ Planner", layout="wide")
    st.title("Die With Zero プランナー")
    st.caption("参照シートの値を一度取り込み、以後はこのアプリ内で都度修正するための版です。")

    c1, c2 = st.columns(2)
    with c1:
        initial_asset = st.number_input("現在の総資産", min_value=0.0, value=9944.0)
    with c2:
        leisure_rate_pct = st.slider("余暇予算比率(%)", 0.0, 10.0, 3.0, 0.1)

    st.header("1) 初期データ")
    st.write("- 方式A: 下のテンプレートを直接編集（推奨）\n- 方式B: CSVを一度だけ読み込み、その後は編集")

    uploaded = st.file_uploader("CSVを読み込む（任意）", type=["csv"])
    if uploaded is not None:
        raw = pd.read_csv(uploaded, header=None)
        items_df, years = parse_sheet_table(raw)
    else:
        items_df = default_plan_table()
        years = [int(c) for c in items_df.columns if c != "項目"]

    edited = st.data_editor(items_df, use_container_width=True, num_rows="dynamic")

    years = [int(c) for c in edited.columns if c != "項目" and str(c).isdigit()]
    years = sorted(years)
    if not years:
        st.error("年の列（例: 2026, 2027）を1つ以上作成してください。")
        st.stop()

    try:
        result = build_projection(edited, years, initial_asset, to_rate(leisure_rate_pct))
    except Exception as e:
        st.error(str(e))
        st.stop()

    st.header("2) 推計結果")
    st.line_chart(result.set_index("年")[["年末資産", "余暇予算(可変)"]])
    st.dataframe(result.style.format("{:,.0f}"), use_container_width=True)
    st.info("必要なタイミングでこの表の数値を修正して再計算してください。")


if __name__ == "__main__":
    main()

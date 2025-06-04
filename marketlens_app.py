import streamlit as st
import pandas as pd
from pathlib import Path
from internet_search import (
    search_duckduckgo,
    search_google,
    fetch_wikipedia_summary,
)


def main() -> None:
    """Render the MarketLens dashboard."""

    # App configuration must be the first Streamlit command
    st.set_page_config(page_title="MarketLens 4C", layout="wide")

    data_path = Path(__file__).parent / "sample_data.csv"

    # Load data
    uploaded_file = st.sidebar.file_uploader("Upload CSV data", type="csv")
    if uploaded_file:
        data = pd.read_csv(uploaded_file)
    else:
        data = pd.read_csv(data_path)

    # Filter by consumer group/segment
    group_options = sorted(data["Group"].unique())
    selected_groups = st.sidebar.multiselect(
        "Chọn nhóm phân khúc", group_options, default=group_options
    )
    data = data[data["Group"].isin(selected_groups)]

    # Optional web search in the sidebar
    st.sidebar.subheader("\U0001F50D Search the Web")
    query = st.sidebar.text_input("Enter search term")
    if query:
        with st.spinner("Searching..."):
            links = search_google(query)
            if not links:
                links = search_duckduckgo(query)
        if links:
            for link in links:
                st.sidebar.markdown(f"- [{link['title']}]({link['url']})")
        else:
            st.sidebar.write("No results found.")

    st.title("📊 MarketLens 4C – Market Research Dashboard")

    # Tabs for 4C
    tab1, tab2, tab3, tab4 = st.tabs([
        "📂 Category",
        "🏢 Company",
        "⚔️ Competitor",
        "🧍 Consumer",
    ])

    with tab1:
        st.header("📂 Category Analysis")
        industry = st.selectbox(
            "Chọn ngành hàng:", sorted(data["Category"].unique())
        )
        st.write(f"Bạn đang xem phân tích ngành hàng **{industry}**.")
        st.markdown(
            "**Xu hướng phát triển**, **rào cản gia nhập**, **cơ hội tăng trưởng** sẽ hiển thị ở đây."
        )
        st.text_area(
            "Dán dữ liệu ngành hàng (nếu có):",
            placeholder="Ví dụ: Báo cáo McKinsey, Vietnam Report,...",
        )
        filtered = data[data["Category"] == industry]
        st.dataframe(filtered)
        if not filtered.empty:
            st.bar_chart(filtered.groupby("Group")["Sales"].sum())

    with tab2:
        st.header("🏢 Company Analysis")
        company = st.selectbox(
            "Chọn thương hiệu:", sorted(data["Brand"].unique())
        )
        st.write(f"Đang phân tích doanh nghiệp **{company}**.")
        company_data = data[data["Brand"] == company]
        st.dataframe(company_data)
        st.markdown(
            "Hiển thị SWOT, USP, Brand Positioning, mục tiêu truyền thông gần nhất."
        )

        with st.spinner("Tìm kiếm thông tin trên Internet..."):
            summary = fetch_wikipedia_summary(company)
            links = search_google(company)
            if not links:
                links = search_duckduckgo(company)
        if summary:
            st.subheader("Thông tin từ Wikipedia")
            st.write(summary)
        if links:
            st.subheader("Kết quả tìm kiếm")
            for link in links:
                st.markdown(f"- [{link['title']}]({link['url']})")

    with tab3:
        st.header("⚔️ Competitor Analysis")
        st.write("So sánh các đối thủ cạnh tranh trong ngành.")
        brands = sorted(data["Brand"].unique())
        main_brand = st.selectbox("Thương hiệu chính:", brands, index=0)
        competitor = st.selectbox(
            "Đối thủ cạnh tranh:", brands, index=min(1, len(brands) - 1)
        )
        comparison = data[data["Brand"].isin([main_brand, competitor])]
        st.dataframe(comparison)
        st.markdown(
            f"**{main_brand}** vs **{competitor}** – so sánh định vị, truyền thông, sản phẩm, v.v."
        )

    with tab4:
        st.header("🧍 Consumer Insight")
        gen = st.selectbox("Chọn nhóm người tiêu dùng:", ["Gen Z", "Gen Y", "Gen X"])
        st.write(
            f"Bạn đang xem thông tin hành vi người tiêu dùng thuộc nhóm **{gen}**."
        )
        st.markdown(
            "Hiển thị sở thích, hành vi tiêu dùng, xu hướng nổi bật, và insight marketing."
        )
        st.text_area(
            "Dán khảo sát hoặc mô tả hành vi người dùng:",
            placeholder="Ví dụ: 67% Gen Z tin tưởng KOL/KOC...",
        )
        st.bar_chart(data[data["Category"] == "F&B"].set_index("Brand")["Sales"])


if __name__ == "__main__":
    main()

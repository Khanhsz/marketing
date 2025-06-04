import streamlit as st

# App Config
st.set_page_config(page_title="MarketLens 4C", layout="wide")

st.title("📊 MarketLens 4C – Market Research Dashboard")

# Tabs for 4C
tab1, tab2, tab3, tab4 = st.tabs(["📂 Category", "🏢 Company", "⚔️ Competitor", "🧍 Consumer"])

with tab1:
    st.header("📂 Category Analysis")
    industry = st.selectbox("Chọn ngành hàng:", ["F&B", "Fashion", "Ride-hailing", "Jewelry", "Tech", "Education"])
    st.write(f"Bạn đang xem phân tích ngành hàng **{industry}**.")
    st.markdown("**Xu hướng phát triển**, **rào cản gia nhập**, **cơ hội tăng trưởng** sẽ hiển thị ở đây.")
    st.text_area("Dán dữ liệu ngành hàng (nếu có):", placeholder="Ví dụ: Báo cáo McKinsey, Vietnam Report,...")

with tab2:
    st.header("🏢 Company Analysis")
    company = st.text_input("Nhập tên công ty:", "PNJ")
    st.write(f"Đang phân tích doanh nghiệp **{company}**.")
    st.markdown("Hiển thị SWOT, USP, Brand Positioning, mục tiêu truyền thông gần nhất.")

with tab3:
    st.header("⚔️ Competitor Analysis")
    st.write("So sánh các đối thủ cạnh tranh trong ngành.")
    main_brand = st.text_input("Thương hiệu chính:", "PNJ")
    competitor = st.text_input("Đối thủ cạnh tranh:", "DOJI")
    st.markdown(f"**{main_brand}** vs **{competitor}** – so sánh định vị, truyền thông, sản phẩm, v.v.")

with tab4:
    st.header("🧍 Consumer Insight")
    gen = st.selectbox("Chọn nhóm người tiêu dùng:", ["Gen Z", "Gen Y", "Gen X"])
    st.write(f"Bạn đang xem thông tin hành vi người tiêu dùng thuộc nhóm **{gen}**.")
    st.markdown("Hiển thị sở thích, hành vi tiêu dùng, xu hướng nổi bật, và insight marketing.")
    st.text_area("Dán khảo sát hoặc mô tả hành vi người dùng:", placeholder="Ví dụ: 67% Gen Z tin tưởng KOL/KOC...")

import streamlit as st
import pandas as pd
import re
import io

# Nạp dữ liệu vào bộ nhớ tạm (Cache) để ứng dụng chạy siêu mượt
@st.cache_data
def load_data():
    df = pd.read_csv("Master_Database_63_Tinh.csv")
    df['Search_Key'] = df['Địa chỉ CŨ'].astype(str).str.lower().str.strip()
    df['Search_Key'] = df['Search_Key'].apply(lambda x: re.sub(r'^(xã|phường|thị trấn|tp\.|thành phố|huyện|quận|tx\.|thị xã)\s+', '', x).strip())
    return df

def clean_query(text):
    if not text: return ""
    text = str(text).lower().strip()
    text = re.sub(r'^(xã|phường|thị trấn|tp\.|thành phố|huyện|quận|tx\.|thị xã)\s+', '', text)
    return text.strip()

# Thiết kế Giao diện Web
st.set_page_config(page_title="Chuyển đổi Địa chỉ", page_icon="🏛️", layout="wide")
st.title("🏛️ CÔNG CỤ TRA CỨU ĐỊA CHỈ HÀNH CHÍNH")
st.markdown("Nhập danh sách địa chỉ cũ để tra cứu. Hệ thống hỗ trợ xử lý hàng loạt và xuất file báo cáo.")

df = load_data()

# Khung chia 2 cột
col1, col2 = st.columns([1, 2])

with col1:
    input_text = st.text_area("Nhập địa chỉ cũ (mỗi địa chỉ 1 dòng):", height=250, placeholder="Ví dụ:\nxã Hà Bình\nthị trấn Chờ")
    search_button = st.button("🔍 Tra cứu tự động", type="primary", use_container_width=True)

with col2:
    if search_button:
        if input_text.strip():
            queries = [q.strip() for q in re.split(r'[,|\n]', input_text) if q.strip()]
            results = []

            for query in queries:
                query_clean = clean_query(query)
                matched = df[df['Search_Key'].str.contains(query_clean, regex=False, na=False)]

                if matched.empty:
                    results.append({"Từ khóa": query, "Tỉnh": "❌", "Địa chỉ CŨ": "-", "Địa chỉ MỚI": "Không tìm thấy", "Trạng thái": "-", "Độ tin cậy": "0%"})
                else:
                    for _, row in matched.iterrows():
                        reliability = "⚠️ Trùng tên (Check Tỉnh)" if len(matched) > 1 else "✅ Cao"
                        results.append({"Từ khóa": query, "Tỉnh": row['Tỉnh/File'], "Địa chỉ CŨ": row['Địa chỉ CŨ'], "Địa chỉ MỚI": row['Địa chỉ MỚI'], "Trạng thái": row['Trạng thái'], "Độ tin cậy": reliability})

            # Hiển thị bảng kết quả
            df_results = pd.DataFrame(results)
            st.dataframe(df_results, use_container_width=True)

            # Tạo nút tải file CSV
            csv_data = df_results.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Tải kết quả về máy (File CSV)",
                data=csv_data,
                file_name="Ket_Qua_Chuyen_Doi_Dia_Chi.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.warning("Vui lòng nhập ít nhất 1 địa chỉ để tra cứu.")
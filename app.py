import streamlit as st
import pandas as pd
import re

# ==========================================
# 1. NẠP DỮ LIỆU
# ==========================================
@st.cache_data
def load_data():
    df = pd.read_csv("Master_Database_63_Tinh.csv")
    # Giữ nguyên cụm từ "phường/xã" để tránh bị trùng lặp số
    df['Search_Key'] = df['Địa chỉ CŨ'].astype(str).str.lower().str.strip()
    return df

df = load_data()

# ==========================================
# 2. GIAO DIỆN WEB
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ", page_icon="🏛️", layout="wide")
st.title("🏛️ CÔNG CỤ TRA CỨU ĐỊA CHỈ HÀNH CHÍNH")
st.markdown("Nhập toàn bộ địa chỉ cũ vào đây. Mỗi dòng là 1 địa chỉ riêng biệt.")

col1, col2 = st.columns([1, 2])

with col1:
    input_text = st.text_area(
        "Nhập địa chỉ cũ (mỗi địa chỉ 1 dòng):", 
        height=250, 
        placeholder="Ví dụ:\n113/47/1a Võ Duy Ninh, Phường 22, Quận Bình Thạnh, TP.HCM"
    )
    search_button = st.button("🔍 Tra cứu tự động", type="primary", use_container_width=True)

with col2:
    if search_button:
        if input_text.strip():
            # CHỈ cắt bằng dấu xuống dòng (\n), tuyệt đối không cắt bằng dấu phẩy
            queries = [q.strip() for q in input_text.split('\n') if q.strip()]
            results = []
            
            for query in queries:
                query_lower = query.lower()
                
                # Logic thông minh: Kiểm tra xem "Tên Phường/Xã trong DB" CÓ XUẤT HIỆN trong "Chuỗi địa chỉ bạn gõ" không
                matched = df[df['Search_Key'].apply(lambda db_val: db_val in query_lower)]
                
                if matched.empty:
                    results.append({"Từ khóa": query, "Tỉnh": "❌", "Địa chỉ CŨ": "-", "Địa chỉ MỚI": "Không tìm thấy", "Trạng thái": "-", "Độ tin cậy": "0%"})
                else:
                    for _, row in matched.iterrows():
                        # Kiểm tra chéo xem Tỉnh trong DB có khớp với Tỉnh bạn gõ không để tăng độ chính xác
                        tinh_db = str(row['Tỉnh/File']).lower().replace('-', ' ')
                        if tinh_db in query_lower:
                            reliability = "🌟 Cực cao (Khớp cả Tỉnh)"
                        elif len(matched) > 1:
                            reliability = "⚠️ Trùng tên (Kiểm tra lại Tỉnh)"
                        else:
                            reliability = "✅ Cao"
                            
                        results.append({
                            "Từ khóa": query, 
                            "Tỉnh": row['Tỉnh/File'], 
                            "Địa chỉ CŨ": row['Địa chỉ CŨ'], 
                            "Địa chỉ MỚI": row['Địa chỉ MỚI'], 
                            "Trạng thái": row['Trạng thái'], 
                            "Độ tin cậy": reliability
                        })
            
            df_results = pd.DataFrame(results)
            st.dataframe(df_results, use_container_width=True)
            
            csv_data = df_results.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Tải kết quả về máy (File CSV)",
                data=csv_data,
                file_name="Ket_Qua_Chuyen_Doi.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.warning("Vui lòng nhập ít nhất 1 địa chỉ để tra cứu.")

import streamlit as st
import pandas as pd
import re

# ==========================================
# 1. NẠP DỮ LIỆU & SẮP XẾP THÔNG MINH
# ==========================================
@st.cache_data
def load_data():
    df = pd.read_csv("Master_Database_63_Tinh.csv")
    # THỦ THUẬT QUAN TRỌNG: Sắp xếp độ dài từ dài đến ngắn.
    # Để máy tính ưu tiên xét chữ "Phường 22" trước khi xét "Phường 2", tránh lỗi đè chữ.
    df['Length'] = df['Địa chỉ CŨ'].astype(str).apply(len)
    df = df.sort_values(by='Length', ascending=False)
    return df

df = load_data()

# ==========================================
# 2. THUẬT TOÁN "DỊCH" ĐỊA CHỈ (1 ĐỔI 1)
# ==========================================
def convert_address(query):
    query_lower = query.lower()
    new_address = query
    note = "Giữ nguyên"
    
    for _, row in df.iterrows():
        old_place = str(row['Địa chỉ CŨ'])
        old_place_lower = old_place.lower()
        
        # Nếu cụm từ cũ có nằm trong địa chỉ bạn gõ
        if old_place_lower in query_lower:
            
            # TRÁNH LỖI NHẬN DIỆN SAI (VD: Phường 2 đè vào Phường 22)
            # Kiểm tra xem ký tự ngay sát đằng sau chữ tìm được có phải là số/chữ không
            idx = query_lower.find(old_place_lower)
            end_idx = idx + len(old_place_lower)
            
            # Nếu liền sau nó là 1 chữ cái hoặc 1 con số -> Đây là từ khác, bỏ qua!
            if end_idx < len(query_lower) and query_lower[end_idx].isalnum():
                continue 
            
            # Nếu chuẩn khớp -> Tiến hành thay thế chữ ngay trên chuỗi gốc
            pattern = re.compile(re.escape(old_place), re.IGNORECASE)
            new_address = pattern.sub(str(row['Địa chỉ MỚI']), new_address)
            
            # Ghi chú lại việc đã làm
            note = f"Đổi: {old_place} ➡️ {row['Địa chỉ MỚI']}"
            if "một phần" in str(row['Trạng thái']).lower():
                note += " (⚠️ Có sáp nhập 1 phần, cần xem lại ranh giới)"
                
            break # Tìm thấy và thay thế xong là ngắt luôn, sang địa chỉ khác
            
    return new_address, note

# ==========================================
# 3. GIAO DIỆN WEB
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ", page_icon="🏛️", layout="wide")
st.title("🏛️ CÔNG CHUYỂN ĐỔI ĐỊA CHỈ HÀNH CHÍNH")
st.markdown("Nhập toàn bộ địa chỉ cũ vào bên trái. Mỗi dòng là 1 địa chỉ.")

# Chia đôi màn hình 50-50
col1, col2 = st.columns(2)

with col1:
    input_text = st.text_area(
        "Nhập địa chỉ cũ:", 
        height=300, 
        placeholder="Ví dụ:\n113/47/1a Võ Duy Ninh, Phường 22, Quận Bình Thạnh, TP.HCM\nSố 5, đường ABC, xã Yên Giả, Bắc Ninh"
    )
    search_button = st.button("🔄 Chuyển đổi ngay", type="primary", use_container_width=True)

with col2:
    if search_button:
        if input_text.strip():
            # Cắt danh sách nhập vào theo từng dòng
            queries = [q.strip() for q in input_text.split('\n') if q.strip()]
            results = []
            
            for query in queries:
                new_addr, status_note = convert_address(query)
                results.append({
                    "Địa chỉ bạn nhập": query,
                    "Địa chỉ SAU chuyển đổi": new_addr,
                    "Ghi chú": status_note
                })
            
            # Hiển thị ra bảng gọn gàng
            df_results = pd.DataFrame(results)
            st.dataframe(df_results, use_container_width=True)
            
            csv_data = df_results.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Tải file kết quả (CSV)",
                data=csv_data,
                file_name="Ket_Qua_Dia_Chi_Moi.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.warning("Vui lòng nhập địa chỉ vào ô bên trái.")

import streamlit as st
import pandas as pd
import re

# ==========================================
# 1. NẠP VÀ LÀM SẠCH DATABASE CHUẨN
# ==========================================
@st.cache_data
def load_data():
    try:
        # Đọc sheet "Tổng hợp_không merge" và lấy dòng số 2 làm tiêu đề
        df = pd.read_excel('BangChuyendoiĐVHCmoi_cu_final.xlsx', sheet_name='Tổng hợp_không merge ', header=1)
        
        # Bỏ qua các dòng trống
        df = df.dropna(subset=['Tên Xã cũ', 'Tên Xã mới'])
        
        # Hàm xóa các mã số trong ngoặc đơn, VD: "Quận 3 (770)" -> "Quận 3"
        def clean_code(text):
            if pd.isna(text): return ""
            return re.sub(r'\s*\(\d+\)', '', str(text)).strip()
            
        df['Tên Xã cũ'] = df['Tên Xã cũ'].apply(clean_code)
        df['Quận/huyện'] = df['Quận/huyện'].apply(clean_code)
        df['Tỉnh cũ'] = df['Tỉnh cũ'].apply(clean_code)
        df['Tên Xã mới'] = df['Tên Xã mới'].apply(clean_code)
        df['Tỉnh, thành phố'] = df['Tỉnh, thành phố'].apply(clean_code)
        
        # Tạo các cột normalize để thuật toán dễ so sánh
        def normalize(text):
            text = str(text).lower()
            text = re.sub(r'^(xã|phường|thị trấn|quận|huyện|thành phố|tỉnh|tp\.|tx\.|thị xã)\s+', '', text)
            return text.strip()
            
        df['xa_norm'] = df['Tên Xã cũ'].apply(normalize)
        df['huyen_norm'] = df['Quận/huyện'].apply(normalize)
        df['tinh_norm'] = df['Tỉnh cũ'].apply(normalize)
        
        # Sắp xếp độ dài Xã cũ giảm dần để ưu tiên ghép từ dài trước
        df['Length'] = df['Tên Xã cũ'].apply(len)
        df = df.sort_values(by='Length', ascending=False)
        return df
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        return pd.DataFrame()

df = load_data()

# ==========================================
# 2. THUẬT TOÁN ĐỊNH VỊ VÀ CHUYỂN ĐỔI
# ==========================================
def convert_address(query):
    if not query or df.empty: return query, "Lỗi hoặc Trống"
    query_lower = query.lower()
    
    matches = []
    for _, row in df.iterrows():
        xa_cu = str(row['Tên Xã cũ']).lower()
        if xa_cu in query_lower:
            start_idx = query_lower.find(xa_cu)
            end_idx = start_idx + len(xa_cu)
            if end_idx < len(query_lower) and query_lower[end_idx].isalnum():
                continue 
            matches.append(row)
            
    if not matches:
        return query, "Không có sáp nhập / Giữ nguyên"
        
    best_match = matches[0]
    if len(matches) > 1:
        max_score = -1
        for row in matches:
            score = 0
            if row['huyen_norm'] in query_lower: score += 2 
            if row['tinh_norm'] in query_lower: score += 1  
            if score > max_score:
                max_score = score
                best_match = row

    out_addr = query
    pattern_xa = re.compile(re.escape(best_match['Tên Xã cũ']), re.IGNORECASE)
    out_addr = pattern_xa.sub(best_match['Tên Xã mới'], out_addr)
    
    huyen_cu = best_match['Quận/huyện']
    huyen_pattern = r'[,]?\s*' + re.escape(huyen_cu) + r'\s*[,]?\s*'
    out_addr = re.sub(huyen_pattern, ', ', out_addr, flags=re.IGNORECASE)
    
    tinh_cu = best_match['Tỉnh cũ']
    tinh_moi = best_match['Tỉnh, thành phố']
    if tinh_cu.lower() != tinh_moi.lower():
        pattern_tinh = re.compile(re.escape(tinh_cu), re.IGNORECASE)
        out_addr = pattern_tinh.sub(tinh_moi, out_addr)
        
    out_addr = re.sub(r',\s*,', ',', out_addr).strip(', ')
    
    status = str(best_match['Ghi chú'])
    note = f"Đổi: {best_match['Tên Xã cũ']} ➡️ {best_match['Tên Xã mới']}"
    if "một phần" in status.lower():
        note += " (⚠️ Có sáp nhập 1 phần)"
        
    return out_addr, note

# ==========================================
# 3. GIAO DIỆN WEB
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ ĐVHC", page_icon="📍", layout="wide")
st.title("📍 CÔNG CỤ CHUYỂN ĐỔI ĐỊA CHỈ")
st.markdown("Hệ thống sử dụng Data chuẩn. Các địa chỉ thuộc diện sáp nhập sẽ được tự động đổi tên Xã/Phường và gỡ bỏ cấp Huyện.")

col1, col2 = st.columns(2)

with col1:
    input_text = st.text_area(
        "Nhập danh sách địa chỉ cũ (mỗi địa chỉ 1 dòng):", 
        height=300, 
        placeholder="Ví dụ:\n113 Võ Duy Ninh, Phường 22, Quận Bình Thạnh, Thành phố Hồ Chí Minh"
    )
    search_button = st.button("🔄 Chuyển đổi ngay", type="primary", use_container_width=True)

with col2:
    if search_button:
        if input_text.strip():
            queries = [q.strip() for q in input_text.split('\n') if q.strip()]
            results = []
            
            for query in queries:
                new_addr, status_note = convert_address(query)
                # Đã loại bỏ cột "Địa chỉ bạn nhập" theo yêu cầu
                results.append({
                    "Địa chỉ SAU chuyển đổi": new_addr,
                    "Ghi chú chi tiết": status_note
                })
            
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

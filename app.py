import streamlit as st
import pandas as pd
import re
import unicodedata

# ==========================================
# 1. NẠP VÀ LÀM SẠCH DATABASE CHUẨN
# ==========================================
@st.cache_data
def load_data():
    try:
        df = pd.read_excel('BangChuyendoiĐVHCmoi_cu_final.xlsx', sheet_name='Tổng hợp_không merge ', header=1)
        df = df.dropna(subset=['Tên Xã cũ', 'Tên Xã mới'])
        
        def clean_code(text):
            if pd.isna(text): return ""
            text = unicodedata.normalize('NFC', str(text))
            return re.sub(r'\s*\(\d+\)', '', text).strip()
            
        df['Tên Xã cũ'] = df['Tên Xã cũ'].apply(clean_code)
        
        huyen_col = 'Quận/huyện cũ' if 'Quận/huyện cũ' in df.columns else 'Quận/huyện'
        df['Huyện cũ'] = df[huyen_col].apply(clean_code)
        
        df['Tỉnh cũ'] = df['Tỉnh cũ'].apply(clean_code)
        df['Tên Xã mới'] = df['Tên Xã mới'].apply(clean_code)
        df['Tỉnh mới'] = df['Tỉnh, thành phố'].apply(clean_code)
        
        df['Length'] = df['Tên Xã cũ'].apply(len)
        df = df.sort_values(by='Length', ascending=False)
        return df
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        return pd.DataFrame()

df = load_data()

# Hàm tách bỏ các tiền tố (Quận, Huyện, Xã...) để tìm "từ lõi"
def get_core_name(name):
    if not name: return ""
    return re.sub(r'^(xã|phường|thị trấn|quận|huyện|thành phố|tỉnh|tp\.?|tx\.?|thị xã)\s+', '', name, flags=re.IGNORECASE).strip()

# ==========================================
# 2. THUẬT TOÁN ĐỊNH VỊ THÔNG MINH
# ==========================================
def convert_address(query):
    if not query or df.empty: return query, ""
    
    query_norm = unicodedata.normalize('NFC', query)
    
    query_expand = query_norm
    query_expand = re.sub(r'\b(tp\.?\s*hcm|tphcm|tp\.\s*hồ chí minh)\b', 'Thành phố Hồ Chí Minh', query_expand, flags=re.IGNORECASE)
    query_expand = re.sub(r'\b(tp\.?\s*hn|tphn|tp\.\s*hà nội)\b', 'Thành phố Hà Nội', query_expand, flags=re.IGNORECASE)
    query_expand = re.sub(r'\b(tp\.?\s*đn|tp\.\s*đà nẵng)\b', 'Thành phố Đà Nẵng', query_expand, flags=re.IGNORECASE)
    query_expand = re.sub(r'\b(tp\.?\s*hp|tp\.\s*hải phòng)\b', 'Thành phố Hải Phòng', query_expand, flags=re.IGNORECASE)
    
    query_lower = query_expand.lower()
    out_addr = query_norm
    notes = []
    
    def is_in_text(word, text):
        if not word: return False
        idx = text.find(word.lower())
        if idx == -1: return False
        end_idx = idx + len(word)
        if end_idx < len(text) and text[end_idx].isalnum():
            return False
        return True

    matches = []
    for _, row in df.iterrows():
        xa_cu = str(row['Tên Xã cũ'])
        huyen_cu = str(row['Huyện cũ'])
        
        # Bắt thông minh: Chấp nhận cả việc người dùng gõ thiếu chữ "Quận", "Huyện", "Xã"
        xa_match = is_in_text(xa_cu, query_lower) or is_in_text(get_core_name(xa_cu), query_lower)
        huyen_match = is_in_text(huyen_cu, query_lower) or is_in_text(get_core_name(huyen_cu), query_lower)
        
        if xa_match and huyen_match:
            matches.append(row)
            
    if matches:
        matched_row = matches[0]
        if len(matches) > 1:
            for m in matches:
                tinh_cu = str(m['Tỉnh cũ'])
                if is_in_text(tinh_cu, query_lower) or is_in_text(get_core_name(tinh_cu), query_lower):
                    matched_row = m
                    break
                    
        tinh_cu_db = str(matched_row['Tỉnh cũ'])
        tinh_moi_db = str(matched_row['Tỉnh mới'])
        huyen_cu_db = str(matched_row['Huyện cũ'])
        xa_cu_db = str(matched_row['Tên Xã cũ'])
        xa_moi_db = str(matched_row['Tên Xã mới'])
        
        # Xác định chính xác người dùng đã gõ chuỗi gốc hay chuỗi lõi để xóa/đổi cho đúng
        actual_tinh = tinh_cu_db if is_in_text(tinh_cu_db, query_lower) else (get_core_name(tinh_cu_db) if is_in_text(get_core_name(tinh_cu_db), query_lower) else None)
        actual_huyen = huyen_cu_db if is_in_text(huyen_cu_db, query_lower) else get_core_name(huyen_cu_db)
        actual_xa = xa_cu_db if is_in_text(xa_cu_db, query_lower) else get_core_name(xa_cu_db)
        
        # 1. Đổi Tỉnh
        if actual_tinh and tinh_cu_db.lower() != tinh_moi_db.lower():
            out_addr = re.sub(re.escape(actual_tinh), tinh_moi_db, out_addr, flags=re.IGNORECASE)
            notes.append(f"Tỉnh: {tinh_cu_db} ➡️ {tinh_moi_db}")
            
        # 2. Bỏ Huyện
        huyen_pattern = r'[,]?\s*' + re.escape(actual_huyen) + r'\s*[,]?\s*'
        out_addr = re.sub(huyen_pattern, ', ', out_addr, flags=re.IGNORECASE)
        notes.append(f"Bỏ: {huyen_cu_db}")
        
        # 3. Đổi Xã
        out_addr = re.sub(re.escape(actual_xa), xa_moi_db, out_addr, flags=re.IGNORECASE)
        notes.append(f"Xã: {xa_cu_db} ➡️ {xa_moi_db}")
        
        out_addr = re.sub(r',\s*,', ',', out_addr).strip(', ')
        
        status = str(matched_row['Ghi chú'])
        if "một phần" in status.lower():
            notes.append("(⚠️ Sáp nhập 1 phần)")
            
        return out_addr, " | ".join(notes)
    else:
        return out_addr, "Giữ nguyên"

# ==========================================
# 3. GIAO DIỆN WEB
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ ĐVHC", page_icon="📍", layout="wide")
st.title("📍 CÔNG CỤ CHUYỂN ĐỔI ĐỊA CHỈ")
st.markdown("Hệ thống tự động nhận diện thông minh: Hỗ trợ viết tắt Tỉnh/Thành, hỗ trợ gõ tắt (lược bỏ chữ Quận, Huyện, Phường, Xã).")

col1, col2 = st.columns(2)

with col1:
    input_text = st.text_area(
        "Nhập danh sách địa chỉ cũ (mỗi địa chỉ 1 dòng):", 
        height=300, 
        placeholder="Ví dụ:\n113/47/1A Võ Duy Ninh, Phường 22, Bình Thạnh, TP.HCM"
    )
    search_button = st.button("🔄 Chuyển đổi ngay", type="primary", use_container_width=True)

with col2:
    if search_button:
        if input_text.strip():
            queries = [q.strip() for q in input_text.split('\n') if q.strip()]
            results = []
            output_lines = []
            
            for query in queries:
                new_addr, status_note = convert_address(query)
                results.append({
                    "Địa chỉ SAU chuyển đổi": new_addr,
                    "Ghi chú chi tiết": status_note
                })
                output_lines.append(new_addr)
            
            output_str = "\n".join(output_lines)
            st.text_area(
                "Danh sách địa chỉ SAU chuyển đổi:", 
                value=output_str, 
                height=300
            )
            
            df_results = pd.DataFrame(results)
            csv_data = df_results.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Tải file kết quả (CSV)",
                data=csv_data,
                file_name="Ket_Qua_Dia_Chi_Moi.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary"
            )
        else:
            st.warning("Vui lòng nhập địa chỉ vào ô bên trái.")

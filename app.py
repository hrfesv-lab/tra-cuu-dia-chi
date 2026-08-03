import streamlit as st
import pandas as pd
import re

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
            return re.sub(r'\s*\(\d+\)', '', str(text)).strip()
            
        df['Tên Xã cũ'] = df['Tên Xã cũ'].apply(clean_code)
        
        huyen_col = 'Quận/huyện cũ' if 'Quận/huyện cũ' in df.columns else 'Quận/huyện'
        df['Huyện cũ'] = df[huyen_col].apply(clean_code)
        
        df['Tỉnh cũ'] = df['Tỉnh cũ'].apply(clean_code)
        df['Tên Xã mới'] = df['Tên Xã mới'].apply(clean_code)
        df['Tỉnh mới'] = df['Tỉnh, thành phố'].apply(clean_code)
        
        # Sắp xếp độ dài Xã cũ giảm dần (ưu tiên các tên dài)
        df['Length'] = df['Tên Xã cũ'].apply(len)
        df = df.sort_values(by='Length', ascending=False)
        return df
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        return pd.DataFrame()

df = load_data()

# ==========================================
# 2. THUẬT TOÁN DÒ THEO CỘT EXCEL (ROW-BASED MAPPING)
# ==========================================
def convert_address(query):
    if not query or df.empty: return query, ""
    
    query_lower = query.lower()
    out_addr = query
    notes = []
    
    # Hàm kiểm tra từ khóa an toàn (không bị đè chữ)
    def is_in_text(word, text):
        if not word: return False
        idx = text.find(word.lower())
        if idx == -1: return False
        end_idx = idx + len(word)
        if end_idx < len(text) and text[end_idx].isalnum():
            return False
        return True

    matched_row = None
    
    # BƯỚC 1: DÒ CỘT CŨ (Tìm dòng chứa đủ Tỉnh + Huyện + Xã)
    for _, row in df.iterrows():
        xa_cu = str(row['Tên Xã cũ'])
        huyen_cu = str(row['Huyện cũ'])
        tinh_cu = str(row['Tỉnh cũ'])
        
        if is_in_text(tinh_cu, query_lower) and \
           is_in_text(huyen_cu, query_lower) and \
           is_in_text(xa_cu, query_lower):
            matched_row = row
            break  # Chốt luôn dòng này, không dò thêm nữa!
            
    # BƯỚC 2: NHÌN SANG CỘT MỚI ĐỂ CHUYỂN ĐỔI
    if matched_row is not None:
        tinh_cu_real = str(matched_row['Tỉnh cũ'])
        tinh_moi_real = str(matched_row['Tỉnh mới'])
        huyen_cu_real = str(matched_row['Huyện cũ'])
        xa_cu_real = str(matched_row['Tên Xã cũ'])
        xa_moi_real = str(matched_row['Tên Xã mới'])
        
        # 1. Đổi Tỉnh cũ -> Tỉnh mới (nếu có khác biệt)
        if tinh_cu_real.lower() != tinh_moi_real.lower():
            out_addr = re.sub(re.escape(tinh_cu_real), tinh_moi_real, out_addr, flags=re.IGNORECASE)
            notes.append(f"Tỉnh: {tinh_cu_real} ➡️ {tinh_moi_real}")
            
        # 2. Cắt bỏ Quận/Huyện cũ ra khỏi câu
        huyen_pattern = r'[,]?\s*' + re.escape(huyen_cu_real) + r'\s*[,]?\s*'
        out_addr = re.sub(huyen_pattern, ', ', out_addr, flags=re.IGNORECASE)
        notes.append(f"Bỏ: {huyen_cu_real}")
        
        # 3. Đổi Xã cũ -> Xã mới
        out_addr = re.sub(re.escape(xa_cu_real), xa_moi_real, out_addr, flags=re.IGNORECASE)
        notes.append(f"Xã: {xa_cu_real} ➡️ {xa_moi_real}")
        
        # Dọn dẹp sạch sẽ các dấu phẩy thừa
        out_addr = re.sub(r',\s*,', ',', out_addr).strip(', ')
        
        status = str(matched_row['Ghi chú'])
        if "một phần" in status.lower():
            notes.append("(⚠️ Sáp nhập 1 phần)")
            
        return out_addr, " | ".join(notes)
    else:
        return out_addr, "Giữ nguyên (Không tìm thấy dòng khớp đủ Tỉnh+Huyện+Xã cũ)"

# ==========================================
# 3. GIAO DIỆN WEB
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ ĐVHC", page_icon="📍", layout="wide")
st.title("📍 CÔNG CỤ CHUYỂN ĐỔI ĐỊA CHỈ")
st.markdown("Hệ thống dò dữ liệu theo cột: Phải khớp đủ **Tỉnh + Quận/Huyện + Xã cũ** thì mới thực hiện chuyển đổi.")

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

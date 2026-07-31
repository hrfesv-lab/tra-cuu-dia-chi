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
        
        df['Length'] = df['Tên Xã cũ'].apply(len)
        df = df.sort_values(by='Length', ascending=False)
        return df
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        return pd.DataFrame()

df = load_data()

# Tạo một bảng riêng chỉ chứa danh sách Tỉnh để phục vụ Bước 1
if not df.empty:
    df_tinh = df[['Tỉnh cũ', 'Tỉnh mới']].drop_duplicates()
else:
    df_tinh = pd.DataFrame()

# ==========================================
# 2. THUẬT TOÁN THEO FLOW CHUẨN
# ==========================================
def convert_address(query):
    if not query or df.empty: return query, ""
    
    # Lưu lại chuỗi gốc viết thường để làm bộ đối chiếu (không bị ảnh hưởng khi cắt ghép)
    original_query_lower = query.lower()
    out_addr = query
    notes = []
    
    def is_in_text(word, text):
        if not word: return False
        idx = text.find(word)
        if idx == -1: return False
        end_idx = idx + len(word)
        # Chặn word boundary để "Phường 2" không đè "Phường 22"
        if end_idx < len(text) and text[end_idx].isalnum():
            return False
        return True

    # 🔥 BƯỚC 1: DÒ TỈNH CŨ -> ĐỔI TỈNH MỚI
    for _, row in df_tinh.iterrows():
        tinh_cu = str(row['Tỉnh cũ'])
        if is_in_text(tinh_cu.lower(), original_query_lower):
            tinh_moi = str(row['Tỉnh mới'])
            if tinh_cu.lower() != tinh_moi.lower():
                out_addr = re.sub(re.escape(tinh_cu), tinh_moi, out_addr, flags=re.IGNORECASE)
                notes.append(f"Tỉnh: {tinh_cu} ➡️ {tinh_moi}")
            break # Tìm thấy và xử lý xong Tỉnh thì ngắt vòng lặp

    # 🔥 BƯỚC 2: DÒ (TỈNH CŨ + HUYỆN CŨ + XÃ CŨ) -> ĐỔI XÃ MỚI
    matches = []
    for _, row in df.iterrows():
        xa_cu = str(row['Tên Xã cũ']).lower()
        huyen_cu = str(row['Huyện cũ']).lower()
        tinh_cu = str(row['Tỉnh cũ']).lower()
        
        # Bắt buộc chuỗi nhập vào phải chứa CẢ 3 yếu tố
        if is_in_text(tinh_cu, original_query_lower) and \
           is_in_text(huyen_cu, original_query_lower) and \
           is_in_text(xa_cu, original_query_lower):
            matches.append(row)
            
    if matches:
        best_match = matches[0] # Lấy kết quả đầu tiên thỏa mãn kiềng 3 chân
        
        # 2.1 - Cắt bỏ Huyện cũ (Kèm dấu phẩy)
        huyen_cu_real = best_match['Huyện cũ']
        huyen_pattern = r'[,]?\s*' + re.escape(huyen_cu_real) + r'\s*[,]?\s*'
        out_addr = re.sub(huyen_pattern, ', ', out_addr, flags=re.IGNORECASE)
        notes.append(f"Bỏ: {huyen_cu_real}")
        
        # 2.2 - Nhả ra Xã mới
        xa_cu_real = best_match['Tên Xã cũ']
        xa_moi_real = best_match['Tên Xã mới']
        out_addr = re.sub(re.escape(xa_cu_real), xa_moi_real, out_addr, flags=re.IGNORECASE)
        notes.append(f"Xã: {xa_cu_real} ➡️ {xa_moi_real}")
        
        status = str(best_match['Ghi chú'])
        if "một phần" in status.lower():
            notes.append("(⚠️ Sáp nhập 1 phần)")
            
    # Dọn dẹp dấu phẩy thừa do việc cắt chữ để lại
    out_addr = re.sub(r',\s*,', ',', out_addr).strip(', ')
    
    if not notes:
        return out_addr, "Giữ nguyên"
        
    return out_addr, " | ".join(notes)

# ==========================================
# 3. GIAO DIỆN WEB
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ ĐVHC", page_icon="📍", layout="wide")
st.title("📍 CÔNG CỤ CHUYỂN ĐỔI ĐỊA CHỈ")
st.markdown("Hệ thống yêu cầu nhập đầy đủ **Tỉnh + Huyện + Xã cũ** để đảm bảo độ chính xác tuyệt đối.")

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

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
        
        # Hàm xóa mã số trong ngoặc (Ví dụ: "Quận 3 (770)" -> "Quận 3")
        def clean_code(text):
            if pd.isna(text): return ""
            return re.sub(r'\s*\(\d+\)', '', str(text)).strip()
            
        df['Tên Xã cũ'] = df['Tên Xã cũ'].apply(clean_code)
        
        # Đề phòng tên cột Huyện bị đổi trong các phiên bản Excel khác nhau
        huyen_col = 'Quận/huyện cũ' if 'Quận/huyện cũ' in df.columns else 'Quận/huyện'
        df['Huyện cũ'] = df[huyen_col].apply(clean_code)
        
        df['Tỉnh cũ'] = df['Tỉnh cũ'].apply(clean_code)
        df['Tên Xã mới'] = df['Tên Xã mới'].apply(clean_code)
        df['Tỉnh mới'] = df['Tỉnh, thành phố'].apply(clean_code)
        
        # Sắp xếp độ dài Xã cũ giảm dần
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
    if not query or df.empty: return query, ""
    query_lower = query.lower()
    out_addr = query
    notes = []
    
    # Hàm kiểm tra từ khóa (Có chặn boundary để tránh "Phường 2" đè vào "Phường 22")
    def is_in_text(word, text):
        idx = text.find(word)
        if idx == -1: return False
        end_idx = idx + len(word)
        if end_idx < len(text) and text[end_idx].isalnum():
            return False
        return True

    # BƯỚC 1: ĐIỀU KIỆN KIÊN QUYẾT (Chuỗi nhập vào phải chứa CẢ Xã cũ VÀ Huyện cũ)
    matches = []
    for _, row in df.iterrows():
        xa_cu = str(row['Tên Xã cũ']).lower()
        huyen_cu = str(row['Huyện cũ']).lower()
        
        if is_in_text(xa_cu, query_lower) and is_in_text(huyen_cu, query_lower):
            matches.append(row)
            
    if not matches:
        return query, "Giữ nguyên (Hoặc bạn nhập thiếu Quận/Huyện cũ)"
        
    # Nếu trùng (hiếm), ưu tiên dòng khớp luôn cả Tỉnh cũ
    best_match = matches[0]
    if len(matches) > 1:
        for row in matches:
            if is_in_text(str(row['Tỉnh cũ']).lower(), query_lower):
                best_match = row
                break
                
    # BƯỚC 2: TIẾN HÀNH THAY THẾ THEO ĐÚNG FLOW
    
    # 2.1 - Check và Đổi Tỉnh (Nếu có nhập tỉnh cũ và tỉnh có đổi tên)
    tinh_cu = best_match['Tỉnh cũ']
    tinh_moi = best_match['Tỉnh mới']
    if is_in_text(tinh_cu.lower(), query_lower) and tinh_cu.lower() != tinh_moi.lower():
        out_addr = re.sub(re.escape(tinh_cu), tinh_moi, out_addr, flags=re.IGNORECASE)
        notes.append(f"Tỉnh: {tinh_cu} ➡️ {tinh_moi}")
        
    # 2.2 - Xóa Huyện cũ (Bao gồm cả các dấu phẩy thừa đứng kề nó)
    huyen_cu = best_match['Huyện cũ']
    huyen_pattern = r'[,]?\s*' + re.escape(huyen_cu) + r'\s*[,]?\s*'
    out_addr = re.sub(huyen_pattern, ', ', out_addr, flags=re.IGNORECASE)
    notes.append(f"Bỏ: {huyen_cu}")
    
    # 2.3 - Đổi Xã cũ thành Xã mới
    xa_cu = best_match['Tên Xã cũ']
    xa_moi = best_match['Tên Xã mới']
    out_addr = re.sub(re.escape(xa_cu), xa_moi, out_addr, flags=re.IGNORECASE)
    notes.append(f"Xã: {xa_cu} ➡️ {xa_moi}")
    
    # Dọn dẹp dấu phẩy bị nhân đôi (nếu có)
    out_addr = re.sub(r',\s*,', ',', out_addr).strip(', ')
    
    status = str(best_match['Ghi chú'])
    if "một phần" in status.lower():
        notes.append("(⚠️ Sáp nhập 1 phần)")
        
    return out_addr, " | ".join(notes)

# ==========================================
# 3. GIAO DIỆN WEB
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ ĐVHC", page_icon="📍", layout="wide")
st.title("📍 CÔNG CỤ CHUYỂN ĐỔI ĐỊA CHỈ")
st.markdown("Hệ thống yêu cầu nhập đầy đủ **Xã/Phường + Quận/Huyện cũ** để đảm bảo chuyển đổi chính xác 100%.")

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

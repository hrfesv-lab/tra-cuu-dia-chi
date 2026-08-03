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

# ==========================================
# 2. BỘ CÔNG CỤ "NUỐT" TIỀN TỐ AN TOÀN TUYỆT ĐỐI 
# ==========================================
# Optional (Có thể có hoặc không)
PREFIX_XA_OPT = r'(?:(?:phường|xã|thị trấn|p\.?|x\.?|tt\.?)\s*)?'
PREFIX_HUYEN_OPT = r'(?:(?:quận|huyện|thành phố|thị xã|tp\.?|q\.?|h\.?|tx\.?)\s*)?'
PREFIX_TINH_OPT = r'(?:(?:tỉnh|thành phố|tp\.?|t\.?)\s*)?'

# Mandatory (Bắt buộc phải có tiền tố)
PREFIX_XA_MAN = r'(?:(?:phường|xã|thị trấn|p\.?|x\.?|tt\.?)\s*)'
PREFIX_HUYEN_MAN = r'(?:(?:quận|huyện|thành phố|thị xã|tp\.?|q\.?|h\.?|tx\.?)\s*)'
PREFIX_TINH_MAN = r'(?:(?:tỉnh|thành phố|tp\.?|t\.?)\s*)'

def get_core_name(name):
    if not name: return ""
    return re.sub(r'^(xã|phường|thị trấn|quận|huyện|thành phố|tỉnh|tp\.?|tx\.?|thị xã)\s+', '', name, flags=re.IGNORECASE).strip()

def is_safe_match(full_name, core_name, query, prefix_man):
    query = query.lower()
    core_name = core_name.lower()
    full_name = full_name.lower()
    
    # 1. Khớp nguyên tên đầy đủ (VD: "phường 4")
    if re.search(r'(?i)\b' + re.escape(full_name) + r'(?!\w)', query): return True
        
    # 2. Khớp theo tiền tố viết tắt (VD: "p. 4")
    if re.search(r'(?i)\b' + prefix_man + re.escape(core_name) + r'(?!\w)', query): return True
        
    # 3. Khớp độc lập giữa các dấu phẩy (VD: ", 4,")
    if re.search(r'(?i)(?:^|,\s*)' + re.escape(core_name) + r'\s*(?=$|,)', query): return True
        
    # 4. Nếu KHÔNG PHẢI SỐ thì cho phép tìm tự do (Bảo vệ các số nhà như 30/4 không bị nhận nhầm)
    if not core_name.isdigit():
        if re.search(r'(?i)\b' + re.escape(core_name) + r'(?!\w)', query): return True
            
    return False

def remove_part_smart(query, core_name, prefix_opt, prefix_man):
    pattern_strict = r'(?i)(?:^|,\s*)' + prefix_opt + re.escape(core_name) + r'\s*(?=$|,)'
    out, count = re.subn(pattern_strict, '', query)
    if count > 0: return re.sub(r',\s*,', ',', out).strip(', ')
    
    pattern_prefix = r'(?i)\b' + prefix_man + re.escape(core_name) + r'(?!\w)\s*'
    out, count = re.subn(pattern_prefix, '', query)
    if count > 0: return re.sub(r',\s*,', ',', out).strip(', ')
    
    if not core_name.isdigit():
        pattern_loose = r'(?i)\b' + re.escape(core_name) + r'(?!\w)\s*'
        out = re.sub(pattern_loose, '', query)
        return re.sub(r',\s*,', ',', out).strip(', ')
        
    return query

def replace_part_smart(query, core_name, new_name, prefix_opt, prefix_man):
    pattern_strict = r'(?i)(^|,\s*)' + prefix_opt + re.escape(core_name) + r'\s*(?=$|,)'
    out, count = re.subn(pattern_strict, lambda m: f"{m.group(1)}{new_name}", query)
    if count > 0: return out
    
    pattern_prefix = r'(?i)\b' + prefix_man + re.escape(core_name) + r'(?!\w)'
    out, count = re.subn(pattern_prefix, new_name, query)
    if count > 0: return out
    
    if not core_name.isdigit():
        pattern_loose = r'(?i)\b' + re.escape(core_name) + r'(?!\w)'
        return re.sub(pattern_loose, new_name, query)
        
    return query

# ==========================================
# 3. THUẬT TOÁN ĐỊNH VỊ 
# ==========================================
def convert_address(query):
    if not query or df.empty: return query, ""
    
    query_norm = unicodedata.normalize('NFC', query)
    query_expand = query_norm
    query_expand = re.sub(r'\b(tp\.?\s*hcm|tphcm|tp\.\s*hồ chí minh)\b', 'Thành phố Hồ Chí Minh', query_expand, flags=re.IGNORECASE)
    query_expand = re.sub(r'\b(tp\.?\s*hn|tphn|tp\.\s*hà nội)\b', 'Thành phố Hà Nội', query_expand, flags=re.IGNORECASE)
    query_expand = re.sub(r'\b(tp\.?\s*đn|tp\.\s*đà nẵng)\b', 'Thành phố Đà Nẵng', query_expand, flags=re.IGNORECASE)
    query_expand = re.sub(r'\b(tp\.?\s*hp|tp\.\s*hải phòng)\b', 'Thành phố Hải Phòng', query_expand, flags=re.IGNORECASE)
    
    out_addr = query_norm
    notes = []
    
    matches = []
    for _, row in df.iterrows():
        xa_cu = str(row['Tên Xã cũ'])
        huyen_cu = str(row['Huyện cũ'])
        
        xa_core = get_core_name(xa_cu)
        huyen_core = get_core_name(huyen_cu)
        
        xa_match = is_safe_match(xa_cu, xa_core, query_expand, PREFIX_XA_MAN)
        huyen_match = is_safe_match(huyen_cu, huyen_core, query_expand, PREFIX_HUYEN_MAN)
        
        if xa_match and huyen_match:
            matches.append(row)
            
    if matches:
        matched_row = matches[0]
        if len(matches) > 1:
            for m in matches:
                tinh_cu = str(m['Tỉnh cũ'])
                tinh_core = get_core_name(tinh_cu)
                if is_safe_match(tinh_cu, tinh_core, query_expand, PREFIX_TINH_MAN):
                    matched_row = m
                    break
                    
        tinh_cu_db = str(matched_row['Tỉnh cũ'])
        tinh_moi_db = str(matched_row['Tỉnh mới'])
        huyen_cu_db = str(matched_row['Huyện cũ'])
        xa_cu_db = str(matched_row['Tên Xã cũ'])
        xa_moi_db = str(matched_row['Tên Xã mới'])
        
        tinh_core = get_core_name(tinh_cu_db)
        huyen_core = get_core_name(huyen_cu_db)
        xa_core = get_core_name(xa_cu_db)
        
        # 1. Đổi Tỉnh
        if is_safe_match(tinh_cu_db, tinh_core, query_expand, PREFIX_TINH_MAN) and tinh_cu_db.lower() != tinh_moi_db.lower():
            out_addr = replace_part_smart(out_addr, tinh_core, tinh_moi_db, PREFIX_TINH_OPT, PREFIX_TINH_MAN)
            notes.append(f"Tỉnh: {tinh_cu_db} ➡️ {tinh_moi_db}")
            
        # 2. Bỏ Huyện 
        out_addr = remove_part_smart(out_addr, huyen_core, PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
        notes.append(f"Bỏ: {huyen_cu_db}")
        
        # 3. Đổi Xã 
        out_addr = replace_part_smart(out_addr, xa_core, xa_moi_db, PREFIX_XA_OPT, PREFIX_XA_MAN)
        notes.append(f"Xã: {xa_cu_db} ➡️ {xa_moi_db}")
        
        status = str(matched_row['Ghi chú'])
        if "một phần" in status.lower():
            notes.append("(⚠️ Sáp nhập 1 phần)")
            
        return out_addr, " | ".join(notes)
    else:
        return out_addr, "Không có sáp nhập / Giữ nguyên"

# ==========================================
# 4. GIAO DIỆN WEB
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ ĐVHC", page_icon="📍", layout="wide")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

st.title("📍 CÔNG CỤ CHUYỂN ĐỔI ĐỊA CHỈ")
st.markdown("Hệ thống thông minh chống nhận nhầm số nhà/tên đường (VD: 30/4) và loại bỏ sạch tiền tố thừa.")

col1, col2 = st.columns(2)

with col1:
    input_text = st.text_area(
        "Nhập danh sách địa chỉ cũ (mỗi địa chỉ 1 dòng):", 
        height=300, 
        placeholder="Ví dụ:\n156, Đường 30/4, phường 2, Thành phố Sóc Trăng, Tỉnh Sóc Trăng"
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

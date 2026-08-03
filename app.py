import streamlit as st
import pandas as pd
import re
import unicodedata

# ==========================================
# 1. CÀI ĐẶT TRANG & NẠP DỮ LIỆU
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ (Pro)", page_icon="📍", layout="wide")

# Ẩn menu nguồn nhưng GIỮ LẠI trạng thái Running
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

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

# KHỞI TẠO BỘ NHỚ TẠM (Để lưu dữ liệu truyền giữa các trang)
if 'app_data' not in st.session_state:
    st.session_state.app_data = []

# ==========================================
# 2. CÔNG CỤ XỬ LÝ LÕI (CỦA BẢN V3)
# ==========================================
PREFIX_XA_OPT = r'(?:(?:phường|xã|thị trấn|p\.?|x\.?|tt\.?)\s*)?'
PREFIX_HUYEN_OPT = r'(?:(?:quận|huyện|thành phố|thị xã|tp\.?|q\.?|h\.?|tx\.?)\s*)?'
PREFIX_TINH_OPT = r'(?:(?:tỉnh|thành phố|tp\.?|t\.?)\s*)?'

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
    if re.search(r'(?i)\b' + re.escape(full_name) + r'(?!\w)', query): return True
    if re.search(r'(?i)\b' + prefix_man + re.escape(core_name) + r'(?!\w)', query): return True
    if re.search(r'(?i)(?:^|,\s*)' + re.escape(core_name) + r'\s*(?=$|,)', query): return True
    if not core_name.isdigit():
        if re.search(r'(?i)\b' + re.escape(core_name) + r'(?!\w)', query): return True
    return False

def remove_part_smart(query, full_name, core_name, prefix_opt, prefix_man):
    pattern_full = r'(?i)(?:^|,\s*)' + re.escape(full_name) + r'\s*(?=$|,)'
    out, count = re.subn(pattern_full, '', query, count=1)
    if count > 0: return re.sub(r',\s*,', ',', out).strip(', ')
    pattern_full_loose = r'(?i)\b' + re.escape(full_name) + r'(?!\w)\s*'
    out, count = re.subn(pattern_full_loose, '', query, count=1)
    if count > 0: return re.sub(r',\s*,', ',', out).strip(', ')
    pattern_strict = r'(?i)(?:^|,\s*)' + prefix_opt + re.escape(core_name) + r'\s*(?=$|,)'
    out, count = re.subn(pattern_strict, '', query, count=1)
    if count > 0: return re.sub(r',\s*,', ',', out).strip(', ')
    pattern_prefix = r'(?i)\b' + prefix_man + re.escape(core_name) + r'(?!\w)\s*'
    out, count = re.subn(pattern_prefix, '', query, count=1)
    if count > 0: return re.sub(r',\s*,', ',', out).strip(', ')
    if not core_name.isdigit():
        pattern_loose = r'(?i)\b' + re.escape(core_name) + r'(?!\w)\s*'
        out = re.sub(pattern_loose, '', query, count=1)
        return re.sub(r',\s*,', ',', out).strip(', ')
    return query

def replace_part_smart(query, full_name, core_name, new_name, prefix_opt, prefix_man):
    pattern_full = r'(?i)(^|,\s*)' + re.escape(full_name) + r'\s*(?=$|,)'
    out, count = re.subn(pattern_full, lambda m: f"{m.group(1)}{new_name}", query, count=1)
    if count > 0: return out
    pattern_full_loose = r'(?i)\b' + re.escape(full_name) + r'(?!\w)'
    out, count = re.subn(pattern_full_loose, new_name, query, count=1)
    if count > 0: return out
    pattern_strict = r'(?i)(^|,\s*)' + prefix_opt + re.escape(core_name) + r'\s*(?=$|,)'
    out, count = re.subn(pattern_strict, lambda m: f"{m.group(1)}{new_name}", query, count=1)
    if count > 0: return out
    pattern_prefix = r'(?i)\b' + prefix_man + re.escape(core_name) + r'(?!\w)'
    out, count = re.subn(pattern_prefix, new_name, query, count=1)
    if count > 0: return out
    if not core_name.isdigit():
        pattern_loose = r'(?i)\b' + re.escape(core_name) + r'(?!\w)'
        return re.sub(pattern_loose, new_name, query, count=1)
    return query

def auto_convert_address(query):
    if not query or df.empty: return query, "", True
    query_norm = unicodedata.normalize('NFC', query)
    query_norm = re.sub(r'(?i)(^|\s|,)(phường|p\.|p|quận|q\.|q|huyện|h\.|h|xã|x\.|x|thị trấn|tt\.|tt)(\s*)0+(\d+)\b', r'\1\2\3\4', query_norm)
    query_expand = query_norm
    query_expand = re.sub(r'\b(tp\.?\s*hcm|tphcm|tp\.\s*hồ chí minh)\b', 'Thành phố Hồ Chí Minh', query_expand, flags=re.IGNORECASE)
    
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
                    
        tinh_cu_db, tinh_moi_db = str(matched_row['Tỉnh cũ']), str(matched_row['Tỉnh mới'])
        huyen_cu_db = str(matched_row['Huyện cũ'])
        xa_cu_db, xa_moi_db = str(matched_row['Tên Xã cũ']), str(matched_row['Tên Xã mới'])
        
        tinh_core, huyen_core, xa_core = get_core_name(tinh_cu_db), get_core_name(huyen_cu_db), get_core_name(xa_cu_db)
        
        if is_safe_match(tinh_cu_db, tinh_core, query_expand, PREFIX_TINH_MAN) and tinh_cu_db.lower() != tinh_moi_db.lower():
            out_addr = replace_part_smart(out_addr, tinh_cu_db, tinh_core, tinh_moi_db, PREFIX_TINH_OPT, PREFIX_TINH_MAN)
            notes.append(f"Tỉnh ➡️ {tinh_moi_db}")
            
        out_addr = remove_part_smart(out_addr, huyen_cu_db, huyen_core, PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
        notes.append(f"Bỏ Huyện")
        
        out_addr = replace_part_smart(out_addr, xa_cu_db, xa_core, xa_moi_db, PREFIX_XA_OPT, PREFIX_XA_MAN)
        notes.append(f"Xã ➡️ {xa_moi_db}")
        
        return out_addr, " | ".join(notes), False
    else:
        return out_addr, "Không thể tự động nhận diện (LỖI)", True

def force_convert_address(query, matched_row):
    # Hàm áp dụng thay thế thủ công khi người dùng đã chọn bằng Droplist
    tinh_cu_db, tinh_moi_db = str(matched_row['Tỉnh cũ']), str(matched_row['Tỉnh mới'])
    huyen_cu_db = str(matched_row['Huyện cũ'])
    xa_cu_db, xa_moi_db = str(matched_row['Tên Xã cũ']), str(matched_row['Tên Xã mới'])
    
    tinh_core, huyen_core, xa_core = get_core_name(tinh_cu_db), get_core_name(huyen_cu_db), get_core_name(xa_cu_db)
    
    out_addr = query
    out_addr = replace_part_smart(out_addr, tinh_cu_db, tinh_core, tinh_moi_db, PREFIX_TINH_OPT, PREFIX_TINH_MAN)
    out_addr = remove_part_smart(out_addr, huyen_cu_db, huyen_core, PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
    out_addr = replace_part_smart(out_addr, xa_cu_db, xa_core, xa_moi_db, PREFIX_XA_OPT, PREFIX_XA_MAN)
    return out_addr

# ==========================================
# 3. GIAO DIỆN WEB (PHÂN 3 TRANG)
# ==========================================
st.sidebar.title("📌 Menu Chức Năng")
menu = st.sidebar.radio("Chọn thao tác:", [
    "1. Chuyển đổi hàng loạt 🚀", 
    "2. Trạm xử lý thủ công 🛠️", 
    "3. Tải file hoàn chỉnh 📥"
])

# ----------------- TRANG 1 -----------------
if menu == "1. Chuyển đổi hàng loạt 🚀":
    st.title("🚀 CÔNG CỤ CHUYỂN ĐỔI TỰ ĐỘNG")
    st.markdown("Dán danh sách địa chỉ của bạn vào đây. Hệ thống sẽ tự động gọt số 0, tránh số nhà (30/4) và loại bỏ tiền tố.")
    
    input_text = st.text_area("Nhập danh sách địa chỉ cũ (mỗi địa chỉ 1 dòng):", height=250)
    
    if st.button("🔄 Bắt đầu chạy", type="primary"):
        if input_text.strip():
            queries = [q.strip() for q in input_text.split('\n') if q.strip()]
            st.session_state.app_data = [] # Reset data
            
            progress_bar = st.progress(0)
            for i, query in enumerate(queries):
                new_addr, note, is_err = auto_convert_address(query)
                st.session_state.app_data.append({
                    'id': i, 'old': query, 'new': new_addr, 'notes': note, 'is_error': is_err
                })
                progress_bar.progress((i + 1) / len(queries))
            
            err_count = sum(1 for d in st.session_state.app_data if d['is_error'])
            if err_count > 0:
                st.warning(f"⚠️ Xử lý xong! Có **{err_count}** địa chỉ không thể tự động nhận diện (do lịch sử đổi tên/sai chính tả). Vui lòng sang tab **'2. Trạm xử lý thủ công'** để giải quyết nốt.")
            else:
                st.success("🎉 Xuất sắc! 100% địa chỉ đã được chuyển đổi thành công. Hãy sang tab **'3. Tải file hoàn chỉnh'** để lấy kết quả.")
        else:
            st.warning("Vui lòng nhập dữ liệu!")

# ----------------- TRANG 2 -----------------
elif menu == "2. Trạm xử lý thủ công 🛠️":
    st.title("🛠️ TRẠM KIỂM DUYỆT THỦ CÔNG")
    error_items = [d for d in st.session_state.app_data if d['is_error']]
    
    if not st.session_state.app_data:
        st.info("💡 Bạn chưa chạy dữ liệu ở Tab 1. Vui lòng quay lại Tab 1 để nhập địa chỉ.")
    elif not error_items:
        st.success("✨ Không có địa chỉ nào bị lỗi! Bạn có thể tải file kết quả ở Tab 3.")
    else:
        st.markdown(f"**Còn {len(error_items)} địa chỉ cần bạn hỗ trợ định hướng:**")
        error_dict = {item['id']: item['old'] for item in error_items}
        
        # Chọn địa chỉ lỗi
        selected_id = st.selectbox("👉 Chọn địa chỉ cần sửa:", options=list(error_dict.keys()), format_func=lambda x: error_dict[x])
        selected_item = next(item for item in st.session_state.app_data if item['id'] == selected_id)
        
        st.markdown(f"> **Địa chỉ gốc:** `{selected_item['old']}`")
        st.markdown("---")
        st.markdown("#### Hỗ trợ AI tìm vị trí đúng trong Database:")
        
        # DROPLIST LIÊN HOÀN (Cascading Dropdowns)
        col1, col2, col3 = st.columns(3)
        tinh_list = sorted(df['Tỉnh cũ'].dropna().unique().tolist())
        
        with col1:
            tinh_sel = st.selectbox("1. Thuộc Tỉnh/Thành nào?", ["-- Chọn --"] + tinh_list)
        
        huyen_sel, xa_sel = "-- Chọn --", "-- Chọn --"
        if tinh_sel != "-- Chọn --":
            huyen_list = sorted(df[df['Tỉnh cũ'] == tinh_sel]['Huyện cũ'].dropna().unique().tolist())
            with col2:
                huyen_sel = st.selectbox("2. Thuộc Quận/Huyện nào?", ["-- Chọn --"] + huyen_list)
                
            if huyen_sel != "-- Chọn --":
                xa_list = sorted(df[(df['Tỉnh cũ'] == tinh_sel) & (df['Huyện cũ'] == huyen_sel)]['Tên Xã cũ'].dropna().unique().tolist())
                with col3:
                    xa_sel = st.selectbox("3. Thuộc Phường/Xã nào?", ["-- Chọn --"] + xa_list)
                    
        # Khi User chọn đủ 3 cấp, hệ thống tự động bốc dòng lệnh ra và sửa
        if xa_sel != "-- Chọn --":
            exact_row = df[(df['Tỉnh cũ'] == tinh_sel) & (df['Huyện cũ'] == huyen_sel) & (df['Tên Xã cũ'] == xa_sel)].iloc[0]
            suggested_addr = force_convert_address(selected_item['old'], exact_row)
            
            st.markdown("---")
            st.markdown("#### Xem trước & Xác nhận kết quả")
            # Text input để user có quyền sửa lần cuối nếu AI cắt chuỗi chưa ưng ý
            final_edit = st.text_input("📝 Địa chỉ sau khi sáp nhập sẽ là (Bạn có thể gõ để sửa nếu muốn):", value=suggested_addr)
            
            col_btn1, col_btn2 = st.columns([1, 4])
            with col_btn1:
                if st.button("💾 Xác nhận & Lưu", type="primary"):
                    for d in st.session_state.app_data:
                        if d['id'] == selected_id:
                            d['new'] = final_edit
                            d['is_error'] = False
                            d['notes'] = "✅ Đã sửa thủ công"
                    st.rerun()
            with col_btn2:
                if st.button("⚠️ Địa chỉ này OK, Giữ nguyên"):
                    for d in st.session_state.app_data:
                        if d['id'] == selected_id:
                            d['new'] = selected_item['old']
                            d['is_error'] = False
                            d['notes'] = "Không có sáp nhập"
                    st.rerun()

# ----------------- TRANG 3 -----------------
elif menu == "3. Tải file hoàn chỉnh 📥":
    st.title("📥 TRẠM XUẤT DỮ LIỆU")
    if not st.session_state.app_data:
        st.info("💡 Bạn chưa có dữ liệu nào. Hãy quay lại Tab 1 nhé.")
    else:
        err_count = sum(1 for d in st.session_state.app_data if d['is_error'])
        if err_count > 0:
            st.warning(f"Vẫn còn {err_count} địa chỉ lỗi chưa được sửa. Bạn có chắc muốn tải file bây giờ không?")
            
        df_results = pd.DataFrame(st.session_state.app_data)
        # Ẩn cột id và is_error đi cho đẹp
        df_display = df_results[['old', 'new', 'notes']].rename(columns={
            'old': 'Địa chỉ GỐC', 
            'new': 'Địa chỉ SAU chuyển đổi', 
            'notes': 'Ghi chú'
        })
        
        st.dataframe(df_display, use_container_width=True)
        
        csv_data = df_display.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="⬇️ Tải file kết quả (CSV)",
            data=csv_data,
            file_name="Ket_Qua_Dia_Chi_Moi_Hoan_Chinh.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary"
        )

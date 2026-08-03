import streamlit as st
import pandas as pd
import re
import unicodedata

# ==========================================
# 1. CÀI ĐẶT TRANG & CSS GIAO DIỆN
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ ĐVHC", page_icon="📍", layout="wide")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            .stTabs [data-baseweb="tab-list"] {
                gap: 24px;
            }
            .stTabs [data-baseweb="tab"] {
                height: 50px;
                white-space: pre-wrap;
                background-color: #f0f2f6;
                border-radius: 4px 4px 0px 0px;
                gap: 1px;
                padding-top: 10px;
                padding-bottom: 10px;
                padding-left: 20px;
                padding-right: 20px;
            }
            .stTabs [aria-selected="true"] {
                background-color: #ffffff;
                border-bottom: 2px solid #ff4b4b;
                color: #ff4b4b;
                font-weight: bold;
            }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

if 'app_data' not in st.session_state:
    st.session_state.app_data = []

# ==========================================
# 2. NẠP DỮ LIỆU & TIỀN XỬ LÝ (TỐI ƯU TỐC ĐỘ)
# ==========================================
def get_core_name(name):
    if not name: return ""
    return re.sub(r'^(xã|phường|thị trấn|quận|huyện|thành phố|tỉnh|tp\.?|tx\.?|thị xã)\s+', '', str(name), flags=re.IGNORECASE).strip()

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
        
        # Đọc Huyện cũ
        huyen_col = 'Quận/huyện cũ' if 'Quận/huyện cũ' in df.columns else 'Quận/huyện'
        df['Huyện cũ'] = df[huyen_col].apply(clean_code)
        
        # Đọc Huyện mới (Nếu trống thì tự hiểu là Huyện không đổi)
        if 'Quận/huyện mới' in df.columns:
            df['Huyện mới'] = df['Quận/huyện mới'].apply(lambda x: clean_code(x) if pd.notna(x) else "")
        else:
            df['Huyện mới'] = df['Huyện cũ']
            
        df['Tỉnh cũ'] = df['Tỉnh cũ'].apply(clean_code)
        df['Tên Xã mới'] = df['Tên Xã mới'].apply(clean_code)
        df['Tỉnh mới'] = df['Tỉnh, thành phố'].apply(clean_code)
        
        df['xa_core'] = df['Tên Xã cũ'].apply(get_core_name)
        df['huyen_core'] = df['Huyện cũ'].apply(get_core_name)
        df['tinh_core'] = df['Tỉnh cũ'].apply(get_core_name)
        
        df['xa_core_lower'] = df['xa_core'].str.lower()
        df['huyen_core_lower'] = df['huyen_core'].str.lower()
        
        records = df.to_dict('records')
        return df, records
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        return pd.DataFrame(), []

df, db_records = load_data()

PREFIX_XA_OPT = r'(?:(?:phường|xã|thị trấn|p\.?|x\.?|tt\.?)\s*)?'
PREFIX_HUYEN_OPT = r'(?:(?:quận|huyện|thành phố|thị xã|tp\.?|q\.?|h\.?|tx\.?)\s*)?'
PREFIX_TINH_OPT = r'(?:(?:tỉnh|thành phố|tp\.?|t\.?)\s*)?'

PREFIX_XA_MAN = r'(?:(?:phường|xã|thị trấn|p\.?|x\.?|tt\.?)\s*)'
PREFIX_HUYEN_MAN = r'(?:(?:quận|huyện|thành phố|thị xã|tp\.?|q\.?|h\.?|tx\.?)\s*)'
PREFIX_TINH_MAN = r'(?:(?:tỉnh|thành phố|tp\.?|t\.?)\s*)'

def normalize_special_cases(query):
    if not query: return query
    query = unicodedata.normalize('NFC', query)
    query = re.sub(r'(?i)(^|\s|,)(phường|p\.|p|quận|q\.|q|huyện|h\.|h|xã|x\.|x|thị trấn|tt\.|tt)(\s*)0+(\d+)\b', r'\1\2\3\4', query)
    query = re.sub(r'\b(tp\.?\s*hcm|tphcm|tp\.\s*hồ chí minh)\b', 'Thành phố Hồ Chí Minh', query, flags=re.IGNORECASE)
    query = re.sub(r'\b(tp\.?\s*hn|tphn|tp\.\s*hà nội)\b', 'Thành phố Hà Nội', query, flags=re.IGNORECASE)
    query = re.sub(r'\b(tp\.?\s*đn|tp\.\s*đà nẵng)\b', 'Thành phố Đà Nẵng', query, flags=re.IGNORECASE)
    query = re.sub(r'\b(tp\.?\s*hp|tp\.\s*hải phòng)\b', 'Thành phố Hải Phòng', query, flags=re.IGNORECASE)
    query = re.sub(r'(?i)\b(tỉnh\s*)?thừa thiên(\s*[-]?\s*)huế\b', 'Thành phố Huế', query)
    return query

def get_match_score(full_name, core_name, query, prefix_man):
    query = query.lower()
    core_name = core_name.lower()
    full_name = full_name.lower()
    
    if re.search(r'(?i)\b' + re.escape(full_name) + r'(?!\w)', query): return 4
    if re.search(r'(?i)\b' + prefix_man + re.escape(core_name) + r'(?!\w)', query): return 3
    if re.search(r'(?i)(?:^|,\s*)' + re.escape(core_name) + r'\s*(?=$|,)', query): return 2
    if not core_name.isdigit():
        if re.search(r'(?i)\b' + re.escape(core_name) + r'(?!\w)', query): return 1
    return 0

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
    if not query or not db_records: return query, "", True
    
    query_expand = normalize_special_cases(query)
    query_lower = query_expand.lower()
    out_addr = query_expand
    
    notes = []
    matches = []
    
    for row in db_records:
        if row['xa_core_lower'] not in query_lower or row['huyen_core_lower'] not in query_lower:
            continue
            
        xa_cu = str(row['Tên Xã cũ'])
        huyen_cu = str(row['Huyện cũ'])
        xa_core = row['xa_core']
        huyen_core = row['huyen_core']
        
        xa_score = get_match_score(xa_cu, xa_core, query_expand, PREFIX_XA_MAN)
        huyen_score = get_match_score(huyen_cu, huyen_core, query_expand, PREFIX_HUYEN_MAN)
        
        if xa_score > 0 and huyen_score > 0:
            tinh_cu = str(row['Tỉnh cũ'])
            tinh_core = row['tinh_core']
            tinh_score = get_match_score(tinh_cu, tinh_core, query_expand, PREFIX_TINH_MAN)
            
            total_score = xa_score + huyen_score + (tinh_score if tinh_score > 0 else 0)
            matches.append({'row': row, 'score': total_score})
            
    if matches:
        matches.sort(key=lambda x: x['score'], reverse=True)
        matched_row = matches[0]['row']
                    
        tinh_cu_db, tinh_moi_db = str(matched_row['Tỉnh cũ']), str(matched_row['Tỉnh mới'])
        huyen_cu_db = str(matched_row['Huyện cũ'])
        huyen_moi_db = str(matched_row['Huyện mới'])
        xa_cu_db, xa_moi_db = str(matched_row['Tên Xã cũ']), str(matched_row['Tên Xã mới'])
        
        tinh_core, huyen_core, xa_core = matched_row['tinh_core'], matched_row['huyen_core'], matched_row['xa_core']
        
        # 1. Tỉnh
        if get_match_score(tinh_cu_db, tinh_core, query_expand, PREFIX_TINH_MAN) > 0 and tinh_cu_db.lower() != tinh_moi_db.lower():
            out_addr = replace_part_smart(out_addr, tinh_cu_db, tinh_core, tinh_moi_db, PREFIX_TINH_OPT, PREFIX_TINH_MAN)
            notes.append(f"Tỉnh ➡️ {tinh_moi_db}")
        else:
            out_addr = replace_part_smart(out_addr, tinh_cu_db, tinh_core, tinh_moi_db, PREFIX_TINH_OPT, PREFIX_TINH_MAN)
            
        # 2. Huyện (Khắc phục triệt để lỗi "Bỏ Huyện" vô lý)
        if huyen_moi_db == "":
            out_addr = remove_part_smart(out_addr, huyen_cu_db, huyen_core, PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
            notes.append(f"Bỏ Huyện")
        elif huyen_cu_db.lower() != huyen_moi_db.lower():
            out_addr = replace_part_smart(out_addr, huyen_cu_db, huyen_core, huyen_moi_db, PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
            notes.append(f"Huyện ➡️ {huyen_moi_db}")
        else:
            # Nếu Huyện không đổi, chỉ chuẩn hóa tên chứ không bỏ
            out_addr = replace_part_smart(out_addr, huyen_cu_db, huyen_core, huyen_moi_db, PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
            
        # 3. Xã
        if xa_cu_db.lower() != xa_moi_db.lower():
            out_addr = replace_part_smart(out_addr, xa_cu_db, xa_core, xa_moi_db, PREFIX_XA_OPT, PREFIX_XA_MAN)
            notes.append(f"Xã ➡️ {xa_moi_db}")
        else:
            out_addr = replace_part_smart(out_addr, xa_cu_db, xa_core, xa_moi_db, PREFIX_XA_OPT, PREFIX_XA_MAN)
            
        # Dọn dấu phẩy thừa
        out_addr = re.sub(r',\s*,', ',', out_addr).strip(', ')
        return out_addr, " | ".join(notes) if notes else "Chuẩn hóa", False
    else:
        return out_addr, "Lỗi/Không tìm thấy vị trí", True

def force_convert_address(query, matched_row):
    out_addr = normalize_special_cases(query)
    
    tinh_cu_db, tinh_moi_db = str(matched_row['Tỉnh cũ']), str(matched_row['Tỉnh mới'])
    huyen_cu_db = str(matched_row['Huyện cũ'])
    huyen_moi_db = str(matched_row['Huyện mới'])
    xa_cu_db, xa_moi_db = str(matched_row['Tên Xã cũ']), str(matched_row['Tên Xã mới'])
    
    tinh_core, huyen_core, xa_core = matched_row['tinh_core'], matched_row['huyen_core'], matched_row['xa_core']
    
    if tinh_cu_db.lower() != tinh_moi_db.lower():
        out_addr = replace_part_smart(out_addr, tinh_cu_db, tinh_core, tinh_moi_db, PREFIX_TINH_OPT, PREFIX_TINH_MAN)
        
    if huyen_moi_db == "":
        out_addr = remove_part_smart(out_addr, huyen_cu_db, huyen_core, PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
    else:
        out_addr = replace_part_smart(out_addr, huyen_cu_db, huyen_core, huyen_moi_db, PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
        
    out_addr = replace_part_smart(out_addr, xa_cu_db, xa_core, xa_moi_db, PREFIX_XA_OPT, PREFIX_XA_MAN)
    
    out_addr = re.sub(r',\s*,', ',', out_addr).strip(', ')
    return out_addr

# ==========================================
# 3. GIAO DIỆN WEB (TABS NGANG)
# ==========================================
st.title("📍 CÔNG CỤ CHUYỂN ĐỔI ĐỊA CHỈ")
st.markdown("Hệ thống thông minh tự động gỡ bỏ các tiền tố (P., Q., TP...) khi sáp nhập.")

tab1, tab2, tab3 = st.tabs(["🚀 1. Chuyển đổi hàng loạt", "🛠️ 2. Chuyển đổi đơn lẻ", "📥 3. Trạm xuất dữ liệu"])

with tab1:
    col_input, col_info = st.columns([2, 1])
    
    with col_input:
        input_text = st.text_area(
            "Nhập danh sách địa chỉ cũ (mỗi địa chỉ 1 dòng):", 
            height=250,
            placeholder="Ví dụ:\n36/8 Đường Số 11, Phường 11, Gò Vấp, TP. Hồ Chí Minh"
        )
        if st.button("🔄 Bắt đầu chạy tự động", type="primary", use_container_width=True):
            if input_text.strip():
                queries = [q.strip() for q in input_text.split('\n') if q.strip()]
                st.session_state.app_data = [] 
                
                progress_bar = st.progress(0)
                for i, query in enumerate(queries):
                    new_addr, note, is_err = auto_convert_address(query)
                    st.session_state.app_data.append({
                        'id': i, 'old': query, 'new': new_addr, 'notes': note, 'is_error': is_err
                    })
                    progress_bar.progress((i + 1) / len(queries))
                
                st.rerun() 
            else:
                st.warning("Vui lòng nhập dữ liệu!")

    with col_info:
        st.info("💡 **Hướng dẫn:**\n\n1. Dán danh sách vào ô bên trái.\n2. Bấm chạy tự động.\n3. Nếu có địa chỉ lỗi, hãy sang Tab 2 để sửa thủ công.\n4. Sang Tab 3 để tải File CSV.")
        
        if st.session_state.app_data:
            err_count = sum(1 for d in st.session_state.app_data if d['is_error'])
            succ_count = len(st.session_state.app_data) - err_count
            st.success(f"✅ Đã xử lý tự động: **{succ_count}**")
            if err_count > 0:
                st.error(f"⚠️ Cần sửa tay: **{err_count}** (Xem Tab 2)")

with tab2:
    error_items = [d for d in st.session_state.app_data if d['is_error']]
    
    if not st.session_state.app_data:
        st.info("👈 Hãy chạy tính năng chuyển đổi hàng loạt ở Tab 1 trước nhé!")
    elif not error_items:
        st.success("🎉 Mọi địa chỉ đều đã được AI nhận diện thành công! Không có lỗi nào cần sửa.")
    else:
        error_dict = {item['id']: item['old'] for item in error_items}
        selected_id = st.selectbox(f"🚨 Đang có {len(error_items)} địa chỉ cần bạn hỗ trợ. Vui lòng chọn:", options=list(error_dict.keys()), format_func=lambda x: error_dict[x])
        selected_item = next(item for item in st.session_state.app_data if item['id'] == selected_id)
        
        st.markdown(f"**📍 Địa chỉ gốc:** `{selected_item['old']}`")
        st.markdown("---")
        st.markdown("### 🔍 Hỗ trợ AI tìm vị trí đúng trong Database:")
        
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
                    
        if xa_sel != "-- Chọn --":
            exact_row = df[(df['Tỉnh cũ'] == tinh_sel) & (df['Huyện cũ'] == huyen_sel) & (df['Tên Xã cũ'] == xa_sel)].iloc[0]
            suggested_addr = force_convert_address(selected_item['old'], exact_row)
            
            st.markdown("---")
            st.markdown("### 👀 Xem trước & Xác nhận kết quả")
            final_edit = st.text_input("✍️ Địa chỉ sau khi sáp nhập sẽ là (Bạn có thể gõ để sửa lại):", value=suggested_addr)
            
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
                if st.button("⚠️ Giữ nguyên địa chỉ gốc"):
                    for d in st.session_state.app_data:
                        if d['id'] == selected_id:
                            d['new'] = selected_item['old']
                            d['is_error'] = False
                            d['notes'] = "Giữ nguyên"
                    st.rerun()

with tab3:
    if not st.session_state.app_data:
        st.info("👈 Hãy chạy tính năng chuyển đổi hàng loạt ở Tab 1 trước nhé!")
    else:
        err_count = sum(1 for d in st.session_state.app_data if d['is_error'])
        if err_count > 0:
            st.warning(f"⚠️ Chú ý: Vẫn còn {err_count} địa chỉ lỗi chưa được sửa ở Tab 2. Bạn có chắc muốn tải file bây giờ không?")
            
        df_results = pd.DataFrame(st.session_state.app_data)
        df_display = df_results[['old', 'new', 'notes']].rename(columns={
            'old': 'Địa chỉ GỐC', 
            'new': 'Địa chỉ SAU chuyển đổi', 
            'notes': 'Ghi chú'
        })
        
        st.dataframe(df_display, use_container_width=True)
        
        csv_data = df_display.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="⬇️ TẢI FILE KẾT QUẢ HOÀN CHỈNH (CSV)",
            data=csv_data,
            file_name="Ket_Qua_Dia_Chi_Moi.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary"
        )

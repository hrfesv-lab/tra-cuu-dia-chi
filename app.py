import streamlit as st
import pandas as pd
import re
import unicodedata
import google.generativeai as genai

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
# 2. NẠP DỮ LIỆU & TIỀN XỬ LÝ (CHIỀU CŨ -> MỚI)
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
        huyen_col = 'Quận/huyện cũ' if 'Quận/huyện cũ' in df.columns else 'Quận/huyện'
        df['Huyện cũ'] = df[huyen_col].apply(clean_code)
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

def normalize_formatting(query):
    if not query: return query
    query = unicodedata.normalize('NFC', query)
    query = re.sub(r'(?i)(^|\s|,)(phường|p\.|p|quận|q\.|q|huyện|h\.|h|xã|x\.|x|thị trấn|tt\.|tt)(\s*)0+(\d+)\b', r'\1\2\3\4', query)
    query = re.sub(r'(?i)\b(tỉnh\s*)?thừa thiên(\s*[-]?\s*)huế\b', 'Thành phố Huế', query)
    return query

def normalize_for_search(query):
    query = re.sub(r'\b(tp\.?\s*hcm|tphcm|tp\.\s*hồ chí minh)\b', 'Thành phố Hồ Chí Minh', query, flags=re.IGNORECASE)
    query = re.sub(r'\b(tp\.?\s*hn|tphn|tp\.\s*hà nội)\b', 'Thành phố Hà Nội', query, flags=re.IGNORECASE)
    query = re.sub(r'\b(tp\.?\s*đn|tp\.\s*đà nẵng)\b', 'Thành phố Đà Nẵng', query, flags=re.IGNORECASE)
    query = re.sub(r'\b(tp\.?\s*hp|tp\.\s*hải phòng)\b', 'Thành phố Hải Phòng', query, flags=re.IGNORECASE)
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
    out_addr = normalize_formatting(query)
    query_search = normalize_for_search(out_addr)
    query_lower = query_search.lower()
    
    notes = []
    matches = []
    
    for row in db_records:
        if row['xa_core_lower'] not in query_lower or row['huyen_core_lower'] not in query_lower:
            continue
        xa_cu = str(row['Tên Xã cũ'])
        huyen_cu = str(row['Huyện cũ'])
        xa_core = row['xa_core']
        huyen_core = row['huyen_core']
        
        xa_score = get_match_score(xa_cu, xa_core, query_search, PREFIX_XA_MAN)
        huyen_score = get_match_score(huyen_cu, huyen_core, query_search, PREFIX_HUYEN_MAN)
        
        if xa_score > 0 and huyen_score > 0:
            tinh_cu = str(row['Tỉnh cũ'])
            tinh_core = row['tinh_core']
            tinh_score = get_match_score(tinh_cu, tinh_core, query_search, PREFIX_TINH_MAN)
            total_score = xa_score + huyen_score + (tinh_score if tinh_score > 0 else 0)
            matches.append({'row': row, 'score': total_score})
            
    if matches:
        matches.sort(key=lambda x: x['score'], reverse=True)
        matched_row = matches[0]['row']
                    
        tinh_cu_db, tinh_moi_db = str(matched_row['Tỉnh cũ']), str(matched_row['Tỉnh mới'])
        huyen_cu_db = str(matched_row['Huyện cũ'])
        xa_cu_db, xa_moi_db = str(matched_row['Tên Xã cũ']), str(matched_row['Tên Xã mới'])
        tinh_core, huyen_core, xa_core = matched_row['tinh_core'], matched_row['huyen_core'], matched_row['xa_core']
        
        if get_match_score(tinh_cu_db, tinh_core, query_search, PREFIX_TINH_MAN) > 0 and tinh_cu_db.lower() != tinh_moi_db.lower():
            out_addr = replace_part_smart(out_addr, tinh_cu_db, tinh_core, tinh_moi_db, PREFIX_TINH_OPT, PREFIX_TINH_MAN)
            notes.append(f"Tỉnh ➡️ {tinh_moi_db}")
            
        out_addr = remove_part_smart(out_addr, huyen_cu_db, huyen_core, PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
        notes.append(f"Bỏ Huyện")
            
        if xa_cu_db.lower() != xa_moi_db.lower():
            out_addr = replace_part_smart(out_addr, xa_cu_db, xa_core, xa_moi_db, PREFIX_XA_OPT, PREFIX_XA_MAN)
            notes.append(f"Xã ➡️ {xa_moi_db}")
        
        return out_addr, " | ".join(notes) if notes else "Chuẩn hóa", False
    else:
        return out_addr, "Lỗi/Không tìm thấy vị trí", True

def force_convert_address(query, matched_row):
    tinh_cu_db = str(matched_row['Tỉnh cũ'])
    huyen_cu_db = str(matched_row['Huyện cũ'])
    xa_cu_db = str(matched_row['Tên Xã cũ'])
    tinh_core = matched_row['tinh_core']
    huyen_core = matched_row['huyen_core']
    xa_core = matched_row['xa_core']

    parts = [p.strip() for p in query.split(',') if p.strip()]
    local_parts = []
    
    for p in parts:
        p_lower = p.lower()
        p_core = get_core_name(p).lower()
        is_admin = False
        
        if re.match(r'(?i)^(phường|xã|thị trấn|p\.|x\.|tt\.|quận|huyện|thành phố|thị xã|q\.|h\.|tx\.|tp\.|tỉnh|t\.)\b', p):
            is_admin = True
        elif re.match(r'(?i)^(p|x|tt|q|h|tx|tp)\s*\d+', p):
            is_admin = True
        elif xa_core and p_core == xa_core.lower():
            is_admin = True
        elif huyen_core and p_core == huyen_core.lower():
            is_admin = True
        elif tinh_core and p_core == tinh_core.lower():
            is_admin = True
        elif re.search(r'\b(hcm|hồ chí minh|hà nội|đà nẵng|hải phòng)\b', p_lower):
            is_admin = True
            
        if not is_admin:
            local_parts.append(p)
        else:
            break 
            
    prefix = ", ".join(local_parts)
    
    original_tinh = parts[-1] if parts else tinh_cu_db
    tinh_to_use = tinh_cu_db
    if re.search(r'(?i)\b(hcm|hồ chí minh|hà nội|đà nẵng|hải phòng|tỉnh|thành phố|tp\.?|t\.?)\b', original_tinh):
        tinh_to_use = original_tinh
        
    if prefix:
        fixed_old_query = f"{prefix}, {xa_cu_db}, {huyen_cu_db}, {tinh_to_use}"
    else:
        fixed_old_query = f"{xa_cu_db}, {huyen_cu_db}, {tinh_to_use}"
        
    out_addr = fixed_old_query
    tinh_moi_db = str(matched_row['Tỉnh mới'])
    xa_moi_db = str(matched_row['Tên Xã mới'])
    
    if tinh_cu_db.lower() != tinh_moi_db.lower():
        out_addr = replace_part_smart(out_addr, tinh_cu_db, tinh_core, tinh_moi_db, PREFIX_TINH_OPT, PREFIX_TINH_MAN)
    out_addr = remove_part_smart(out_addr, huyen_cu_db, huyen_core, PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
    if xa_cu_db.lower() != xa_moi_db.lower():
        out_addr = replace_part_smart(out_addr, xa_cu_db, xa_core, xa_moi_db, PREFIX_XA_OPT, PREFIX_XA_MAN)
    
    out_addr = re.sub(r',\s*,', ',', out_addr).strip(', ')
    return out_addr

# ==========================================
# 3. GIAO DIỆN WEB (TABS NGANG)
# ==========================================
st.title("📍 CÔNG CỤ CHUYỂN ĐỔI ĐỊA CHỈ")
st.markdown("Hệ thống thông minh tự động gỡ bỏ các tiền tố (P., Q., TP...) khi sáp nhập.")

tab1, tab2, tab3, tab4 = st.tabs(["🚀 1. Chuyển đổi hàng loạt", "🛠️ 2. Chuyển đổi đơn lẻ", "📥 3. Trạm xuất dữ liệu", "⏪ 4. AI Dịch ngược (Mới -> Cũ)"])

with tab1:
    col_input, col_info = st.columns([2, 1])
    with col_input:
        input_text = st.text_area(
            "Nhập danh sách địa chỉ cũ (mỗi địa chỉ 1 dòng):", 
            height=250,
            placeholder="Ví dụ:\n182 Phạm Phú Thứ, Phường 4, Quận 6, TP. HCM"
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
        st.info("💡 **Hướng dẫn:**\n\n1. Dán danh sách vào ô bên trái.\n2. Bấm chạy tự động.\n3. Sang Tab 2 nếu có lỗi.\n4. Sang Tab 3 tải CSV.")
        if st.session_state.app_data:
            err_count = sum(1 for d in st.session_state.app_data if d['is_error'])
            succ_count = len(st.session_state.app_data) - err_count
            st.success(f"✅ Đã xử lý: **{succ_count}**")
            if err_count > 0:
                st.error(f"⚠️ Lỗi: **{err_count}** (Xem Tab 2)")

with tab2:
    error_items = [d for d in st.session_state.app_data if d['is_error']]
    if not st.session_state.app_data:
        st.info("👈 Hãy chạy tính năng chuyển đổi hàng loạt ở Tab 1 trước nhé!")
    elif not error_items:
        st.success("🎉 Mọi địa chỉ đều đã được AI nhận diện thành công!")
    else:
        error_dict = {item['id']: item['old'] for item in error_items}
        selected_id = st.selectbox(f"🚨 Đang có {len(error_items)} địa chỉ cần bạn hỗ trợ:", options=list(error_dict.keys()), format_func=lambda x: error_dict[x])
        selected_item = next(item for item in st.session_state.app_data if item['id'] == selected_id)
        
        st.markdown(f"**📍 Địa chỉ gốc:** `{selected_item['old']}`")
        st.markdown("---")
        
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
            final_edit = st.text_input("✍️ Xem trước & Chỉnh sửa kết quả:", value=suggested_addr)
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
            st.warning(f"⚠️ Chú ý: Vẫn còn {err_count} địa chỉ lỗi chưa được sửa ở Tab 2.")
            
        df_results = pd.DataFrame(st.session_state.app_data)
        df_display = df_results[['old', 'new', 'notes']].rename(columns={
            'old': 'Địa chỉ GỐC', 
            'new': 'Địa chỉ SAU chuyển đổi', 
            'notes': 'Ghi chú'
        })
        st.dataframe(df_display, use_container_width=True)
        csv_data = df_display.to_csv(index=False, encoding='utf-8-sig')
        st.download_button("⬇️ TẢI FILE KẾT QUẢ CSV", data=csv_data, file_name="Ket_Qua_Dia_Chi.csv", mime="text/csv", use_container_width=True, type="primary")

# ==========================================
# ==========================================
# 4. TAB 4: TÍCH HỢP AI GEMINI (MỚI -> CŨ)
# ==========================================
with tab4:
    st.markdown("### 🤖 Trợ lý AI: Dịch ngược địa chỉ MỚI về CŨ")
    st.info("Hệ thống tự động quét các phiên bản AI mà API Key của bạn hỗ trợ để tránh lỗi kết nối.")
    
    col_ai_1, col_ai_2 = st.columns([1, 2])
    
    with col_ai_1:
        api_key_input = st.text_input("🔑 Nhập Google Gemini API Key:", type="password")
    
    # Chỉ khi bạn nhập API Key thì mới hiện tiếp các phần sau
    if api_key_input:
        try:
            genai.configure(api_key=api_key_input)
            
            # TỰ ĐỘNG DÒ TÌM MODEL MÀ API KEY HỖ TRỢ
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name.replace("models/", ""))
            
            if available_models:
                with col_ai_2:
                    selected_model = st.selectbox("🧠 Chọn phiên bản AI (Hệ thống tự nhận diện):", available_models)
                
                new_address_input = st.text_input(
                    "📍 Nhập địa chỉ cần tra cứu:", 
                    placeholder="K29/2 Nguyễn Như Đãi, Tổ 20, Phường Cẩm Lệ, TP Đà Nẵng"
                )
                
                if st.button("⏪ Yêu cầu AI dịch ngược", type="primary"):
                    if not new_address_input:
                        st.warning("Vui lòng nhập địa chỉ cần tra cứu!")
                    else:
                        with st.spinner(f"Đang kết nối não bộ {selected_model}..."):
                            try:
                                model = genai.GenerativeModel(selected_model)
                                prompt = f"""
                                Bạn là chuyên gia bản đồ và địa giới hành chính Việt Nam. Nhiệm vụ: Tra ngược địa chỉ MỚI về địa chỉ CŨ (phiên bản trước sáp nhập 2023-2025).

                                Địa chỉ đầu vào (có thể bị mâu thuẫn/gõ sai): "{new_address_input}"
                                
                                NGUYÊN TẮC SUY LUẬN BẮT BUỘC (Đọc kỹ):
                                1. Xử lý mâu thuẫn: Nếu địa chỉ có sự mâu thuẫn (VD: Phường A ở Tỉnh B nhưng người dùng gõ Tỉnh C), BẮT BUỘC phải ưu tiên giữ nguyên các đơn vị CẤP NHỎ (Khu phố, Đường, Phường) để làm chuẩn, từ đó sửa lại CẤP LỚN (Quận/Huyện, Tỉnh) cho đúng. (Ví dụ: Thấy Ninh Chữ thì phải tự biết đó là Ninh Thuận và sửa lại tỉnh).
                                2. Khung thời gian: Chỉ xét lịch sử sáp nhập trong khoảng 2023-2025. Không lùi về các năm như 2005, 1997...
                                3. Format trả về 1 dòng duy nhất: [Số nhà/Đường/Khu phố], [Phường/Xã CŨ], [Quận/Huyện CŨ], [Tỉnh/Thành phố CŨ].
                                4. Dòng tiếp theo ghi: "Giải thích: [Nêu ngắn gọn lý do sửa lỗi Tỉnh/Huyện hoặc tình trạng sáp nhập]"
                                """
                                
                                response = model.generate_content(prompt)
                                st.success("🎉 Kết quả suy luận từ AI:")
                                st.write(response.text)
                                
                            except Exception as e:
                                st.error(f"Lỗi khi chạy model {selected_model}: {e}")
            else:
                st.error("API Key của bạn hợp lệ nhưng không được cấp quyền sử dụng bất kỳ model tạo văn bản nào của Google.")
                
        except Exception as e:
            st.error(f"Lỗi kết nối với API Key: {e}")

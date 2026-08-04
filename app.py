import streamlit as st
import pandas as pd
import re
import unicodedata
import google.generativeai as genai
import time
import json
from streamlit_option_menu import option_menu

# ==========================================
# 1. CÀI ĐẶT TRANG
# ==========================================
st.set_page_config(page_title="Công cụ Chuyển đổi Địa chỉ", page_icon="📍", layout="wide")

hide_st_style = """
    <style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    .stTextArea textarea, .stTextInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 10px !important;
    }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# Khởi tạo Session State
if 'app_data_excel' not in st.session_state: st.session_state.app_data_excel = []
if 'app_data_ai' not in st.session_state: st.session_state.app_data_ai = []
if 'ai_cache' not in st.session_state: st.session_state.ai_cache = {}

# ==========================================
# 2. HÀM XỬ LÝ EXCEL (CŨ -> MỚI)
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
        return df, df.to_dict('records')
    except Exception:
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
    return query

def get_match_score(full_name, core_name, query, prefix_man):
    query, core_name, full_name = query.lower(), core_name.lower(), full_name.lower()
    if re.search(r'(?i)\b' + re.escape(full_name) + r'(?!\w)', query): return 4
    if re.search(r'(?i)\b' + prefix_man + re.escape(core_name) + r'(?!\w)', query): return 3
    if re.search(r'(?i)(?:^|,\s*)' + re.escape(core_name) + r'\s*(?=$|,)', query): return 2
    if not core_name.isdigit() and re.search(r'(?i)\b' + re.escape(core_name) + r'(?!\w)', query): return 1
    return 0

def remove_part_smart(query, full_name, core_name, prefix_opt, prefix_man):
    for pattern in [r'(?i)(?:^|,\s*)' + re.escape(full_name) + r'\s*(?=$|,)', 
                    r'(?i)\b' + re.escape(full_name) + r'(?!\w)\s*',
                    r'(?i)(?:^|,\s*)' + prefix_opt + re.escape(core_name) + r'\s*(?=$|,)',
                    r'(?i)\b' + prefix_man + re.escape(core_name) + r'(?!\w)\s*']:
        out, count = re.subn(pattern, '', query, count=1)
        if count > 0: return re.sub(r',\s*,', ',', out).strip(', ')
    if not core_name.isdigit():
        out = re.sub(r'(?i)\b' + re.escape(core_name) + r'(?!\w)\s*', '', query, count=1)
        return re.sub(r',\s*,', ',', out).strip(', ')
    return query

def replace_part_smart(query, full_name, core_name, new_name, prefix_opt, prefix_man):
    for pattern in [r'(?i)(^|,\s*)' + re.escape(full_name) + r'\s*(?=$|,)', r'(?i)(^|,\s*)' + prefix_opt + re.escape(core_name) + r'\s*(?=$|,)']:
        out, count = re.subn(pattern, lambda m: f"{m.group(1)}{new_name}", query, count=1)
        if count > 0: return out
    for pattern in [r'(?i)\b' + re.escape(full_name) + r'(?!\w)', r'(?i)\b' + prefix_man + re.escape(core_name) + r'(?!\w)']:
        out, count = re.subn(pattern, new_name, query, count=1)
        if count > 0: return out
    if not core_name.isdigit(): return re.sub(r'(?i)\b' + re.escape(core_name) + r'(?!\w)', new_name, query, count=1)
    return query

def auto_convert_address(query):
    if not query or not db_records: return query, "", True
    out_addr = normalize_formatting(query)
    query_search = normalize_for_search(out_addr)
    query_lower = query_search.lower()
    notes, matches = [], []
    
    for row in db_records:
        if row['xa_core_lower'] not in query_lower or row['huyen_core_lower'] not in query_lower: continue
        xa_score = get_match_score(str(row['Tên Xã cũ']), row['xa_core'], query_search, PREFIX_XA_MAN)
        huyen_score = get_match_score(str(row['Huyện cũ']), row['huyen_core'], query_search, PREFIX_HUYEN_MAN)
        if xa_score > 0 and huyen_score > 0:
            tinh_score = get_match_score(str(row['Tỉnh cũ']), row['tinh_core'], query_search, PREFIX_TINH_MAN)
            matches.append({'row': row, 'score': xa_score + huyen_score + (tinh_score if tinh_score > 0 else 0)})
            
    if matches:
        matches.sort(key=lambda x: x['score'], reverse=True)
        row = matches[0]['row']
        tinh_cu, tinh_moi = str(row['Tỉnh cũ']), str(row['Tỉnh mới'])
        xa_cu, xa_moi = str(row['Tên Xã cũ']), str(row['Tên Xã mới'])
        huyen_cu = str(row['Huyện cũ'])
        
        if get_match_score(tinh_cu, row['tinh_core'], query_search, PREFIX_TINH_MAN) > 0 and tinh_cu.lower() != tinh_moi.lower():
            out_addr = replace_part_smart(out_addr, tinh_cu, row['tinh_core'], tinh_moi, PREFIX_TINH_OPT, PREFIX_TINH_MAN)
            notes.append(f"Tỉnh ➡️ {tinh_moi}")
        out_addr = remove_part_smart(out_addr, huyen_cu, row['huyen_core'], PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
        notes.append("Bỏ Huyện")
        if xa_cu.lower() != xa_moi.lower():
            out_addr = replace_part_smart(out_addr, xa_cu, row['xa_core'], xa_moi, PREFIX_XA_OPT, PREFIX_XA_MAN)
            notes.append(f"Xã ➡️ {xa_moi}")
        return out_addr, " | ".join(notes), False
    return out_addr, "Lỗi/Không tìm thấy vị trí", True

def force_convert_address(query, row):
    parts = [p.strip() for p in query.split(',') if p.strip()]
    local_parts = []
    for p in parts:
        p_core, p_lower = get_core_name(p).lower(), p.lower()
        is_admin = False
        if re.match(r'(?i)^(phường|xã|thị trấn|p\.|x\.|tt\.|quận|huyện|thành phố|thị xã|q\.|h\.|tx\.|tp\.|tỉnh|t\.)\b', p) or \
           re.match(r'(?i)^(p|x|tt|q|h|tx|tp)\s*\d+', p) or \
           (row['xa_core'] and p_core == row['xa_core'].lower()) or \
           (row['huyen_core'] and p_core == row['huyen_core'].lower()) or \
           (row['tinh_core'] and p_core == row['tinh_core'].lower()) or \
           re.search(r'\b(hcm|hồ chí minh|hà nội|đà nẵng|hải phòng)\b', p_lower):
            is_admin = True
        if not is_admin: local_parts.append(p)
        else: break
            
    prefix = ", ".join(local_parts)
    tinh_to_use = parts[-1] if parts and re.search(r'(?i)\b(hcm|hồ chí minh|hà nội|đà nẵng|hải phòng|tỉnh|thành phố|tp\.?|t\.?)\b', parts[-1]) else str(row['Tỉnh cũ'])
    out_addr = f"{prefix}, {row['Tên Xã cũ']}, {row['Huyện cũ']}, {tinh_to_use}" if prefix else f"{row['Tên Xã cũ']}, {row['Huyện cũ']}, {tinh_to_use}"
    
    if str(row['Tỉnh cũ']).lower() != str(row['Tỉnh mới']).lower():
        out_addr = replace_part_smart(out_addr, str(row['Tỉnh cũ']), row['tinh_core'], str(row['Tỉnh mới']), PREFIX_TINH_OPT, PREFIX_TINH_MAN)
    out_addr = remove_part_smart(out_addr, str(row['Huyện cũ']), row['huyen_core'], PREFIX_HUYEN_OPT, PREFIX_HUYEN_MAN)
    if str(row['Tên Xã cũ']).lower() != str(row['Tên Xã mới']).lower():
        out_addr = replace_part_smart(out_addr, str(row['Tên Xã cũ']), row['xa_core'], str(row['Tên Xã mới']), PREFIX_XA_OPT, PREFIX_XA_MAN)
    
    return re.sub(r',\s*,', ',', out_addr).strip(', ')

# ==========================================
# 3. HÀM XỬ LÝ AI (MỚI -> CŨ)
# ==========================================
def process_batch_with_intelligence(model, address_list, batch_size=5):
    all_results = {}
    uncached_addresses = []
    
    for addr in address_list:
        if addr in st.session_state.ai_cache:
            all_results[addr] = st.session_state.ai_cache[addr]
        else:
            uncached_addresses.append(addr)
            
    if not uncached_addresses: return all_results
    
    batches = [uncached_addresses[i:i + batch_size] for i in range(0, len(uncached_addresses), batch_size)]
    progress_bar = st.progress(0, text="Đang kết nối AI...")
    
    for idx, batch in enumerate(batches):
        # BỎ HOÀN TOÀN YÊU CẦU GIẢI THÍCH TRONG PROMPT
        prompt = f"""
        Bạn là chuyên gia địa giới hành chính Việt Nam. Tra ngược danh sách địa chỉ MỚI sau đây về địa chỉ CŨ (trước sáp nhập 2025).
        Danh sách:
        {json.dumps(batch, ensure_ascii=False)}
        
        Luật suy luận:
        - Ưu tiên cấp nhỏ (Đường/Khu phố) để sửa lỗi cấp lớn.
        - Nếu địa chỉ chỉ có "Tổ/Khu phố" + "Quận/Huyện" (thiếu tên Đường/Phường), hãy trả về kết quả là: "LỖI: Thiếu dữ liệu đường/phường".
        - Trả về DUY NHẤT một chuỗi JSON hợp lệ. Key là địa chỉ gốc, value là CHUỖI ĐỊA CHỈ HOÀN CHỈNH.
        - TUYỆT ĐỐI KHÔNG thêm giải thích hay ký tự đặc biệt. 
        - Format value chuẩn: "[Số nhà/Đường], [Phường/Xã cũ], [Quận/Huyện cũ], [Tỉnh/Thành phố]".
        """
        
        max_retries, delay = 3, 2
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                text_res = response.text.strip()
                if text_res.startswith("```json"): text_res = text_res[7:-3].strip()
                elif text_res.startswith("

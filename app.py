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
    .ref-box {
        background-color: #e7f5ff;
        border-left: 4px solid #1c7ed6;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# Khởi tạo Session State
if 'app_data_excel' not in st.session_state: st.session_state.app_data_excel = []
if 'app_data_ai' not in st.session_state: st.session_state.app_data_ai = []
if 'ai_cache' not in st.session_state: st.session_state.ai_cache = {}

# ==========================================
# 2. HÀM XỬ LÝ EXCEL & CHUẨN HÓA LÕI (CŨ -> MỚI)
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
        
        # Lõi ĐVHC Cũ
        df['xa_core'] = df['Tên Xã cũ'].apply(get_core_name)
        df['huyen_core'] = df['Huyện cũ'].apply(get_core_name)
        df['tinh_core'] = df['Tỉnh cũ'].apply(get_core_name)
        df['xa_core_lower'] = df['xa_core'].str.lower()
        df['huyen_core_lower'] = df['huyen_core'].str.lower()
        
        # Lõi ĐVHC Mới (Dành cho chiều Mới -> Cũ)
        df['xa_moi_core'] = df['Tên Xã mới'].apply(get_core_name)
        df['tinh_moi_core'] = df['Tỉnh mới'].apply(get_core_name)
        df['xa_moi_core_lower'] = df['xa_moi_core'].str.lower()
        df['tinh_moi_core_lower'] = df['tinh_moi_core'].str.lower()
        
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
# 3. LUỒNG THUẬT TOÁN BÓC TÁCH -> DÒ CỘT MỚI -> KHOANH VÙNG AI (MỚI -> CŨ)
# ==========================================

def extract_address_components(addr):
    """ Bóc tách địa chỉ MỚI do người dùng nhập thành 4 phần rõ rệt """
    parts = [p.strip() for p in addr.split(',') if p.strip()]
    tinh, huyen, xa, prefix_parts = "", "", "", []
    
    for p in reversed(parts):
        p_lower = p.lower()
        # Tìm Tỉnh/Thành Mới
        if not tinh and (re.search(r'^(tỉnh|thành phố|tp\.)\s+', p_lower) or p_lower in ['hà nội', 'hồ chí minh', 'đà nẵng', 'hải phòng', 'cần thơ']):
            tinh = p
            continue
        # Tìm Quận/Huyện Mới
        if not huyen and re.search(r'^(quận|huyện|thị xã|thành phố|q\.|h\.|tx\.)\s+', p_lower):
            huyen = p
            continue
        # Tìm Xã/Phường Mới
        if not xa and (re.search(r'^(phường|xã|thị trấn|p\.|x\.|tt\.)\s+', p_lower) or re.match(r'^(p|x|tt)\s*\d+', p_lower)):
            xa = p
            continue
        
        prefix_parts.insert(0, p)
        
    # Cứu hộ nếu người dùng gõ chuỗi ngắn thiếu Prefix
    if not tinh and not huyen and not xa:
        if len(parts) >= 3:
            tinh, huyen, xa = parts[-1], parts[-2], parts[-3]
            prefix_parts = parts[:-3]
        elif len(parts) == 2:
            tinh, xa = parts[-1], parts[-2]
        else:
            prefix_parts = parts
            
    prefix = ", ".join(prefix_parts)
    return prefix, get_core_name(xa), get_core_name(huyen), get_core_name(tinh)


def smart_ai_lookup(model, address_list, batch_size=5):
    results = {}
    uncached_addresses = []
    
    for addr in address_list:
        if addr in st.session_state.ai_cache:
            results[addr] = st.session_state.ai_cache[addr]
        else:
            uncached_addresses.append(addr)
            
    if not uncached_addresses: return results
    
    batches = [uncached_addresses[i:i + batch_size] for i in range(0, len(uncached_addresses), batch_size)]
    progress_bar = st.progress(0, text="Đang bóc tách Lõi Mới & Dò Excel...")
    
    for idx, batch in enumerate(batches):
        prompt_data = {}
        direct_results = {}
        
        for addr in batch:
            # BƯỚC 1: Bóc tách Input người dùng
            norm_addr = normalize_formatting(normalize_for_search(addr))
            prefix, xa_in, huyen_in, tinh_in = extract_address_components(norm_addr)
            xa_in_lower = xa_in.lower()
            tinh_in_lower = tinh_in.lower()
            
            # BƯỚC 2: Dò thẳng vào Cột XÃ MỚI & TỈNH MỚI trong Excel
            matched_records = []
            for row in db_records:
                score = 0
                db_xa_moi = row['xa_moi_core_lower']
                db_tinh_moi = row['tinh_moi_core_lower']
                
                # Khớp Tên Xã Mới
                if xa_in_lower and xa_in_lower == db_xa_moi:
                    score += 10
                    # Tăng điểm nếu khớp Tỉnh Mới
                    if tinh_in_lower and tinh_in_lower == db_tinh_moi:
                        score += 5
                
                if score > 0:
                    matched_records.append({'row': row, 'score': score})
                    
            # Nếu người dùng gõ sai Xã, tìm "mềm" (Fuzzy match) trong cột Xã Mới
            if not matched_records and xa_in_lower:
                for row in db_records:
                    db_xa_moi = row['xa_moi_core_lower']
                    if (len(xa_in_lower) >= 3 and xa_in_lower in db_xa_moi) or (len(db_xa_moi) >= 3 and db_xa_moi in xa_in_lower):
                        score = 5
                        if tinh_in_lower and tinh_in_lower == row['tinh_moi_core_lower']:
                            score += 3
                        matched_records.append({'row': row, 'score': score})
                        
            # BƯỚC 3: Xử lý dữ liệu tìm được -> Dò ra ĐỊA CHỈ CŨ
            if matched_records:
                matched_records.sort(key=lambda x: x['score'], reverse=True)
                top_score = matched_records[0]['score']
                best_rows = [m['row'] for m in matched_records if m['score'] == top_score]
                
                # Trích xuất ra danh sách Địa chỉ CŨ
                old_candidates = []
                for r in best_rows:
                    old_addr = f"{r['Tên Xã cũ']}, {r['Huyện cũ']}, {r['Tỉnh cũ']}"
                    full_old = f"{prefix}, {old_addr}" if prefix else old_addr
                    if full_old not in old_candidates:
                        old_candidates.append(full_old)
                        
                # BƯỚC 4: Phân nhánh xử lý (Ghép luôn hoặc Khoanh vùng AI)
                if len(old_candidates) == 1:
                    # Tuyệt vời! Khớp đúng 1 địa chỉ Cũ -> Trả ngay (Độ tin cậy Cao)
                    direct_results[addr] = {"address": old_candidates[0], "confidence": "Cao"}
                else:
                    # Xã Mới gộp từ nhiều Xã Cũ -> Khoanh vùng gửi AI làm trọng tài
                    prompt_data[addr] = {
                        "prefix": prefix,
                        "candidates": old_candidates
                    }
            else:
                # BƯỚC 5: Không tìm thấy gì (gõ sai quá nặng) -> Nhờ AI hoặc Trạm cấp cứu
                prompt_data[addr] = {
                    "prefix": prefix,
                    "candidates": ["Không tìm thấy trong CSDL, hãy tự suy luận sửa lỗi và chuyển về Xã CŨ"]
                }
        
        # BƯỚC 6: CHỈ GỌI AI CHO NHỮNG CA NHẬP NHẰNG/NHIỀU KẾT QUẢ
        if prompt_data:
            prompt = f"""
            HỆ THỐNG CHUYỂN ĐỔI ĐỊA CHỈ: MỚI ➡️ CŨ (TRƯỚC SÁP NHẬP)
            
            DANH SÁCH CẦN XỬ LÝ:
            {json.dumps(prompt_data, ensure_ascii=False)}
            
            YÊU CẦU CHO TRỌNG TÀI AI:
            1. Tuyệt đối KHÔNG ĐƯỢC trả lại y nguyên địa chỉ đầu vào. Phải tìm ra địa chỉ CŨ.
            2. Với mỗi địa chỉ, tôi đã khoanh vùng "candidates" (là các ĐỊA CHỈ CŨ khả thi từ CSDL).
            3. Dựa vào "prefix" (tên đường/thôn/xóm/ấp), hãy CHỌN 1 địa chỉ đúng nhất trong danh sách candidates.
            4. Trả về JSON: Key là địa chỉ gốc, Value: {{"address": "KẾT QUẢ ĐỊA CHỈ CŨ", "confidence": "Cao" hoặc "Trung bình"}}
            5. Nếu candidates là rỗng hoặc báo lỗi, hãy tự suy luận. Nếu hoàn toàn bó tay mới trả về {{"address": "[Ghi lại địa chỉ gốc]", "confidence": "Nghi ngờ"}}.
            """
            
            max_retries, delay = 3, 2
            for attempt in range(max_retries):
                try:
                    response = model.generate_content(prompt)
                    text_res = response.text.strip()
                    if text_res.startswith("```json"): text_res = text_res[7:-3].strip()
                    elif text_res.startswith("

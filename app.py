import streamlit as st
import pandas as pd
import re
import unicodedata
import google.generativeai as genai
import time
import json
from streamlit_option_menu import option_menu

# ==========================================
# 1. CÀI ĐẶT TRANG & CSS
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
# 2. HÀM XỬ LÝ EXCEL & CHUẨN HÓA LÕI
# ==========================================
def get_core_name(name):
    if pd.isna(name) or not name: return ""
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
        df['xa_core_lower'] = df['xa_core'].astype(str).str.lower()
        df['huyen_core_lower'] = df['huyen_core'].astype(str).str.lower()
        
        df['xa_moi_core'] = df['Tên Xã mới'].apply(get_core_name)
        df['tinh_moi_core'] = df['Tỉnh mới'].apply(get_core_name)
        df['xa_moi_core_lower'] = df['xa_moi_core'].astype(str).str.lower()
        df['tinh_moi_core_lower'] = df['tinh_moi_core'].astype(str).str.lower()
        
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
    query = re.sub(r'\b(tp\.?\s*đn|tp\.\s*đà nẵng)\b', 'Thành phố Đà Nẵng', query, flags=re.IGNORECASE)
    query = re.sub(r'\b(tp\.?\s*hp|tp\.\s*hải phòng)\b', 'Thành phố Hải Phòng', query, flags=re.IGNORECASE)
    return query

def get_match_score(full_name, core_name, query, prefix_man):
    query, core_name, full_name = query.lower(), core_name.lower(), full_name.lower()
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
    notes, matches = [], []
    
    for row in db_records:
        if row['xa_core_lower'] not in query_lower or row['huyen_core_lower'] not in query_lower:
            continue
        xa_score = get_match_score(str(row['Tên Xã cũ']), row['xa_core'], query_search, PREFIX_XA_MAN)
        huyen_score = get_match_score(str(row['Huyện cũ']), row['huyen_core'], query_search, PREFIX_HUYEN_MAN)
        
        if xa_score > 0 and huyen_score > 0:
            tinh_score = get_match_score(str(row['Tỉnh cũ']), row['tinh_core'], query_search, PREFIX_TINH_MAN)
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
# 3. THUẬT TOÁN AI DỊCH NGƯỢC (MỚI -> CŨ) - TƯ DUY CHUỖI
# ==========================================
def extract_address_components(addr):
    if not addr: return "", "", "", ""
    parts = [p.strip() for p in addr.split(',') if p.strip()]
    tinh, huyen, xa, prefix_parts = "", "", "", []
    
    for p in reversed(parts):
        p_lower = p.lower()
        if not tinh and (re.search(r'^(tỉnh|thành phố|tp\.)\s+', p_lower) or p_lower in ['hà nội', 'hồ chí minh', 'đà nẵng', 'hải phòng', 'cần thơ']):
            tinh = p; continue
        if not huyen and re.search(r'^(quận|huyện|thị xã|thành phố|q\.|h\.|tx\.)\s+', p_lower):
            huyen = p; continue
        if not xa and (re.search(r'^(phường|xã|thị trấn|p\.|x\.|tt\.)\s+', p_lower) or re.match(r'^(p|x|tt)\s*\d+', p_lower)):
            xa = p; continue
        prefix_parts.insert(0, p)
        
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
            try:
                norm_addr = normalize_formatting(normalize_for_search(addr))
                prefix, xa_in, huyen_in, tinh_in = extract_address_components(norm_addr)
                xa_in_lower = str(xa_in).lower()
                tinh_in_lower = str(tinh_in).lower()
                
                matched_records = []
                for row in db_records:
                    score = 0
                    db_xa_moi = str(row.get('xa_moi_core_lower', ''))
                    db_tinh_moi = str(row.get('tinh_moi_core_lower', ''))
                    
                    if xa_in_lower and xa_in_lower == db_xa_moi:
                        score += 10
                        if tinh_in_lower and tinh_in_lower == db_tinh_moi:
                            score += 5
                    
                    if score > 0:
                        matched_records.append({'row': row, 'score': score})
                        
                if not matched_records and xa_in_lower:
                    for row in db_records:
                        db_xa_moi = str(row.get('xa_moi_core_lower', ''))
                        if (len(xa_in_lower) >= 3 and xa_in_lower in db_xa_moi) or (len(db_xa_moi) >= 3 and db_xa_moi in xa_in_lower):
                            score = 5
                            if tinh_in_lower and tinh_in_lower == str(row.get('tinh_moi_core_lower', '')):
                                score += 3
                            matched_records.append({'row': row, 'score': score})
                            
                if matched_records:
                    matched_records.sort(key=lambda x: x['score'], reverse=True)
                    top_score = matched_records[0]['score']
                    best_rows = [m['row'] for m in matched_records if m['score'] == top_score]
                    
                    old_candidates = []
                    for r in best_rows:
                        old_addr = f"{r['Tên Xã cũ']}, {r['Huyện cũ']}, {r['Tỉnh cũ']}"
                        if old_addr not in old_candidates:
                            old_candidates.append(old_addr)
                            
                    if len(old_candidates) == 1:
                        direct_results[addr] = {"address": f"{prefix}, {old_candidates[0]}" if prefix else old_candidates[0], "confidence": "Cao"}
                    else:
                        prompt_data[addr] = {"type": "merge_choice", "prefix": prefix, "candidates": old_candidates}
                else:
                    prompt_data[addr] = {"type": "geocoding_fix", "prefix": prefix, "original": addr}
            except Exception:
                prompt_data[addr] = {"type": "geocoding_fix", "prefix": addr, "original": addr}
        
        # GỌI AI NHỮNG CA PHỨC TẠP
        if prompt_data:
            prompt = f"""
            HỆ THỐNG CHUYỂN ĐỔI VÀ KIỂM ĐỊNH ĐỊA CHỈ VIỆT NAM (Mốc trước sáp nhập 2023-2025)
            
            DANH SÁCH CẦN XỬ LÝ:
            {json.dumps(prompt_data, ensure_ascii=False)}
            
            QUY TẮC BẮT BUỘC DÀNH CHO BẠN (TRỌNG TÀI BẢN ĐỒ):
            1. Bạn phải dùng kiến thức Google Maps để tự truy xuất xem "prefix" (tên đường/số nhà) đó thực tế nằm ở Phường/Xã nào.
            2. TUYỆT ĐỐI CẤM CHỌN BỪA (Random). Trước khi đưa ra địa chỉ, bạn PHẢI tự viết một dòng "reasoning" (lý do) để chứng minh bạn biết con đường đó nằm ở đâu.
            3. Nếu bạn không biết chắc chắn, HÃY TRẢ VỀ "Nghi ngờ" để con người tự sửa. CẤM trả lại y nguyên địa chỉ đầu vào nếu bị sai Phường.
            
            HƯỚNG DẪN XỬ LÝ THEO LOẠI (TYPE):
            - Nếu "type" == "merge_choice": Tìm con đường "prefix" xem nó khớp với Phường Cũ nào trong danh sách "candidates" và nối lại.
            - Nếu "type" == "geocoding_fix": "candidates" không có, bạn phải TỰ TÌM tên Phường/Xã đúng cho con đường đó và TỰ SỬA LẠI toàn bộ chuỗi địa chỉ.

            TRẢ VỀ ĐỊNH DẠNG JSON CHUẨN XÁC:
            {{
                "địa chỉ gốc": {{
                    "reasoning": "Ghi ngắn gọn lý do chọn (VD: Đường Lý Thường Kiệt số 330 thực chất nằm ở Phường 9...)",
                    "address": "ĐỊA CHỈ HOÀN CHỈNH ĐÃ GHÉP NỐI VÀ SỬA LỖI",
                    "confidence": "Cao" hoặc "Nghi ngờ"
                }}
            }}
            """
            
            max_retries, delay = 3, 2
            ai_success = False
            for attempt in range(max_retries):
                try:
                    response = model.generate_content(prompt)
                    text_res = response.text.strip()
                    if text_res.startswith("```json"): text_res = text_res[7:-3].strip()
                    elif text_res.startswith("```"): text_res = text_res[3:-3].strip()
                    res_obj = json.loads(text_res)
                    
                    for k, v in prompt_data.items():
                        if k in res_obj:
                            ai_addr = res_obj[k].get("address", "")
                            ai_conf = res_obj[k].get("confidence", "Nghi ngờ")
                            
                            if v["type"] == "geocoding_fix" and ai_addr.lower() == k.lower():
                                ai_conf = "Nghi ngờ"
                                
                            st.session_state.ai_cache[k] = {"address": ai_addr, "confidence": ai_conf}
                            results[k] = st.session_state.ai_cache[k]
                        else:
                            st.session_state.ai_cache[k] = {"address": k, "confidence": "Nghi ngờ"}
                            results[k] = st.session_state.ai_cache[k]
                    ai_success = True
                    break
                except Exception:
                    if attempt < max_retries - 1: time.sleep(delay); delay *= 2
                    
            if not ai_success:
                for k, v in prompt_data.items():
                    st.session_state.ai_cache[k] = {"address": k, "confidence": "Lỗi API/Nghi ngờ"}
                    results[k] = st.session_state.ai_cache[k]
        
        for k, v in direct_results.items():
            st.session_state.ai_cache[k] = v
            results[k] = v
            
        progress_bar.progress((idx + 1) / len(batches), text=f"Đang xử lý gói {idx + 1}/{len(batches)}...")
    
    progress_bar.empty()
    return results


# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
st.markdown("### 📍 Công cụ Chuyển đổi Địa chỉ Hành chính")

# MENU CẤP 1
main_mode = option_menu(
    menu_title=None,
    options=["Chuyển CŨ ➡️ MỚI (Excel)", "Chuyển MỚI ➡️ CŨ (Trợ lý AI)"],
    icons=["rocket-takeoff", "robot"],
    orientation="horizontal",
    styles={
        "container": {"padding": "4px", "background-color": "#f1f3f5", "border-radius": "12px", "margin-bottom": "15px"},
        "icon": {"color": "#495057", "font-size": "15px"},
        "nav-link": {
            "font-size": "14px", "font-weight": "600", "color": "#495057", 
            "border-radius": "8px", "padding": "8px 20px", "margin": "0px 4px",
            "--hover-color": "#e9ecef"
        },
        "nav-link-selected": {
            "background-color": "#ffffff", "color": "#0d6efd", "font-weight": "700",
            "box-shadow": "0px 2px 6px rgba(0,0,0,0.08)"
        },
    }
)

# ------------------------------------------
# PHÂN HỆ 1: CHUYỂN CŨ -> MỚI
# ------------------------------------------
if "CŨ ➡️ MỚI" in main_mode:
    sub_mode_excel = option_menu(
        menu_title=None,
        options=["Chuyển đổi hàng loạt", "Trạm vá lỗi dữ liệu", "Trạm xuất dữ liệu"],
        icons=["cloud-upload", "wrench", "download"],
        orientation="horizontal",
        styles={
            "container": {"padding": "3px", "background-color": "#f8f9fa", "border-radius": "8px", "margin-bottom": "15px", "border": "1px solid #e9ecef"},
            "icon": {"font-size": "13px"},
            "nav-link": {"font-size": "13px", "border-radius": "6px", "padding": "6px 15px"},
            "nav-link-selected": {"background-color": "#ffffff", "color": "#198754", "font-weight": "600", "box-shadow": "0px 1px 4px rgba(0,0,0,0.05)"},
        }
    )

    if sub_mode_excel == "Chuyển đổi hàng loạt":
        input_text = st.text_area("Nhập danh sách địa chỉ cũ (mỗi địa chỉ 1 dòng):", height=180, key="excel_input", placeholder="Ví dụ:\nPhường 1, Quận 3, TP HCM\nXã Tân Bình, Huyện Châu Thành, Tỉnh Đồng Tháp...")
        if st.button("⚡ Bắt đầu chuyển đổi Excel", type="primary", key="btn_excel"):
            queries = [q.strip() for q in input_text.split('\n') if q.strip()]
            st.session_state.app_data_excel = []
            bar = st.progress(0)
            for i, q in enumerate(queries):
                new_addr, note, is_err = auto_convert_address(q)
                st.session_state.app_data_excel.append({'id': i, 'old': q, 'new': new_addr, 'notes': note, 'is_error': is_err})
                bar.progress((i + 1) / len(queries))
            st.rerun()
            
        if st.session_state.app_data_excel:
            errs = sum(1 for d in st.session_state.app_data_excel if d['is_error'])
            st.success(f"🎉 Hoàn tất {len(st.session_state.app_data_excel)} dòng. (Có {errs} dòng bị lỗi ➡️ Chọn tab 'Trạm vá lỗi dữ liệu' phía trên để sửa)")

    elif sub_mode_excel == "Trạm vá lỗi dữ liệu":
        error_items = [d for d in st.session_state.app_data_excel if d['is_error']]
        if not error_items: st.info("🎉 Tất cả dữ liệu đã chính xác, không có dòng nào bị lỗi!")
        else:
            err_dict = {i['id']: i['old'] for i in error_items}
            sel_id = st.selectbox("Chọn địa chỉ lỗi để xử lý:", options=list(err_dict.keys()), format_func=lambda x: err_dict[x], key="excel_err_select")
            sel_item = next(i for i in st.session_state.app_data_excel if i['id'] == sel_id)
            
            c1, c2, c3 = st.columns(3)
            tinh_list = sorted(df['Tỉnh cũ'].astype(str).dropna().unique().tolist()) if not df.empty else []
            tinh_sel = c1.selectbox("Tỉnh/Thành cũ", ["-- Chọn --"] + tinh_list, key="tinh_sel")
            huyen_sel, xa_sel = "-- Chọn --", "-- Chọn --"
            if tinh_sel != "-- Chọn --":
                huyen_sel = c2.selectbox("Quận/Huyện cũ", ["-- Chọn --"] + sorted(df[df['Tỉnh cũ'] == tinh_sel]['Huyện cũ'].dropna().unique().tolist()), key="huyen_sel")
                if huyen_sel != "-- Chọn --":
                    xa_sel = c3.selectbox("Phường/Xã cũ", ["-- Chọn --"] + sorted(df[(df['Tỉnh cũ'] == tinh_sel) & (df['Huyện cũ'] == huyen_sel)]['Tên Xã cũ'].dropna().unique().tolist()), key="xa_sel")
            
            if xa_sel != "-- Chọn --":
                exact_row = df[(df['Tỉnh cũ'] == tinh_sel) & (df['Huyện cũ'] == huyen_sel) & (df['Tên Xã cũ'] == xa_sel)].iloc[0]
                sug_addr = force_convert_address(sel_item['old'], exact_row)
                final_edit = st.text_input("✍️ Chỉnh sửa lại kết quả:", value=sug_addr, key="edit_excel_input")
                if st.button("💾 Lưu kết quả sửa", type="primary", key="save_excel"):
                    for d in st.session_state.app_data_excel:
                        if d['id'] == sel_id:
                            d.update({'new': final_edit, 'is_error': False, 'notes': "✅ Đã sửa thủ công"})
                    st.rerun()

    elif sub_mode_excel == "Trạm xuất dữ liệu":
        if st.session_state.app_data_excel:
            df_out = pd.DataFrame(st.session_state.app_data_excel)[['old', 'new', 'notes']].rename(columns={'old': 'Địa chỉ Gốc', 'new': 'Địa chỉ Mới', 'notes': 'Ghi chú'})
            st.dataframe(df_out, use_container_width=True)
            st.download_button("📥 Tải file CSV", data=df_out.to_csv(index=False, encoding='utf-8-sig'), file_name="ChuyenDoi_Excel.csv", mime="text/csv", type="primary", key="dl_excel")
        else: st.info("Chưa có dữ liệu. Vui lòng chuyển đổi ở tab đầu tiên trước!")

# ------------------------------------------
# PHÂN HỆ 2: CHUYỂN MỚI -> CŨ
# ------------------------------------------
else:
    with st.expander("🔑 Bảng cấu hình API Google Gemini", expanded=True):
        c1, c2 = st.columns([1, 2])
        api_key = c1.text_input("Nhập Google Gemini API Key:", type="password", key="ai_key_input", placeholder="AIzaSy...")
        selected_model = None
        if api_key:
            try:
                genai.configure(api_key=api_key)
                models = [m.name.replace("models/", "") for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                selected_model = c2.selectbox("Chọn phiên bản AI:", models, index=models.index('gemini-1.5-flash') if 'gemini-1.5-flash' in models else 0, key="ai_model_select")
            except Exception:
                st.error("API Key chưa hợp lệ!")

    sub_mode_ai = option_menu(
        menu_title=None,
        options=["Chuyển đổi hàng loạt", "Trạm cấp cứu AI", "Trạm xuất dữ liệu"],
        icons=["cpu", "patch-exclamation", "download"],
        orientation="horizontal",
        styles={
            "container": {"padding": "3px", "background-color": "#f8f9fa", "border-radius": "8px", "margin-bottom": "15px"},
            "icon": {"font-size": "13px"},
            "nav-link": {"font-size": "13px", "border-radius": "6px", "padding": "6px 15px"},
            "nav-link-selected": {"background-color": "#ffffff", "color": "#0d6efd", "font-weight": "600", "box-shadow": "0px 1px 4px rgba(0,0,0,0.05)"},
        }
    )

    if sub_mode_ai == "Chuyển đổi hàng loạt":
        input_text_ai = st.text_area("Nhập danh sách địa chỉ MỚI cần tra cứu/sửa lỗi (Mỗi địa chỉ 1 dòng):", height=180, key="ai_input", placeholder="Ví dụ:\n330 Lý Thường Kiệt, Phường 6, Quận Tân Bình, Thành phố Hồ Chí Minh\nK29/2 Nguyễn Như Đãi, Phường Cẩm Lệ, Đà Nẵng")
        if st.button("⏪ Yêu cầu AI dịch ngược & sửa lỗi", type="primary", key="btn_ai"):
            if not selected_model: st.warning("⚠️ Vui lòng nhập API Key hợp lệ ở bảng cấu hình phía trên trước!")
            elif input_text_ai.strip():
                st.session_state.ai_cache = {}
                queries = [q.strip() for q in input_text_ai.split('\n') if q.strip()]
                model = genai.GenerativeModel(selected_model)
                
                with st.spinner("Hệ thống đang Vận hành Logic Dò tìm Excel & Tư duy AI..."):
                    results = smart_ai_lookup(model, queries)
                
                st.session_state.app_data_ai = []
                for i, q in enumerate(queries):
                    res_obj = results.get(q, {"address": q, "confidence": "Nghi ngờ"})
                    conf = res_obj.get("confidence", "Nghi ngờ")
                    
                    st.session_state.app_data_ai.append({
                        'id': i, 
                        'old': q, 
                        'new': res_obj.get("address", ""), 
                        'confidence': conf,
                        'is_error': conf == "Nghi ngờ"
                    })
                st.rerun()

        if st.session_state.app_data_ai:
            suspects = sum(1 for d in st.session_state.app_data_ai if d['is_error'])
            st.success(f"🎉 Hoàn tất phân tích {len(st.session_state.app_data_ai)} dòng! (Có {suspects} ca chuyển về 'Trạm cấp cứu AI' để xử lý)")

    elif sub_mode_ai == "Trạm cấp cứu AI":
        suspect_items = [d for d in st.session_state.app_data_ai if d['is_error']]
        if not suspect_items: st.info("🎉 Tất cả địa chỉ đều đã được dò Excel và AI sửa lỗi thành công!")
        else:
            st.warning("Các địa chỉ dưới đây thiếu thông tin hoặc sai lệch quá nặng khiến AI không thể suy luận. Bạn hãy chọn Tỉnh/Xã MỚI chuẩn để Bảng Cũ hiện ra!")
            err_dict_ai = {i['id']: f"{i['old']} ➡️ [Dự đoán: {i['new']}]" for i in suspect_items}
            sel_id_ai = st.selectbox("Chọn địa chỉ cần xác nhận/cấp cứu:", options=list(err_dict_ai.keys()), format_func=lambda x: err_dict_ai[x], key="ai_err_select")
            sel_item_ai = next(i for i in st.session_state.app_data_ai if i['id'] == sel_id_ai)
            
            c1, c2 = st.columns(2)
            tinh_list_new = sorted(df['Tỉnh mới'].astype(str).dropna().unique().tolist()) if not df.empty else []
            tinh_sel_new = c1.selectbox("1. Thuộc Tỉnh/Thành MỚI chuẩn?", ["-- Chọn --"] + tinh_list_new, key="tinh_sel_new")
            
            xa_sel_new = "-- Chọn --"
            if tinh_sel_new != "-- Chọn --":
                df_tinh = df[df['Tỉnh mới'] == tinh_sel_new]
                xa_sel_new = c2.selectbox("2. Thuộc Phường/Xã MỚI chuẩn?", ["-- Chọn --"] + sorted(df_tinh['Tên Xã mới'].dropna().unique().tolist()), key="xa_sel_new")
            
            if xa_sel_new != "-- Chọn --":
                matched_rows = df[(df['Tỉnh mới'] == tinh_sel_new) & (df['Tên Xã mới'] == xa_sel_new)]
                
                st.markdown(f"""
                <div class="ref-box">
                    💡 <b>BẢNG SÁP NHẬP ĐỊA GIỚI:</b><br>
                    Địa bàn <b>{xa_sel_new} ({tinh_sel_new})</b> được sáp nhập từ <b>{len(matched_rows)}</b> đơn vị cũ dưới đây:
                </div>
                """, unsafe_allow_html=True)
                
                st.dataframe(matched_rows[['Tên Xã cũ', 'Huyện cũ', 'Tỉnh cũ']].reset_index(drop=True), use_container_width=True)
                
                old_options = [f"{row['Tên Xã cũ']}, {row['Huyện cũ']}, {row['Tỉnh cũ']}" for _, row in matched_rows.iterrows()]
                
                def update_edit_text(addr_input):
                    selected_old = st.session_state.old_unit_select
                    prefix, _, _, _ = extract_address_components(addr_input)
                    st.session_state.edit_ai_input = f"{prefix}, {selected_old}" if prefix else selected_old

                selected_old_unit = st.selectbox(
                    "3. Chọn thủ công Đơn vị CŨ đúng:", 
                    options=old_options, 
                    key="old_unit_select",
                    on_change=update_edit_text,
                    args=(sel_item_ai['old'],)
                )
                
                prefix_str, _, _, _ = extract_address_components(sel_item_ai['old'])
                default_val = f"{prefix_str}, {selected_old_unit}" if prefix_str else selected_old_unit
                if "edit_ai_input" not in st.session_state:
                    st.session_state.edit_ai_input = default_val
                
                final_edit_ai = st.text_input("✍️ Chỉnh sửa lần cuối:", key="edit_ai_input")
                
                if st.button("💾 Lưu thủ công", type="primary", key="save_ai_fix"):
                    for d in st.session_state.app_data_ai:
                        if d['id'] == sel_id_ai:
                            d.update({'new': final_edit_ai, 'confidence': 'Đã sửa tay', 'is_error': False})
                    if "edit_ai_input" in st.session_state: del st.session_state.edit_ai_input
                    st.rerun()

    elif sub_mode_ai == "Trạm xuất dữ liệu":
        if st.session_state.app_data_ai:
            df_out_ai = pd.DataFrame(st.session_state.app_data_ai)[['old', 'new', 'confidence']].rename(
                columns={'old': 'Địa chỉ Gốc Đầu vào', 'new': 'Địa chỉ CŨ chuẩn (AI Sửa/Dịch)', 'confidence': 'Trạng thái'}
            )
            st.dataframe(df_out_ai, use_container_width=True)
            
            st.markdown("---")
            st.markdown("##### 🚨 Phát hiện AI/Hệ thống đoán sai?")
            
            c1, c2 = st.columns([3, 1])
            ai_items_dict = {i['id']: f"Dòng {idx+1}: {i['old']} ➡️ [{i['new']}]" for idx, i in enumerate(st.session_state.app_data_ai)}
            sel_wrong_id = c1.selectbox("Chọn dòng bạn phát hiện sai:", options=list(ai_items_dict.keys()), format_func=lambda x: ai_items_dict[x], key="wrong_select")
            
            if c2.button("🚨 Đẩy sang Trạm cấp cứu", type="secondary"):
                for d in st.session_state.app_data_ai:
                    if d['id'] == sel_wrong_id:
                        d.update({'confidence': 'Nghi ngờ', 'is_error': True})
                st.success("✅ Đã chuyển ca này về 'Nghi ngờ'! Hãy sang Tab 'Trạm cấp cứu AI' để chỉnh lại nhé.")
                st.rerun()
                
            st.markdown("---")
            st.download_button("📥 TẢI FILE KẾT QUẢ AI (CSV)", data=df_out_ai.to_csv(index=False, encoding='utf-8-sig'), file_name="Ket_Qua_AI_Sua_Loi.csv", mime="text/csv", type="primary", key="dl_ai")
        else: st.info("Chưa có dữ liệu. Vui lòng chạy phân tích ở tab đầu tiên trước!")

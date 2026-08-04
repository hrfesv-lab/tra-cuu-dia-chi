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
        
        records = df.to_dict('records')
        return df, records
    except Exception as e:
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
# 3. THUẬT TOÁN AI DỊCH NGƯỢC (TỐI ƯU TƯ DUY CHUỖI)
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
                        # Tuyệt vời! Khớp đúng 1 địa chỉ Cũ -> Trả ngay
                        direct_results[addr] = {"address": f"{prefix}, {old_candidates[0]}" if prefix else old_candidates[0], "confidence": "Cao"}
                    else:
                        # Khoanh vùng nhiều ứng viên
                        prompt_data[addr] = {"type": "merge_choice", "prefix": prefix, "candidates": old_candidates}
                else:
                    # KHÔNG CÓ TRONG EXCEL -> Geocoding Fix
                    prompt_data[addr] = {"type": "geocoding_fix", "prefix": prefix, "original": addr}
            except Exception:
                prompt_data[addr] = {"type": "geocoding_fix", "prefix": addr, "original": addr}
        
        # BƯỚC GỌI AI: SỬ DỤNG KỸ THUẬT CHAIN-OF-THOUGHT CHỐNG ĐOÁN MÒ
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
                            
                            # Phạt AI nếu vẫn trả lại input cũ ở chế độ tự sửa
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
                    
            # Nếu AI sập mạng -> Đẩy thẳng về Trạm cấp cứu, KHÔNG BỐC BỪA
            if not ai_success:
                for k, v in prompt_data.items():
                    st.session_state.ai_cache[k] = {"address": k, "confidence": "Lỗi API/Nghi ngờ"}
                    results[k] = st.session_state.ai_cache[k]
        
        # Nạp dữ liệu giải quyết trực tiếp
        for k, v in direct_results.items():
            st.session_state.ai_cache[k] = v
            results[k] = v
            
        progress_bar.progress((idx + 1) / len(batches), text=f"Đang xử lý gói {idx + 1}/{len(batches)}...")
    
    progress_bar.empty()
    return results

# ==========================================
# 4. GIAO DIỆN CHÍNH (TABS NGANG XỊN)
# ==========================================
st.title("📍 CÔNG CỤ CHUYỂN ĐỔI ĐỊA CHỈ")
st.markdown("Hệ thống thông minh tự động gỡ bỏ các tiền tố (P., Q., TP...) khi sáp nhập.")

tab1, tab2, tab3, tab4 = st.tabs(["🚀 1. Chuyển đổi hàng loạt", "🛠️ 2. Trạm cấp cứu (Sửa thủ công)", "📥 3. Trạm xuất dữ liệu", "🤖 4. AI Dịch ngược (Mới -> Cũ)"])

with tab1:
    col_input, col_info = st.columns([2, 1])
    with col_input:
        input_text = st.text_area(
            "Nhập danh sách địa chỉ cũ (mỗi địa chỉ 1 dòng):", 
            height=250,
            placeholder="Ví dụ:\n182 Phạm Phú Thứ, Phường 4, Quận 6, TP. HCM\nXã Tân Bình, Huyện Châu Thành, Tỉnh Đồng Tháp"
        )
        if st.button("🔄 Bắt đầu chạy tự động", type="primary", use_container_width=True):
            if input_text.strip():
                queries = [q.strip() for q in input_text.split('\n') if q.strip()]
                st.session_state.app_data_excel = [] 
                
                progress_bar = st.progress(0)
                for i, query in enumerate(queries):
                    new_addr, note, is_err = auto_convert_address(query)
                    st.session_state.app_data_excel.append({
                        'id': i, 'old': query, 'new': new_addr, 'notes': note, 'is_error': is_err
                    })
                    progress_bar.progress((i + 1) / len(queries))
                st.rerun() 
            else:
                st.warning("Vui lòng nhập dữ liệu!")

    with col_info:
        st.info("💡 **Hướng dẫn:**\n\n1. Dán danh sách vào ô bên trái.\n2. Bấm chạy tự động.\n3. Sang Tab 2 nếu có lỗi.\n4. Sang Tab 3 tải CSV.")
        if st.session_state.app_data_excel:
            err_count = sum(1 for d in st.session_state.app_data_excel if d['is_error'])
            succ_count = len(st.session_state.app_data_excel) - err_count
            st.success(f"✅ Đã xử lý: **{succ_count}**")
            if err_count > 0:
                st.error(f"⚠️ Lỗi: **{err_count}** (Xem Tab 2)")

with tab2:
    error_items = [d for d in st.session_state.app_data_excel if d['is_error']]
    if not st.session_state.app_data_excel:
        st.info("👈 Hãy chạy tính năng chuyển đổi hàng loạt ở Tab 1 trước nhé!")
    elif not error_items:
        st.success("🎉 Mọi địa chỉ đều đã được nhận diện thành công!")
    else:
        error_dict = {item['id']: item['old'] for item in error_items}
        selected_id = st.selectbox(f"🚨 Đang có {len(error_items)} địa chỉ cần bạn hỗ trợ:", options=list(error_dict.keys()), format_func=lambda x: error_dict[x])
        selected_item = next(item for item in st.session_state.app_data_excel if item['id'] == selected_id)
        
        st.markdown(f"**📍 Địa chỉ gốc:** `{selected_item['old']}`")
        st.markdown("---")
        
        col1, col2, col3 = st.columns(3)
        tinh_list = sorted(df['Tỉnh cũ'].astype(str).dropna().unique().tolist()) if not df.empty else []
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
                    for d in st.session_state.app_data_excel:
                        if d['id'] == selected_id:
                            d['new'] = final_edit
                            d['is_error'] = False
                            d['notes'] = "✅ Đã sửa thủ công"
                    st.rerun()
            with col_btn2:
                if st.button("⚠️ Giữ nguyên địa chỉ gốc"):
                    for d in st.session_state.app_data_excel:
                        if d['id'] == selected_id:
                            d['new'] = selected_item['old']
                            d['is_error'] = False
                            d['notes'] = "Giữ nguyên"
                    st.rerun()

with tab3:
    if not st.session_state.app_data_excel:
        st.info("👈 Hãy chạy tính năng chuyển đổi hàng loạt ở Tab 1 trước nhé!")
    else:
        err_count = sum(1 for d in st.session_state.app_data_excel if d['is_error'])
        if err_count > 0:
            st.warning(f"⚠️ Chú ý: Vẫn còn {err_count} địa chỉ lỗi chưa được sửa ở Tab 2.")
            
        df_results = pd.DataFrame(st.session_state.app_data_excel)
        df_display = df_results[['old', 'new', 'notes']].rename(columns={
            'old': 'Địa chỉ GỐC', 
            'new': 'Địa chỉ SAU chuyển đổi', 
            'notes': 'Ghi chú'
        })
        st.dataframe(df_display, use_container_width=True)
        csv_data = df_display.to_csv(index=False, encoding='utf-8-sig')
        st.download_button("⬇️ TẢI FILE KẾT QUẢ CSV", data=csv_data, file_name="Ket_Qua_Dia_Chi.csv", mime="text/csv", use_container_width=True, type="primary")

# ==========================================
# TAB 4: MỚI -> CŨ VÀ TỰ SỬA LỖI (AI GEOCONDING FIX)
# ==========================================
with tab4:
    st.markdown("### 🤖 Trợ lý AI: Dịch ngược & Tự sửa lỗi địa chỉ (Mới -> Cũ)")
    st.info("AI sẽ tự động kiểm tra xem khu vực có bị sáp nhập không. Nếu bạn gõ sai tên Phường/Xã, AI sẽ dùng kiến thức bản đồ để tự động sửa lại cho đúng!")
    
    col_ai_1, col_ai_2 = st.columns([1, 2])
    
    with col_ai_1:
        api_key_input = st.text_input("🔑 Nhập Google Gemini API Key:", type="password")
    
    if api_key_input:
        try:
            genai.configure(api_key=api_key_input)
            available_models = [m.name.replace("models/", "") for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            
            if available_models:
                with col_ai_2:
                    selected_model = st.selectbox("🧠 Chọn phiên bản AI:", available_models)
                
                input_text_ai = st.text_area(
                    "📍 Nhập danh sách địa chỉ MỚI cần tra cứu/sửa lỗi (Mỗi địa chỉ 1 dòng):", 
                    height=200,
                    placeholder="Ví dụ:\n330 Lý Thường Kiệt, Phường 6, Quận Tân Bình, Thành phố Hồ Chí Minh\nK29/2 Nguyễn Như Đãi, Phường Cẩm Lệ, Đà Nẵng"
                )
                
                if st.button("⏪ Yêu cầu AI xử lý hàng loạt", type="primary", use_container_width=True):
                    if not input_text_ai.strip():
                        st.warning("Vui lòng nhập địa chỉ cần tra cứu!")
                    else:
                        queries = [q.strip() for q in input_text_ai.split('\n') if q.strip()]
                        st.session_state.app_data_ai = []
                        model = genai.GenerativeModel(selected_model)
                        
                        with st.spinner("Hệ thống đang Vận hành Logic Dò tìm Excel & Tư duy AI..."):
                            results = smart_ai_lookup(model, queries)
                            
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
                    st.success(f"🎉 Hoàn tất phân tích {len(st.session_state.app_data_ai)} dòng! (Có {suspects} ca cần bạn kiểm tra thủ công)")
                    
                    st.markdown("---")
                    df_ai = pd.DataFrame(st.session_state.app_data_ai)[['old', 'new', 'confidence']].rename(
                        columns={'old': 'Địa chỉ Gốc Đầu vào', 'new': 'Địa chỉ CŨ chuẩn (AI Sửa/Dịch)', 'confidence': 'Trạng thái'}
                    )
                    st.dataframe(df_ai, use_container_width=True)
                    
                    # Nút Download cho Tab AI
                    csv_ai = df_ai.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button("📥 TẢI FILE KẾT QUẢ AI (CSV)", data=csv_ai, file_name="Ket_Qua_AI_Sua_Loi.csv", mime="text/csv", type="primary")
                    
                    # Nút Trạm cấp cứu
                    if suspects > 0:
                        st.markdown("---")
                        st.markdown("##### 🚨 Xử lý các địa chỉ Nghi ngờ/Lỗi AI")
                        
                        err_dict_ai = {i['id']: f"{i['old']} ➡️ [{i['new']}]" for i in st.session_state.app_data_ai if i['is_error']}
                        sel_id_ai = st.selectbox("Chọn địa chỉ cần xác nhận/cấp cứu:", options=list(err_dict_ai.keys()), format_func=lambda x: err_dict_ai[x])
                        sel_item_ai = next(i for i in st.session_state.app_data_ai if i['id'] == sel_id_ai)
                        
                        c1, c2 = st.columns(2)
                        tinh_list_new = sorted(df['Tỉnh mới'].astype(str).dropna().unique().tolist()) if not df.empty else []
                        tinh_sel_new = c1.selectbox("1. Thuộc Tỉnh/Thành MỚI chuẩn?", ["-- Chọn --"] + tinh_list_new)
                        
                        xa_sel_new = "-- Chọn --"
                        if tinh_sel_new != "-- Chọn --":
                            df_tinh = df[df['Tỉnh mới'] == tinh_sel_new]
                            xa_sel_new = c2.selectbox("2. Thuộc Phường/Xã MỚI chuẩn?", ["-- Chọn --"] + sorted(df_tinh['Tên Xã mới'].dropna().unique().tolist()))
                        
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
                            selected_old_unit = st.selectbox("3. Chọn thủ công Đơn vị CŨ đúng:", options=old_options)
                            
                            prefix_str, _, _, _ = extract_address_components(sel_item_ai['old'])
                            default_val = f"{prefix_str}, {selected_old_unit}" if prefix_str else selected_old_unit
                            final_edit_ai = st.text_input("✍️ Chỉnh sửa lần cuối:", value=default_val)
                            
                            if st.button("💾 Lưu thủ công", type="primary"):
                                for d in st.session_state.app_data_ai:
                                    if d['id'] == sel_id_ai:
                                        d['new'] = final_edit_ai
                                        d['confidence'] = "Đã sửa tay"
                                        d['is_error'] = False
                                st.rerun()

        except Exception as e:
            st.error(f"Lỗi kết nối với API Key: {e}")

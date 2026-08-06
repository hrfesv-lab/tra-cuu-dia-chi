import streamlit as st
import pandas as pd
import re
import unicodedata
import os
import json
from streamlit_option_menu import option_menu
import time

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
if 'app_data_moi_cu' not in st.session_state: st.session_state.app_data_moi_cu = []

# ==========================================
# 2. HỆ THỐNG TỪ ĐIỂN SỬA TAY VĨNH VIỄN (2 CHIỀU)
# ==========================================
DICT_CU_MOI = "Tu_Dien_Cu_Moi.json"
DICT_MOI_CU = "Tu_Dien_Moi_Cu.json"

def load_dict(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_dict(d, filepath):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=4)

if 'dict_cu_moi' not in st.session_state:
    st.session_state.dict_cu_moi = load_dict(DICT_CU_MOI)
if 'dict_moi_cu' not in st.session_state:
    st.session_state.dict_moi_cu = load_dict(DICT_MOI_CU)

# ==========================================
# 3. NẠP DỮ LIỆU EXCEL & CHUẨN HÓA LÕI
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
    # ƯU TIÊN LẤY TỪ ĐIỂN SỬA TAY
    if query in st.session_state.dict_cu_moi:
        return st.session_state.dict_cu_moi[query]['new'], st.session_state.dict_cu_moi[query]['notes'], False

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
# 4. THUẬT TOÁN MỚI -> CŨ (OFFLINE 100%)
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

def convert_moi_to_cu_offline(query):
    # ƯU TIÊN LẤY TỪ ĐIỂN SỬA TAY
    if query in st.session_state.dict_moi_cu:
        return st.session_state.dict_moi_cu[query]['new'], st.session_state.dict_moi_cu[query]['notes'], False

    query_search = normalize_for_search(normalize_formatting(query))
    prefix, xa_in, huyen_in, tinh_in = extract_address_components(query_search)
    
    xa_in_lower = str(xa_in).lower()
    tinh_in_lower = str(tinh_in).lower()
    
    matched_records = []
    
    if xa_in_lower:
        for row in db_records:
            if xa_in_lower == str(row.get('xa_moi_core_lower', '')):
                score = 10
                if tinh_in_lower and tinh_in_lower in str(row.get('tinh_moi_core_lower', '')):
                    score += 5
                matched_records.append({'row': row, 'score': score})
                
    if not matched_records and xa_in_lower:
        for row in db_records:
            db_xa = str(row.get('xa_moi_core_lower', ''))
            if (len(xa_in_lower) >= 3 and xa_in_lower in db_xa) or (len(db_xa) >= 3 and db_xa in xa_in_lower):
                score = 5
                if tinh_in_lower and tinh_in_lower in str(row.get('tinh_moi_core_lower', '')):
                    score += 5
                matched_records.append({'row': row, 'score': score})
                
    if matched_records:
        matched_records.sort(key=lambda x: x['score'], reverse=True)
        top_score = matched_records[0]['score']
        best_rows = [m['row'] for m in matched_records if m['score'] == top_score]
        
        old_cands = list(set([f"{r['Tên Xã cũ']}, {r['Huyện cũ']}, {r['Tỉnh cũ']}" for r in best_rows]))
        
        if len(old_cands) == 1:
            ans = f"{prefix}, {old_cands[0]}" if prefix else old_cands[0]
            ans = re.sub(r',\s*,', ',', ans).strip(', ')
            return ans, "Thành công", False
        else:
            huyen_cu = best_rows[0]['Huyện cũ']
            tinh_cu = best_rows[0]['Tỉnh cũ']
            ans = f"{prefix}, [*Vui lòng tra cứu Phường/Xã cũ tại web UBND*], {huyen_cu}, {tinh_cu}" if prefix else f"[*Vui lòng tra cứu Phường/Xã cũ tại web UBND*], {huyen_cu}, {tinh_cu}"
            ans = re.sub(r',\s*,', ',', ans).strip(', ')
            return ans, "Cảnh báo: Thiếu Xã/Phường", True
    else:
        return f"{query} ➡️ [*Không khớp CSDL*]", "Lỗi hệ thống", True

# ==========================================
# 5. GIAO DIỆN CHÍNH
# ==========================================
st.markdown("### 📍 Công cụ Chuyển đổi Địa chỉ Hành chính")

main_mode = option_menu(
    menu_title=None,
    options=["Chuyển CŨ ➡️ MỚI", "Chuyển MỚI ➡️ CŨ"],
    icons=["rocket-takeoff", "database"],
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
        icons=["cloud-upload", "tools", "download"],
        orientation="horizontal",
        styles={
            "container": {"padding": "3px", "background-color": "#f8f9fa", "border-radius": "8px", "margin-bottom": "15px", "border": "1px solid #e9ecef"},
            "icon": {"font-size": "13px"},
            "nav-link": {"font-size": "13px", "border-radius": "6px", "padding": "6px 15px"},
            "nav-link-selected": {"background-color": "#ffffff", "color": "#198754", "font-weight": "600", "box-shadow": "0px 1px 4px rgba(0,0,0,0.05)"},
        }
    )

    if sub_mode_excel == "Chuyển đổi hàng loạt":
        input_text = st.text_area("Nhập danh sách địa chỉ cũ (mỗi địa chỉ 1 dòng):", height=180, placeholder="Ví dụ:\nPhường 1, Quận 3, TP HCM\nXã Tân Bình, Huyện Châu Thành, Tỉnh Đồng Tháp")
        if st.button("⚡ Bắt đầu chuyển đổi", type="primary", use_container_width=True):
            if input_text.strip():
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
            st.success(f"🎉 Hoàn tất {len(st.session_state.app_data_excel)} dòng. (Có {errs} dòng bị lỗi). Sang Tab 'Trạm xuất dữ liệu' để rà soát.")

    elif sub_mode_excel == "Trạm vá lỗi dữ liệu":
        st.markdown("##### 🛠️ Khu vực Sửa tay & Nạp Từ Điển vĩnh viễn")
        error_items = [d for d in st.session_state.app_data_excel if d['is_error']]
        
        if not error_items: 
            st.info("Mọi dữ liệu đang sạch! (Nếu phát hiện dòng nào sai sót lúc kiểm tra, hãy tích ô 🚨 Cấp cứu ở Tab Xuất Dữ Liệu)")
        else:
            err_dict = {i['id']: i['old'] for i in error_items}
            sel_id = st.selectbox("Chọn địa chỉ cần cấp cứu:", options=list(err_dict.keys()), format_func=lambda x: err_dict[x])
            sel_item = next(i for i in st.session_state.app_data_excel if i['id'] == sel_id)
            
            c1, c2, c3 = st.columns(3)
            tinh_list = sorted(df['Tỉnh cũ'].astype(str).dropna().unique().tolist()) if not df.empty else []
            tinh_sel = c1.selectbox("Tỉnh/Thành cũ", ["-- Chọn --"] + tinh_list)
            huyen_sel, xa_sel = "-- Chọn --", "-- Chọn --"
            if tinh_sel != "-- Chọn --":
                huyen_sel = c2.selectbox("Quận/Huyện cũ", ["-- Chọn --"] + sorted(df[df['Tỉnh cũ'] == tinh_sel]['Huyện cũ'].dropna().unique().tolist()))
                if huyen_sel != "-- Chọn --":
                    xa_sel = c3.selectbox("Phường/Xã cũ", ["-- Chọn --"] + sorted(df[(df['Tỉnh cũ'] == tinh_sel) & (df['Huyện cũ'] == huyen_sel)]['Tên Xã cũ'].dropna().unique().tolist()))
            
            if xa_sel != "-- Chọn --":
                exact_row = df[(df['Tỉnh cũ'] == tinh_sel) & (df['Huyện cũ'] == huyen_sel) & (df['Tên Xã cũ'] == xa_sel)].iloc[0]
                sug_addr = force_convert_address(sel_item['old'], exact_row)
                final_edit = st.text_input("✍️ Chỉnh sửa lần cuối:", value=sug_addr)
                
                if st.button("💾 Lưu kết quả & Nạp vào Từ điển", type="primary"):
                    for d in st.session_state.app_data_excel:
                        if d['id'] == sel_id:
                            d.update({'new': final_edit, 'is_error': False, 'notes': "✅ Lấy từ Từ điển"})
                    
                    st.session_state.dict_cu_moi[sel_item['old']] = {'new': final_edit, 'notes': '✅ Lấy từ Từ điển'}
                    save_dict(st.session_state.dict_cu_moi, DICT_CU_MOI)
                    st.success("Đã ghi nhớ vĩnh viễn vào hệ thống!")
                    time.sleep(1)
                    st.rerun()

    elif sub_mode_excel == "Trạm xuất dữ liệu":
        if not st.session_state.app_data_excel:
            st.info("👈 Hãy chạy tính năng chuyển đổi hàng loạt ở Tab đầu tiên!")
        else:
            st.markdown("##### 🚨 Bảng kiểm tra và Xuất dữ liệu")
            st.write("Lướt bảng, nếu thấy dòng nào sai (Tách xã, mâu thuẫn), hãy **Tích vào ô vuông 🚨 Cấp cứu** rồi bấm nút bên dưới bảng.")
            
            df_show = pd.DataFrame(st.session_state.app_data_excel)
            if '🚨 Cấp cứu' not in df_show.columns:
                df_show.insert(0, '🚨 Cấp cứu', False)
                
            cols = ['🚨 Cấp cứu', 'id', 'old', 'new', 'notes', 'is_error']
            edited_df = st.data_editor(
                df_show[cols], 
                column_config={
                    "🚨 Cấp cứu": st.column_config.CheckboxColumn("🚨 Cấp cứu", default=False),
                    "old": "Địa chỉ Gốc",
                    "new": "Kết quả",
                    "notes": "Ghi chú",
                },
                disabled=['id', 'old', 'new', 'notes', 'is_error'],
                hide_index=True,
                use_container_width=True
            )
            
            c1, c2 = st.columns([1, 3])
            with c1:
                if st.button("🛠️ Đẩy các dòng tích về Trạm Vá", type="secondary"):
                    count_pushed = 0
                    for index, row in edited_df.iterrows():
                        if row['🚨 Cấp cứu']:
                            for item in st.session_state.app_data_excel:
                                if item['id'] == row['id']:
                                    item['is_error'] = True
                                    item['notes'] = "Cần sửa tay"
                                    count_pushed += 1
                    if count_pushed > 0:
                        st.success(f"✅ Đã đẩy {count_pushed} dòng về diện cần sửa thủ công!")
                        st.rerun()
            with c2:
                csv_data = pd.DataFrame(st.session_state.app_data_excel)[['old', 'new', 'notes']].rename(columns={'old': 'Địa chỉ Gốc', 'new': 'Địa chỉ Mới', 'notes': 'Ghi chú'}).to_csv(index=False, encoding='utf-8-sig')
                st.download_button("📥 TẢI FILE KẾT QUẢ CSV", data=csv_data, file_name="ChuyenDoi_Excel_Clean.csv", mime="text/csv", type="primary")

# ------------------------------------------
# PHÂN HỆ 2: CHUYỂN MỚI -> CŨ (OFFLINE 100%)
# ------------------------------------------
else:
    sub_mode_ai = option_menu(
        menu_title=None,
        options=["Chuyển đổi hàng loạt", "Trạm vá lỗi dữ liệu", "Trạm xuất dữ liệu"],
        icons=["lightning", "tools", "download"],
        orientation="horizontal",
        styles={
            "container": {"padding": "3px", "background-color": "#f8f9fa", "border-radius": "8px", "margin-bottom": "15px"},
            "icon": {"font-size": "13px"},
            "nav-link": {"font-size": "13px", "border-radius": "6px", "padding": "6px 15px"},
            "nav-link-selected": {"background-color": "#ffffff", "color": "#0d6efd", "font-weight": "600", "box-shadow": "0px 1px 4px rgba(0,0,0,0.05)"},
        }
    )

    if sub_mode_ai == "Chuyển đổi hàng loạt":
        st.warning("⚠️ CHÚ Ý: Chế độ này dùng CSDL Offline siêu tốc. Nếu khu vực có xã sáp nhập phức tạp, hệ thống sẽ trả về Cảnh báo và yêu cầu tra cứu Phường/Xã cũ tại web của UBND.")
        input_text_ai = st.text_area("Nhập danh sách địa chỉ MỚI (Mỗi địa chỉ 1 dòng):", height=180, placeholder="Ví dụ:\n1118 Kha Vạn Cân, Phường Thủ Đức, TP HCM\nK29/2 Nguyễn Như Đãi, Phường Cẩm Lệ, Đà Nẵng")
        if st.button("⏪ Bắt đầu Xử lý Offline", type="primary"):
            if input_text_ai.strip():
                queries = [q.strip() for q in input_text_ai.split('\n') if q.strip()]
                st.session_state.app_data_moi_cu = []
                
                bar = st.progress(0)
                for i, q in enumerate(queries):
                    ans, conf, is_err = convert_moi_to_cu_offline(q)
                    st.session_state.app_data_moi_cu.append({
                        'id': i, 
                        'old': q, 
                        'new': ans, 
                        'confidence': conf,
                        'is_error': is_err
                    })
                    bar.progress((i + 1) / len(queries))
                st.rerun()

        if st.session_state.app_data_moi_cu:
            warns = sum(1 for d in st.session_state.app_data_moi_cu if d['is_error'])
            st.success(f"🎉 Hoàn tất {len(st.session_state.app_data_moi_cu)} dòng! (Có {warns} dòng bị Cảnh báo/Lỗi. Sang Tab 'Trạm xuất dữ liệu' để rà soát)")

    elif sub_mode_ai == "Trạm vá lỗi dữ liệu":
        st.markdown("##### 🛠️ Khu vực Cập nhật Địa chỉ CŨ & Nạp Từ Điển vĩnh viễn")
        error_items = [d for d in st.session_state.app_data_moi_cu if d.get('is_error', False)]
        
        if not error_items: 
            st.info("Mọi dữ liệu đang sạch! (Nếu bạn biết 1 địa chỉ Mới tương ứng với địa chỉ Cũ nào, hãy sang Tab 'Trạm xuất dữ liệu' tích ô 🚨 Cấp cứu để đẩy về đây nhập Từ điển)")
        else:
            err_dict = {i['id']: i['old'] for i in error_items}
            sel_id = st.selectbox("Chọn địa chỉ MỚI cần cập nhật thông tin CŨ:", options=list(err_dict.keys()), format_func=lambda x: err_dict[x])
            sel_item = next(i for i in st.session_state.app_data_moi_cu if i['id'] == sel_id)
            
            st.write("Bạn hãy chọn đơn vị hành chính **CŨ** chuẩn xác cho địa chỉ này:")
            c1, c2, c3 = st.columns(3)
            tinh_list = sorted(df['Tỉnh cũ'].astype(str).dropna().unique().tolist()) if not df.empty else []
            tinh_sel = c1.selectbox("Tỉnh/Thành CŨ", ["-- Chọn --"] + tinh_list)
            huyen_sel, xa_sel = "-- Chọn --", "-- Chọn --"
            if tinh_sel != "-- Chọn --":
                huyen_list = sorted(df[df['Tỉnh cũ'] == tinh_sel]['Huyện cũ'].dropna().unique().tolist())
                huyen_sel = c2.selectbox("Quận/Huyện CŨ", ["-- Chọn --"] + huyen_list)
                if huyen_sel != "-- Chọn --":
                    xa_list = sorted(df[(df['Tỉnh cũ'] == tinh_sel) & (df['Huyện cũ'] == huyen_sel)]['Tên Xã cũ'].dropna().unique().tolist())
                    xa_sel = c3.selectbox("Phường/Xã CŨ", ["-- Chọn --"] + xa_list)
            
            if xa_sel != "-- Chọn --":
                prefix, _, _, _ = extract_address_components(normalize_for_search(normalize_formatting(sel_item['old'])))
                suggested_addr = f"{prefix}, {xa_sel}, {huyen_sel}, {tinh_sel}" if prefix else f"{xa_sel}, {huyen_sel}, {tinh_sel}"
                suggested_addr = re.sub(r',\s*,', ',', suggested_addr).strip(', ')
                
                final_edit = st.text_input("✍️ Chỉnh sửa địa chỉ CŨ hoàn chỉnh:", value=suggested_addr)
                
                if st.button("💾 Lưu kết quả & Nạp vào Từ điển", type="primary"):
                    for d in st.session_state.app_data_moi_cu:
                        if d['id'] == sel_id:
                            d.update({'new': final_edit, 'is_error': False, 'confidence': "✅ Lấy từ Từ điển"})
                    
                    st.session_state.dict_moi_cu[sel_item['old']] = {'new': final_edit, 'notes': '✅ Lấy từ Từ điển'}
                    save_dict(st.session_state.dict_moi_cu, DICT_MOI_CU)
                    st.success("Đã ghi nhớ vĩnh viễn vào hệ thống Từ điển Mới ➡️ Cũ!")
                    time.sleep(1)
                    st.rerun()

    elif sub_mode_ai == "Trạm xuất dữ liệu":
        if not st.session_state.app_data_moi_cu:
            st.info("👈 Hãy chạy tính năng chuyển đổi hàng loạt ở Tab đầu tiên!")
        else:
            st.markdown("##### 🚨 Bảng kiểm tra và Xuất dữ liệu (MỚI ➡️ CŨ)")
            st.write("Lướt bảng, nếu thấy Cảnh báo hoặc sai sót, hãy **Tích vào ô vuông 🚨 Cấp cứu** rồi bấm nút đẩy về Trạm Vá.")
            
            df_show = pd.DataFrame(st.session_state.app_data_moi_cu)
            if '🚨 Cấp cứu' not in df_show.columns:
                df_show.insert(0, '🚨 Cấp cứu', False)
                
            cols = ['🚨 Cấp cứu', 'id', 'old', 'new', 'confidence', 'is_error']
            edited_df = st.data_editor(
                df_show[cols], 
                column_config={
                    "🚨 Cấp cứu": st.column_config.CheckboxColumn("🚨 Cấp cứu", default=False),
                    "old": "Địa chỉ MỚI (Đầu vào)",
                    "new": "Địa chỉ CŨ (Kết quả)",
                    "confidence": "Trạng thái",
                },
                disabled=['id', 'old', 'new', 'confidence', 'is_error'],
                hide_index=True,
                use_container_width=True
            )
            
            c1, c2 = st.columns([1, 3])
            with c1:
                if st.button("🛠️ Đẩy các dòng tích về Trạm Vá", type="secondary"):
                    count_pushed = 0
                    for index, row in edited_df.iterrows():
                        if row['🚨 Cấp cứu']:
                            for item in st.session_state.app_data_moi_cu:
                                if item['id'] == row['id']:
                                    item['is_error'] = True
                                    item['confidence'] = "Cần cập nhật Từ điển"
                                    count_pushed += 1
                    if count_pushed > 0:
                        st.success(f"✅ Đã đẩy {count_pushed} dòng về diện cần sửa thủ công!")
                        st.rerun()
            with c2:
                csv_data = pd.DataFrame(st.session_state.app_data_moi_cu)[['old', 'new', 'confidence']].rename(columns={'old': 'Địa chỉ MỚI', 'new': 'Địa chỉ CŨ', 'confidence': 'Trạng thái'}).to_csv(index=False, encoding='utf-8-sig')
                st.download_button("📥 TẢI FILE KẾT QUẢ CSV", data=csv_data, file_name="Ket_Qua_Moi_Cu.csv", mime="text/csv", type="primary")

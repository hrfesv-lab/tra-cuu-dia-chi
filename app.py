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
# 2. HÀM XỬ LÝ EXCEL & DỮ LIỆU CHUẨN
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

# HÀM BÓC TÁCH PHẦN SỐ NHÀ/ĐƯỜNG/THÔN/XÓM TỰ ĐỘNG
def extract_street_prefix(address_str):
    if not address_str: return ""
    parts = [p.strip() for p in address_str.split(',') if p.strip()]
    street_parts = []
    
    for p in parts:
        # Nếu bắt gặp các từ khóa đơn vị hành chính thì dừng bóc tách
        if re.search(r'(?i)\b(phường|xã|thị trấn|quận|huyện|thành phố|tỉnh|p\.|x\.|tt\.|q\.|h\.|tp\.|t\.)\b', p) or \
           re.match(r'(?i)^(p|x|tt|q|h|tx|tp)\s*\d+', p):
            break
        street_parts.append(p)
        
    if street_parts:
        return ", ".join(street_parts)
    # Nếu không tách được theo dấu phẩy, lấy phần tử đầu tiên làm mặc định
    return parts[0] if parts else ""

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
    progress_bar = st.progress(0, text="Đang phân tích và đánh giá độ tin cậy...")
    
    for idx, batch in enumerate(batches):
        prompt = f"""
        Bạn là chuyên gia địa giới hành chính Việt Nam. Tra ngược danh sách địa chỉ MỚI sau đây về địa chỉ CŨ (trước sáp nhập 2025).
        Danh sách:
        {json.dumps(batch, ensure_ascii=False)}
        
        Yêu cầu BẮT BUỘC:
        1. Trả về kết quả dưới dạng JSON hợp lệ. Key là địa chỉ gốc, Value là một Object chứa 2 trường: "address" và "confidence".
        2. Trường "confidence" ghi nhận mức độ tin cậy:
           - "Cao": Nếu biết rõ lịch sử sáp nhập/địa giới chính xác.
           - "Trung bình": Nếu giữ nguyên địa chỉ hoặc sửa lỗi chính tả nhẹ.
           - "Nghi ngờ": Nếu địa chỉ bị mâu thuẫn lớn (VD: tên phường ở tỉnh này nhưng đuôi lại ghi tỉnh khác), thiếu thông tin nghiêm trọng, hoặc bạn không chắc chắn.
        3. Trường "address": Chuỗi địa chỉ dự đoán theo format "[Số nhà/Đường], [Phường/Xã cũ], [Quận/Huyện cũ], [Tỉnh/Thành phố cũ]".
        """
        
        max_retries, delay = 3, 2
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                text_res = response.text.strip()
                if text_res.startswith("```json"): text_res = text_res[7:-3].strip()
                elif text_res.startswith("```"): text_res = text_res[3:-3].strip()
                    
                parsed_data = json.loads(text_res)
                for k, v in parsed_data.items():
                    if isinstance(v, dict):
                        res_obj = {"address": v.get("address", ""), "confidence": v.get("confidence", "Nghi ngờ")}
                    else:
                        res_obj = {"address": str(v), "confidence": "Nghi ngờ"}
                    
                    st.session_state.ai_cache[k] = res_obj
                    all_results[k] = res_obj
                break
            except Exception:
                if attempt < max_retries - 1: time.sleep(delay); delay *= 2
                else:
                    for addr in batch: 
                        all_results[addr] = {"address": addr, "confidence": "Nghi ngờ"}
                    
        time.sleep(1)
        progress_bar.progress((idx + 1) / len(batches), text=f"Đang xử lý gói {idx + 1}/{len(batches)}...")
        
    progress_bar.empty()
    return all_results

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
            tinh_list = sorted(df['Tỉnh cũ'].dropna().unique().tolist())
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
# PHÂN HỆ 2: CHUYỂN MỚI -> CŨ (AI)
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
            "container": {"padding": "3px", "background-color": "#f8f9fa", "border-radius": "8px", "margin-bottom": "15px", "border": "1px solid #e9ecef"},
            "icon": {"font-size": "13px"},
            "nav-link": {"font-size": "13px", "border-radius": "6px", "padding": "6px 15px"},
            "nav-link-selected": {"background-color": "#ffffff", "color": "#0d6efd", "font-weight": "600", "box-shadow": "0px 1px 4px rgba(0,0,0,0.05)"},
        }
    )

    if sub_mode_ai == "Chuyển đổi hàng loạt":
        input_text_ai = st.text_area("Nhập danh sách địa chỉ mới/sáp nhập cần dịch ngược:", height=180, key="ai_input", placeholder="Ví dụ:\n1118 Kha Vạn Cân, Phường Thủ Đức, TP HCM\nK29/2 Nguyễn Như Đãi, Phường Cẩm Lệ, Đà Nẵng...")
        if st.button("⏪ Yêu cầu AI dịch ngược", type="primary", key="btn_ai"):
            if not selected_model: st.warning("⚠️ Vui lòng nhập API Key hợp lệ ở bảng cấu hình phía trên trước!")
            elif input_text_ai.strip():
                st.session_state.ai_cache = {}
                queries = [q.strip() for q in input_text_ai.split('\n') if q.strip()]
                model = genai.GenerativeModel(selected_model)
                results = process_batch_with_intelligence(model, queries)
                
                st.session_state.app_data_ai = []
                for i, q in enumerate(queries):
                    res_obj = results.get(q, {"address": q, "confidence": "Nghi ngờ"})
                    conf = res_obj.get("confidence", "Nghi ngờ")
                    is_err = conf == "Nghi ngờ"
                    
                    st.session_state.app_data_ai.append({
                        'id': i, 
                        'old': q, 
                        'new': res_obj.get("address", ""), 
                        'confidence': conf,
                        'is_error': is_err
                    })
                st.rerun()

        if st.session_state.app_data_ai:
            suspects = sum(1 for d in st.session_state.app_data_ai if d['is_error'])
            st.success(f"🎉 Đã phân tích xong {len(st.session_state.app_data_ai)} dòng. (Có {suspects} ca nghi ngờ ➡️ Chọn tab 'Trạm cấp cứu AI' để kiểm tra lại)")

    # TRẠM CẤP CỨU AI: TỰ ĐỘNG BÓC TÁCH PREFIX VÀ GHÉP VỚI ĐƠN VỊ CỦ ĐƯỢC CHỌN
    elif sub_mode_ai == "Trạm cấp cứu AI":
        suspect_items = [d for d in st.session_state.app_data_ai if d['is_error']]
        if not suspect_items: st.info("🎉 Tất cả địa chỉ đều có độ tin cậy Cao/Trung bình!")
        else:
            st.warning("Các địa chỉ dưới đây bị nghi ngờ hoặc gõ sai. Bạn có thể chọn địa bàn MỚI chuẩn để xem Bảng tham chiếu các Xã CŨ tương ứng!")
            err_dict_ai = {i['id']: f"{i['old']} ➡️ [AI đoán: {i['new']}]" for i in suspect_items}
            sel_id_ai = st.selectbox("Chọn địa chỉ cần cấp cứu/xác nhận:", options=list(err_dict_ai.keys()), format_func=lambda x: err_dict_ai[x], key="ai_err_select")
            sel_item_ai = next(i for i in st.session_state.app_data_ai if i['id'] == sel_id_ai)
            
            c1, c2 = st.columns(2)
            tinh_list_new = sorted(df['Tỉnh mới'].dropna().unique().tolist())
            tinh_sel_new = c1.selectbox("1. Chọn Tỉnh/Thành MỚI chuẩn", ["-- Chọn --"] + tinh_list_new, key="tinh_sel_new")
            
            xa_sel_new = "-- Chọn --"
            if tinh_sel_new != "-- Chọn --":
                df_tinh = df[df['Tỉnh mới'] == tinh_sel_new]
                xa_sel_new = c2.selectbox("2. Chọn Phường/Xã MỚI chuẩn", ["-- Chọn --"] + sorted(df_tinh['Tên Xã mới'].dropna().unique().tolist()), key="xa_sel_new")
            
            if xa_sel_new != "-- Chọn --":
                matched_rows = df[(df['Tỉnh mới'] == tinh_sel_new) & (df['Tên Xã mới'] == xa_sel_new)]
                
                st.markdown(f"""
                <div class="ref-box">
                    💡 <b>BẢNG THAM CHIẾU ĐỊA GIỚI:</b><br>
                    Địa bàn <b>{xa_sel_new} ({tinh_sel_new})</b> được hợp nhất/sáp nhập từ <b>{len(matched_rows)}</b> đơn vị cũ dưới đây:
                </div>
                """, unsafe_allow_html=True)
                
                st.dataframe(matched_rows[['Tên Xã cũ', 'Huyện cũ', 'Tỉnh cũ']].reset_index(drop=True), use_container_width=True)
                
                old_options = [f"{row['Tên Xã cũ']}, {row['Huyện cũ']}, {row['Tỉnh cũ']}" for _, row in matched_rows.iterrows()]
                selected_old_unit = st.selectbox("3. Chọn Đơn vị CŨ gốc chính xác cho địa chỉ này:", options=old_options, key="old_unit_select")
                
                # TỰ ĐỘNG BÓC TÁCH SỐ NHÀ/ĐƯỜNG/THÔN/XÓM TỪ ĐỊA CHỈ ĐẦU VÀO
                street_prefix = extract_street_prefix(sel_item_ai['old'])
                
                # TỰ ĐỘNG GHÉP NỐI PREFIX VỚI ĐƠN VỊ CỦ CHỌN TỪ DROPDOWN
                sug_addr_old = f"{street_prefix}, {selected_old_unit}" if street_prefix else selected_old_unit
                
                final_edit_ai = st.text_input("✍️ Địa chỉ CŨ chuẩn hoàn chỉnh (Đã tự động kết hợp):", value=sug_addr_old, key="edit_ai_input")
                
                if st.button("💾 Xác nhận lưu địa chỉ CŨ chuẩn này", type="primary", key="save_ai_fix"):
                    for d in st.session_state.app_data_ai:
                        if d['id'] == sel_id_ai:
                            d.update({'new': final_edit_ai, 'confidence': 'Đã xác nhận', 'is_error': False})
                    st.rerun()

    elif sub_mode_ai == "Trạm xuất dữ liệu":
        if st.session_state.app_data_ai:
            df_out_ai = pd.DataFrame(st.session_state.app_data_ai)[['old', 'new', 'confidence']].rename(
                columns={'old': 'Địa chỉ Đầu vào', 'new': 'Địa chỉ AI Dịch ngược', 'confidence': 'Mức độ tin cậy'}
            )
            st.dataframe(df_out_ai, use_container_width=True)
            st.download_button("📥 Tải file CSV", data=df_out_ai.to_csv(index=False, encoding='utf-8-sig'), file_name="Data_ChuyenDoi_AI.csv", mime="text/csv", type="primary", key="dl_ai")
        else: st.info("Chưa có dữ liệu. Vui lòng chạy phân tích AI ở tab đầu tiên trước!")

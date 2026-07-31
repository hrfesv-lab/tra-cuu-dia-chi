import streamlit as st
import pandas as pd
import re

# ==========================================
# 1. NẠP DỮ LIỆU (2 LỚP: XÃ & TỈNH)
# ==========================================
@st.cache_data
def load_data():
    # Load file cấp Xã
    try:
        df_xa = pd.read_csv("Master_Database_63_Tinh.csv")
        df_xa['Length'] = df_xa['Địa chỉ CŨ'].astype(str).apply(len)
        df_xa = df_xa.sort_values(by='Length', ascending=False)
    except Exception:
        df_xa = pd.DataFrame(columns=['Địa chỉ CŨ', 'Địa chỉ MỚI', 'Trạng thái'])
        
    # Load file cấp Tỉnh
    try:
        df_tinh = pd.read_csv("Tinh_Huyen.csv")
        df_tinh['Length'] = df_tinh['Địa chỉ CŨ'].astype(str).apply(len)
        df_tinh = df_tinh.sort_values(by='Length', ascending=False)
    except Exception:
        df_tinh = pd.DataFrame(columns=['Địa chỉ CŨ', 'Địa chỉ MỚI', 'Trạng thái'])
        
    return df_xa, df_tinh

df_xa, df_tinh = load_data()

# ==========================================
# ==========================================
# 2. HÀM XỬ LÝ LÕI (THAY THẾ CHUẨN XÁC)
# ==========================================
def replace_entity(address, df_ref):
    addr_lower = address.lower()
    new_addr = address
    note = ""
    
    for _, row in df_ref.iterrows():
        old_place = str(row['Địa chỉ CŨ'])
        old_place_lower = old_place.lower()
        
        if old_place_lower in addr_lower:
            idx = addr_lower.find(old_place_lower)
            end_idx = idx + len(old_place_lower)
            
            if end_idx < len(addr_lower) and addr_lower[end_idx].isalnum():
                continue 
            
            pattern = re.compile(re.escape(old_place), re.IGNORECASE)
            new_addr = pattern.sub(str(row['Địa chỉ MỚI']), new_addr)
            
            note = f"Đổi {old_place} ➡️ {row['Địa chỉ MỚI']}"
            if "một phần" in str(row.get('Trạng thái', '')).lower():
                note += " (⚠️ Sáp nhập 1 phần)"
            break
            
    return new_addr, note

def convert_address(query):
    if not query:
        return query, "Trống"
    
    current_addr = query
    notes = []
    
    # 🔥 BƯỚC 1: DÒ VÀ ĐỔI TỈNH/HUYỆN TRƯỚC
    if not df_tinh.empty:
        current_addr, note_tinh = replace_entity(current_addr, df_tinh)
        if note_tinh:
            notes.append(note_tinh)
            
    # 🔥 BƯỚC 2: DÒ VÀ ĐỔI XÃ/PHƯỜNG SAU
    if not df_xa.empty:
        current_addr, note_xa = replace_entity(current_addr, df_xa)
        if note_xa:
            notes.append(note_xa)
            
    # Tổng hợp ghi chú (Hiển thị Tỉnh trước, Xã sau cho thuận mắt)
    if not notes:
        final_note = "Giữ nguyên"
    else:
        final_note = " | ".join(notes)
        
    return current_addr, final_note

# ==========================================
# 3. GIAO DIỆN WEB
# ==========================================
st.set_page_config(page_title="Chuyển đổi Địa chỉ", page_icon="🏛️", layout="wide")
st.title("🏛️ CÔNG CỤ CHUYỂN ĐỔI ĐỊA CHỈ HÀNH CHÍNH")
st.markdown("Nhập toàn bộ địa chỉ cũ vào bên trái. Máy sẽ tự động quy đổi tên Xã/Phường và Tỉnh/Thành phố.")

col1, col2 = st.columns(2)

with col1:
    input_text = st.text_area(
        "Nhập địa chỉ cũ (mỗi địa chỉ 1 dòng):", 
        height=300, 
        placeholder="Ví dụ:\n113 Võ Duy Ninh, Phường 22, Quận Bình Thạnh, Thành phố Hồ Chí Minh\nKhu công nghiệp A, tỉnh Hà Tây"
    )
    search_button = st.button("🔄 Chuyển đổi ngay", type="primary", use_container_width=True)

with col2:
    if search_button:
        if input_text.strip():
            queries = [q.strip() for q in input_text.split('\n') if q.strip()]
            results = []
            
            for query in queries:
                new_addr, status_note = convert_address(query)
                results.append({
                    "Địa chỉ bạn nhập": query,
                    "Địa chỉ SAU chuyển đổi": new_addr,
                    "Ghi chú chi tiết": status_note
                })
            
            df_results = pd.DataFrame(results)
            st.dataframe(df_results, use_container_width=True)
            
            csv_data = df_results.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Tải file kết quả (CSV)",
                data=csv_data,
                file_name="Ket_Qua_Dia_Chi_Moi.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.warning("Vui lòng nhập địa chỉ vào ô bên trái.")

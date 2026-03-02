import streamlit as st
import fitz  # PyMuPDF
from io import BytesIO
from PIL import Image
import zipfile
import os
import gc


def hex_to_rgb(hex_color):
    """Converte '#RRGGBB' in (r, g, b) per PyMuPDF (0.0-1.0)"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))

# Configurazione Pagina
st.set_page_config(page_title="PDF Stamper CRIT", page_icon="📝", layout="wide")

st.title("📝 PDF Stamper CRIT")

# --- SIDEBAR: CONFIGURAZIONE ---
with st.sidebar:
    st.header("⚙️ 1. Configurazione Timbro")
    stamp_file = st.file_uploader("Carica Timbro (PNG/JPG)", type=["png", "jpg", "jpeg"])

    if stamp_file:
        # Opzioni Timbro
        dim_timbro = st.slider("Dimensione (px):", 50, 400, 150)

        st.subheader("📍 Posizionamento")
        # Checkbox per decidere se usare la parola chiave o la posizione fissa
        usa_keyword = st.checkbox("Cerca parola chiave", value=True)

        keyword = ""
        if usa_keyword:
            keyword = st.text_input("Parola da cercare:", value="Firma")
            st.caption("Se la parola non viene trovata, si userà la posizione fissa nell'ultima pagina.")

        st.write("Griglia di allineamento (rispetto alla parola o alla pagina):")

        if 'pos_choice' not in st.session_state:
            st.session_state.pos_choice = "Sotto"

        # Griglia 3x3
        c1, c2, c3 = st.columns(3)
        if c1.button("↖️"): st.session_state.pos_choice = "Top-Left"
        if c2.button("⬆️"): st.session_state.pos_choice = "Sopra"  # o Top-Center per pagina
        if c3.button("↗️"): st.session_state.pos_choice = "Top-Right"

        c4, c5, c6 = st.columns(3)
        if c4.button("⬅️"): st.session_state.pos_choice = "Sinistra"
        if c5.button("🎯"): st.session_state.pos_choice = "Sovrapposto"  # Center
        if c6.button("➡️"): st.session_state.pos_choice = "Destra"

        c7, c8, c9 = st.columns(3)
        if c7.button("↙️"): st.session_state.pos_choice = "Bottom-Left"
        if c8.button("⬇️"): st.session_state.pos_choice = "Sotto"  # o Bottom-Center
        if c9.button("↘️"): st.session_state.pos_choice = "Bottom-Right"

        st.info(f"Allineamento: **{st.session_state.pos_choice}**")

        # SPOSTAMENTO MANUALE (Offset)
        st.markdown("---")
        st.write("📐 **Regolazione Fine (Offset)**")
        col_x, col_y = st.columns(2)
        offset_x = col_x.number_input("Sposta X (px)", value=0, step=10, help="Negativo: sinistra, Positivo: destra")
        offset_y = col_y.number_input("Sposta Y (px)", value=0, step=10, help="Negativo: su, Positivo: giù")

    st.divider()
    st.header("📝 2. Configurazione Testo")
    testo_progetto = st.text_area("Testo in calce:",
                                  value="")
    colore_testo = st.color_picker("Colore testo", "#000000")
    margine_testo = st.slider("Distanza dal fondo (px):", 10, 200, 50, help="Aumenta per alzare il testo")


# --- FUNZIONI DI CALCOLO ---

def elabora_timbro_bianco(uploaded_file):
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    else:
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def get_rect_by_keyword(inst, scelta, size, off_x, off_y):
    """Calcola posizione relativa alla parola trovata"""
    w, h = size, size // 2
    off = 8
    cx, cy = (inst.x0 + inst.x1) / 2, (inst.y0 + inst.y1) / 2

    # Base coordinates
    coords = {
        "Top-Left": (inst.x0 - w, inst.y0 - h - off),
        "Sopra": (cx - w / 2, inst.y0 - h - off),
        "Top-Right": (inst.x1, inst.y0 - h - off),
        "Sinistra": (inst.x0 - w - off, cy - h / 2),
        "Sovrapposto": (cx - w / 2, cy - h / 2),
        "Destra": (inst.x1 + off, cy - h / 2),
        "Bottom-Left": (inst.x0 - w, inst.y1 + off),
        "Sotto": (cx - w / 2, inst.y1 + off),
        "Bottom-Right": (inst.x1, inst.y1 + off),
    }
    base_x, base_y = coords.get(scelta, coords["Sotto"])
    # Apply manual offset
    return fitz.Rect(base_x + off_x, base_y + off_y, base_x + w + off_x, base_y + h + off_y)


def get_rect_absolute(page_rect, scelta, size, off_x, off_y):
    """Calcola posizione assoluta nella pagina (se manca parola chiave)"""
    w, h = size, size // 2
    W, H = page_rect.width, page_rect.height
    margin = 50  # Margine standard dai bordi

    # Coordinate centro pagina
    cx, cy = W / 2, H / 2

    # Mappa le posizioni 3x3 sulla pagina intera
    coords = {
        "Top-Left": (margin, margin),
        "Sopra": (cx - w / 2, margin),
        "Top-Right": (W - w - margin, margin),
        "Sinistra": (margin, cy - h / 2),
        "Sovrapposto": (cx - w / 2, cy - h / 2),  # Centro pagina esatto
        "Destra": (W - w - margin, cy - h / 2),
        "Bottom-Left": (margin, H - h - margin),
        "Sotto": (cx - w / 2, H - h - margin),  # Centro basso (Standard firma)
        "Bottom-Right": (W - w - margin, H - h - margin),
    }

    base_x, base_y = coords.get(scelta, coords["Sotto"])
    return fitz.Rect(base_x + off_x, base_y + off_y, base_x + w + off_x, base_y + h + off_y)


# --- GENERATORE ANTEPRIMA ---
def genera_anteprima(file_bytes, stamp_bytes):
    """Genera un'immagine dell'ultima pagina con le modifiche applicate"""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc[-1]  # Anteprima sull'ultima pagina

    # 1. Timbro
    if stamp_bytes:
        # Proviamo a cercare la parola nell'ultima pagina
        timbro_applicato = False
        if usa_keyword and keyword.strip():
            instances = page.search_for(keyword)
            # Prendiamo l'ultima occorrenza nella pagina per l'anteprima
            if instances:
                rect = get_rect_by_keyword(instances[-1], st.session_state.pos_choice, dim_timbro, offset_x, offset_y)
                page.insert_image(rect, stream=stamp_bytes)
                timbro_applicato = True

        # Se non applicato (o parola non trovata), usa posizione assoluta
        if not timbro_applicato:
            rect = get_rect_absolute(page.rect, st.session_state.pos_choice, dim_timbro, offset_x, offset_y)
            page.insert_image(rect, stream=stamp_bytes)

    # 2. Testo
    if testo_progetto.strip():
        # Usa posizione fissa dal basso regolata da slider (Infallibile)
        text_y0 = page.rect.height - margine_testo - 40  # 40px stima altezza testo
        text_rect = fitz.Rect(50, text_y0, page.rect.width - 50, page.rect.height - margine_testo + 10)

        page.insert_textbox(
            text_rect,
            testo_progetto,
            fontsize=10,
            fontname="Helvetica-Bold",
            color=hex_to_rgb(colore_testo),
            align=1
        )

    pix = page.get_pixmap(dpi=100)  # Renderizza immagine
    doc.close()
    return Image.open(BytesIO(pix.tobytes()))


# --- INTERFACCIA PRINCIPALE ---

# 1. Input File
st.subheader("📁 1. Caricamento")
files = st.file_uploader("Trascina i tuoi PDF qui", type=["pdf"], accept_multiple_files=True)

# 2. Anteprima (Se ci sono file)
if files:
    st.divider()
    st.subheader("👁️ Anteprima (Ultima pagina del primo file)")

    stamp_bin = elabora_timbro_bianco(stamp_file) if stamp_file else None

    # Genera anteprima live leggendo solo il primo file al volo
    try:
        preview_img = genera_anteprima(files[0].getvalue(), stamp_bin)
        st.image(preview_img, caption="Risultato atteso", use_container_width=True)
        st.caption("Nota: L'anteprima mostra dove finiranno Timbro e Testo. Usa i controlli a sinistra per spostarli.")
    except Exception as e:
        st.error(f"Errore anteprima: {e}")

# 3. Elaborazione
st.divider()
if files and (stamp_file or testo_progetto.strip()):
    if st.button("🚀 APPLICA A TUTTI I DOCUMENTI", type="primary"):
        stamp_bin = elabora_timbro_bianco(stamp_file) if stamp_file else None
        results = []
        bar = st.progress(0)

        for i, f in enumerate(files):
            # Legge il file in memoria SOLO in questo momento
            file_bytes = f.getvalue()
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            modified = False

            # --- LOOP PAGINE ---
            for page_num, page in enumerate(doc):
                # TIMBRO
                if stamp_bin:
                    applied_on_page = False
                    # Caso A: Parola Chiave
                    if usa_keyword and keyword.strip():
                        hits = page.search_for(keyword)
                        for inst in hits:
                            r = get_rect_by_keyword(inst, st.session_state.pos_choice, dim_timbro, offset_x, offset_y)
                            page.insert_image(r, stream=stamp_bin)
                            modified = True
                            applied_on_page = True

                    # Caso B: Posizione Fissa (Solo ultima pagina se keyword fallisce o non richiesta)
                    is_last_page = (page_num == len(doc) - 1)

                    if is_last_page and not applied_on_page:
                        r = get_rect_absolute(page.rect, st.session_state.pos_choice, dim_timbro, offset_x, offset_y)
                        page.insert_image(r, stream=stamp_bin)
                        modified = True

            # TESTO (Solo ultima pagina)
            if testo_progetto.strip():
                page = doc[-1]
                text_y0 = page.rect.height - margine_testo - 40
                tr = fitz.Rect(50, text_y0, page.rect.width - 50, page.rect.height - margine_testo + 10)
                page.insert_textbox(
                    tr, testo_progetto, fontsize=10, fontname="Helvetica-Bold",
                    color=hex_to_rgb(colore_testo), align=1
                )
                modified = True

            if modified:
                out = BytesIO()
                doc.save(out)
                results.append((f.name, out.getvalue()))

            # --- PULIZIA RAM (Fondamentale per il SaaS) ---
            doc.close()
            del doc
            del file_bytes
            gc.collect()  # Forza lo svuotamento della memoria per questo ciclo

            bar.progress((i + 1) / len(files))

        # DOWNLOAD
        if len(results) == 1:
            st.download_button("📥 Scarica PDF", results[0][1], results[0][0], "application/pdf")
        elif len(results) > 1:
            z = BytesIO()
            with zipfile.ZipFile(z, "a", zipfile.ZIP_DEFLATED) as zf:
                for n, d in results: zf.writestr(n, d)
            st.success(f"Fatto! {len(results)} file processati.")
            st.download_button("📥 Scarica ZIP", z.getvalue(), "Timbri_CRIT.zip", "application/zip")
        else:
            st.warning("Nessuna modifica applicata.")

else:
    if files:
        st.info("👈 Configura Timbro o Testo nella barra laterale per iniziare.")
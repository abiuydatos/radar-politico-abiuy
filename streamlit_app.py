import csv
import io
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import streamlit as st

st.set_page_config(page_title="Radar Político | Abiuy", page_icon="📡", layout="wide")
st.title("📡 Radar Político")
st.caption("Observatorio de conversación pública | ABIUY · Versión 0.1")
st.info("Primera fuente: Google News (noticias indexadas). Todavía no mide menciones de X, Instagram o Facebook.")

TEMAS = {
    "Seguridad": ["seguridad", "policía", "policia", "delito", "homicidio", "narcotráfico", "narcotrafico"],
    "Economía": ["economía", "economia", "impuesto", "empleo", "salario", "presupuesto"],
    "Parlamento": ["senado", "senador", "parlamento", "comisión", "comision", "proyecto de ley", "diputados"],
    "Educación": ["educación", "educacion", "escuela", "universidad", "liceo"],
    "Política partidaria": ["partido colorado", "coalición", "coalicion", "frente amplio", "partido nacional"],
}
STOPWORDS = set("sobre desde entre hasta junto tras ante para como este esta estos estas esas esos pero porque donde cuando quien quienes algo todo toda todos todas desde hacia tiene tuvo será fueron esta está entre unas unos uruguay bordaberry pedro senado senador".split())

@st.cache_data(ttl=1800, show_spinner=False)
def buscar_noticias(consulta, dias):
    # Google News RSS devuelve una muestra de noticias indexadas, no un censo de las redes.
    consulta_rss = f'{consulta} when:{dias}d'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": consulta_rss, "hl": "es-419", "gl": "UY", "ceid": "UY:es-419"
    })
    solicitud = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 RadarPolitico/0.1"})
    with urllib.request.urlopen(solicitud, timeout=12) as respuesta:
        raiz = ET.fromstring(respuesta.read())
    encontrados = []
    for item in raiz.findall("./channel/item"):
        titulo = (item.findtext("title") or "").strip()
        enlace = (item.findtext("link") or "").strip()
        origen = item.find("source")
        fuente = origen.text.strip() if origen is not None and origen.text else "Sin identificar"
        fecha_raw = item.findtext("pubDate") or ""
        try:
            fecha = parsedate_to_datetime(fecha_raw).astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
        if fecha >= datetime.now(timezone.utc) - timedelta(days=dias) and titulo and enlace:
            encontrados.append({"fecha": fecha.date().isoformat(), "titulo": titulo,
                                "fuente": fuente, "url": enlace})
    return list({n["url"]: n for n in encontrados}.values())

with st.sidebar:
    st.header("Configuración")
    persona = st.text_input("Dirigente", "Pedro Bordaberry")
    contexto = st.text_input("Tema o contexto", "Senado")
    dias = st.selectbox("Período", [7, 14, 30], index=0, format_func=lambda x: f"Últimos {x} días")
    st.caption("Por defecto busca el nombre completo y el contexto indicados.")

if not persona.strip():
    st.warning("Escribí un nombre para comenzar.")
    st.stop()

consulta = f'"{persona.strip()}" {contexto.strip()}'.strip()
st.write(f"**Búsqueda:** `{consulta}`")
if st.button("🔎 Buscar noticias", type="primary"):
    try:
        with st.spinner("Consultando Google News…"):
            st.session_state["noticias"] = buscar_noticias(consulta, dias)
            st.session_state["ultima_consulta"] = consulta
            st.session_state["periodo"] = dias
            st.session_state.pop("error", None)
    except Exception as e:
        st.session_state.pop("noticias", None)
        st.session_state["error"] = f"No se pudo consultar el RSS: {type(e).__name__}. Probá de nuevo más tarde."

if "error" in st.session_state:
    st.error(st.session_state["error"])

noticias = st.session_state.get("noticias")
if noticias is None:
    st.write("Presioná **Buscar noticias** para cargar registros reales.")
    st.stop()

st.caption(f"Consulta cargada: {st.session_state.get('ultima_consulta')} · {st.session_state.get('periodo')} días. Volvé a buscar si cambiaste los filtros.")
tab_resumen, tab_publicaciones, tab_chat = st.tabs(["📊 Resumen", "📰 Publicaciones", "💬 Consultas"])
conteo_fuentes = Counter(n["fuente"] for n in noticias)
conteo_fechas = Counter(n["fecha"] for n in noticias)
conteo_temas = Counter()
for n in noticias:
    t = n["titulo"].casefold()
    for tema, palabras in TEMAS.items():
        if any(p in t for p in palabras):
            conteo_temas[tema] += 1
palabras = Counter(w for n in noticias for w in re.findall(r"[a-záéíóúñü]{4,}", n["titulo"].lower()) if w not in STOPWORDS)

with tab_resumen:
    a, b, c = st.columns(3)
    a.metric("Noticias encontradas", len(noticias))
    b.metric("Medios identificados", len(conteo_fuentes))
    c.metric("Días con noticias", len(conteo_fechas))
    st.caption("Son artículos devueltos por Google News RSS, no menciones totales de redes sociales. Los tópicos pueden superponerse.")
    if noticias:
        st.subheader("Evolución diaria")
        st.bar_chart({"Noticias": dict(sorted(conteo_fechas.items()))})
        st.subheader("Temas detectados en titulares")
        if conteo_temas:
            st.bar_chart({"Noticias con el tema": dict(conteo_temas.most_common())})
        else:
            st.write("No aparecen los temas del diccionario en los titulares recolectados.")
        st.subheader("Palabras frecuentes en titulares")
        st.write(" · ".join(f"**{p}** ({n})" for p, n in palabras.most_common(15)) or "Sin datos")
    else:
        st.warning("No encontramos noticias para esta búsqueda y período. Probá quitando el contexto o usando 30 días.")

with tab_publicaciones:
    if noticias:
        medios = sorted(conteo_fuentes)
        seleccion = st.multiselect("Filtrar medios", medios, default=medios)
        filtradas = [n for n in noticias if n["fuente"] in seleccion]
        for n in sorted(filtradas, key=lambda x: x["fecha"], reverse=True):
            st.markdown(f'**{n["fecha"]} · {n["fuente"]}**')
            st.link_button(n["titulo"], n["url"])
        salida = io.StringIO()
        escritor = csv.DictWriter(salida, fieldnames=["fecha", "titulo", "fuente", "url"])
        escritor.writeheader()
        escritor.writerows(filtradas)
        st.download_button("⬇️ Descargar CSV", salida.getvalue().encode("utf-8-sig"), "radar_politico.csv", "text/csv")
    else:
        st.write("No hay publicaciones para mostrar.")

with tab_chat:
    st.write("**Consultas guiadas sobre los datos cargados** (todavía no es un chat de IA).")
    pregunta = st.selectbox("¿Qué querés saber?", ["¿Cuántas noticias hay?", "¿Qué medios publicaron más?", "¿Qué temas aparecen?", "¿Cuáles son las palabras más frecuentes?"])
    if pregunta == "¿Cuántas noticias hay?":
        st.write(f"La búsqueda devolvió **{len(noticias)}** noticias indexadas en el período elegido.")
    elif pregunta == "¿Qué medios publicaron más?":
        st.write("; ".join(f"{medio}: {n}" for medio, n in conteo_fuentes.most_common(10)) or "No hay datos.")
    elif pregunta == "¿Qué temas aparecen?":
        st.write("; ".join(f"{tema}: {n}" for tema, n in conteo_temas.most_common()) or "Ninguno de los temas predefinidos.")
    else:
        st.write("; ".join(f"{palabra}: {n}" for palabra, n in palabras.most_common(15)) or "No hay datos.")
    st.caption("La evidencia está en la pestaña Publicaciones. Esta versión solo analiza titulares, no artículos completos.")

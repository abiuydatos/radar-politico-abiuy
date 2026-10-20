        rows.append({'fecha':dt.isoformat(),'plataforma':r['plataforma'].strip(),'autor':r['autor'].strip(),'texto':r['texto'].strip(),'url':r['url'].strip(),'metricas_disponibles':has_metrics,**metrics})
    return rows

def dedup(rows):
    return list({r['url'].split('?')[0].rstrip('/'):r for r in rows if r.get('url')}.values())

if 'registros' not in st.session_state: st.session_state.registros=[]
if 'estado_fuentes' not in st.session_state: st.session_state.estado_fuentes=[]
with st.sidebar:
    st.header('Configuración')
    persona=st.text_input('Dirigente o expresión', 'Pedro Bordaberry')
    tema=st.text_input('Tema (opcional)', 'Senado')
    dias=st.selectbox('Período', [1,7,14,30], index=1, format_func=lambda x:f'Últimos {x} días')
    news=st.checkbox('Google News', value=True)
    bluesky=st.checkbox('Bluesky', value=True)
    st.caption('Solo se miden las publicaciones efectivamente recuperadas. La búsqueda de Bluesky consulta hasta 100 resultados recientes por ejecución.')
    run=st.button('🔄 Actualizar fuentes', type='primary', use_container_width=True)
    st.divider()
    uploaded=st.file_uploader('Importar publicaciones (CSV)', type=['csv'])
    if uploaded and st.button('Agregar CSV a la sesión'):
        try:
            imported=load_csv(uploaded)
            st.session_state.registros=dedup(st.session_state.registros+imported)
            st.success(f'Importados {len(imported)} registros válidos (antes de deduplicar).')
        except (ValueError,UnicodeDecodeError) as exc:
            st.error(f'CSV inválido: {exc}')
    template='fecha,plataforma,autor,texto,url,likes,comentarios,compartidos\n2026-10-20T09:00:00-03:00,X,cuenta_ejemplo,Texto de ejemplo,https://example.com/publicacion,12,3,2\n'
    st.download_button('⬇️ Plantilla CSV (ejemplo)', template.encode('utf-8-sig'), 'plantilla_radar.csv', 'text/csv',use_container_width=True)
    st.caption('La fila de la plantilla es ficticia: no la importes como dato real.')

if run:
    query=f'"{persona.strip()}" {tema.strip()}'.strip()
    if not persona.strip(): st.error('Escribí una expresión para buscar.')
    else:
        status=[]; fetched=[]
        with st.spinner('Recuperando registros de las fuentes habilitadas…'):
            for active,label,fn in [(news,'Google News',get_news),(bluesky,'Bluesky',get_bluesky)]:
                if not active: continue
                try:
                    found=fn(query,dias)
                    fetched.extend(found)
                    status.append(f'{label}: {len(found)} registros devueltos')
                except Exception as exc:
                    status.append(f'{label}: no disponible ({type(exc).__name__})')
        st.session_state.registros=dedup(st.session_state.registros+fetched)
        st.session_state.estado_fuentes=status
        st.session_state.actualizado=datetime.now(timezone.utc).isoformat()

for item in st.session_state.estado_fuentes: st.caption('• '+item)
if 'actualizado' in st.session_state: st.caption('Última consulta: '+st.session_state.actualizado+' UTC')

all_rows=dedup(st.session_state.registros)
cutoff=datetime.now(timezone.utc)-timedelta(days=dias)
rows=[]
for r in all_rows:
    try:
        dt=datetime.fromisoformat(r['fecha'].replace('Z','+00:00'))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        if dt>=cutoff: rows.append(r)
    except (ValueError,TypeError): pass

platforms=sorted({r['plataforma'] for r in rows})
selected=st.multiselect('Filtrar fuentes',platforms,default=platforms)
rows=[r for r in rows if r['plataforma'] in selected]
terms=Counter()
topics=Counter()
for r in rows:
    txt=norm(r['texto'])
    words=re.findall(r'[a-z]{4,}',txt)
    terms.update(w for w in words if w not in STOP and w not in set(re.findall(r'[a-z]{4,}',norm(persona))))
    for topic,keys in CATEGORIAS.items():
        if any(norm(k) in txt for k in keys):topics[topic]+=1

summary, words_tab, posts_tab, chat_tab=st.tabs(['📊 Resumen','🔤 Palabras y tópicos','🗂️ Publicaciones','💬 Consultas'])
with summary:
    a,b,c,d=st.columns(4)
    a.metric('Publicaciones registradas',len(rows))
    b.metric('Fuentes presentes',len({r['plataforma'] for r in rows}))
    c.metric('Autores identificados',len({(r['plataforma'],r['autor']) for r in rows if r['autor']}))
    metrics_rows=[r for r in rows if r.get('metricas_disponibles')]
    d.metric('Interacciones informadas',sum(r[k] for r in metrics_rows for k in ('likes','comentarios','compartidos')))
    st.caption(f'Interacciones: solo {len(metrics_rows)} registros con métricas disponibles. Sin métricas no significa cero interacciones. Cobertura NO exhaustiva.')
    bydate=Counter(r['fecha'][:10] for r in rows)
    if bydate: st.subheader('Publicaciones por día');st.bar_chart([{'fecha':k,'publicaciones':v} for k,v in sorted(bydate.items())],x='fecha',y='publicaciones')
    byplatform=Counter(r['plataforma'] for r in rows)
    if byplatform: st.subheader('Registros por plataforma'); st.bar_chart([{'plataforma':k,'registros':v} for k,v in byplatform.items()],x='plataforma',y='registros',horizontal=True)
    if not rows: st.warning('Todavía no hay registros para los filtros seleccionados. Usá «Actualizar fuentes» o importá un CSV.')
with words_tab:
    st.subheader('Palabras más frecuentes')
    st.caption('Conteos de términos presentes en los textos recuperados. No representa toda la conversación pública.')
    if terms: st.bar_chart([{'palabra':k,'veces':v} for k,v in terms.most_common(20)],x='palabra',y='veces',horizontal=True)
    else:st.write('Sin textos suficientes.')
    st.subheader('Tópicos detectados')
    st.caption('Un registro puede pertenecer a varias categorías; los valores no suman necesariamente 100 %.')
    if topics:st.bar_chart([{'topico':k,'registros':v} for k,v in topics.most_common()],x='topico',y='registros',horizontal=True)
    else:st.write('No se identificaron categorías del diccionario.')
    keyword=st.text_input('Rastrear palabra o frase específica', 'seguridad')
    if keyword.strip():
        matched=[r for r in rows if norm(keyword.strip()) in norm(r['texto'])]
        st.metric(f'Registros con «{keyword}»',len(matched))
        if matched:st.write('Ejemplos:');[(st.markdown(f'- [{r["texto"][:130]}]({r["url"]})')) for r in matched[:10]]
with posts_tab:
    st.subheader('Registros y evidencia')
    st.caption('La fecha, texto y métricas dependen de la fuente; las publicaciones importadas son responsabilidad de quien las carga.')
    for r in sorted(rows,key=lambda z:z['fecha'],reverse=True)[:200]:
        st.markdown(f'**{r["plataforma"]} · {r["fecha"][:16]} · {r["autor"]}**')
        st.write(r['texto'][:750])
        st.link_button('Abrir publicación',r['url'])
        if r.get('metricas_disponibles'):st.caption(f'♥ {r["likes"]} · Comentarios {r["comentarios"]} · Compartidos {r["compartidos"]}')
        st.divider()
    fields=['fecha','plataforma','autor','texto','url','likes','comentarios','compartidos']
    buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=fields);writer.writeheader()
    for r in rows:writer.writerow({k:r.get(k,'') if (k not in ('likes','comentarios','compartidos') or r.get('metricas_disponibles')) else '' for k in fields})
    st.download_button('⬇️ Exportar CSV / guardar historial',buffer.getvalue().encode('utf-8-sig'),'radar_exportacion.csv','text/csv')
with chat_tab:
    st.write('Consultas guiadas, no chat generativo de IA. Todas las respuestas salen del conjunto de datos visible.')
    q=st.selectbox('Elegí una pregunta',['¿Qué fuentes aportaron registros?','¿Qué palabras aparecen más?','¿Qué tópicos aparecen?','¿Qué días registraron más publicaciones?'])
    if q.startswith('¿Qué fuentes'):st.write(', '.join(f'{k}: {v}' for k,v in Counter(r['plataforma'] for r in rows).most_common()) or 'Sin registros.')
    elif 'palabras' in q:st.write(', '.join(f'{k} ({v})' for k,v in terms.most_common(12)) or 'Sin registros.')
    elif 'tópicos' in q:st.write(', '.join(f'{k} ({v})' for k,v in topics.most_common()) or 'Sin registros.')
    else:st.write(', '.join(f'{k} ({v})' for k,v in Counter(r['fecha'][:10] for r in rows).most_common(10)) or 'Sin registros.')
st.warning('Historial provisional: los registros de esta versión se guardan en la sesión del navegador. Exportá el CSV antes de cerrar y reimportalo cuando vuelvas. Para monitoreo continuo y alertas hace falta almacenamiento persistente y una tarea programada.')

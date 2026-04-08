import streamlit as st
from streamlit_gsheets import GSheetsConnection
from supabase import create_client, Client
import pandas as pd
import gspread
from datetime import datetime, date, timedelta
import os
import time
import re
import io

# Configuração da Página
st.set_page_config(page_title="Status - Gestão Integral por Item", layout="wide", page_icon="🏗️")

# ID DA PLANILHA DE TESTE (STAGING)
SHEET_ID = "1EXZg04wRlKRDUTo0dBTQTelABBhDDgQaGbaRF95s0lI"

# --- 1. CONEXÕES (HÍBRIDA: SHEETS + SUPABASE) ---
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except:
        return None

supabase = init_supabase()

# Conexão GSheets com o link da planilha já configurado internamente
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÃO DE AUTO-REFRESH (5 MINUTOS) ---
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

refresh_interval = 300 
if time.time() - st.session_state.last_refresh > refresh_interval:
    st.session_state.last_refresh = time.time()
    st.rerun()

# --- ESTILIZAÇÃO CSS (Mantida original) ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1, h2, h3 { color: #634D3E !important; }
    .stButton>button { background-color: #634D3E; color: white; border-radius: 5px; width: 100%; }
    .stInfo { background-color: #f0f2f6; border-left: 5px solid #B59572; }
    
    @keyframes pulse-red {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 0, 0, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(255, 0, 0, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 0, 0, 0); }
    }
    
    .alerta-pulsante {
        color: white; 
        background-color: #FF0000; 
        padding: 8px;
        border-radius: 5px; 
        font-weight: bold; 
        animation: pulse-red 2s infinite;
        text-align: center;
        display: block;
    }

    .no-prazo {
        color: white;
        background-color: #28a745;
        padding: 8px;
        border-radius: 5px;
        font-weight: bold;
        text-align: center;
        display: block;
    }

    .semaforo {
        height: 12px;
        width: 12px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 5px;
    }

    @keyframes rocket-launch {
        0% { transform: translateY(100vh) translateX(0px); opacity: 1; }
        50% { transform: translateY(50vh) translateX(20px); }
        100% { transform: translateY(-100vh) translateX(-20px); opacity: 0; }
    }
    .rocket-container {
        position: fixed; bottom: -100px; left: 50%; font-size: 50px;
        z-index: 9999; animation: rocket-launch 3s ease-in forwards;
    }
    </style>
    """, unsafe_allow_html=True)

def disparar_foguete():
    st.markdown('<div class="rocket-container">🚀</div>', unsafe_allow_html=True)

# --- FUNÇÃO DE AUXÍLIO PARA ORDENAÇÃO ---
def extrair_numero_item(texto):
    try:
        nums = re.findall(r'\d+', str(texto))
        return int(nums[0]) if nums else 9999
    except:
        return 9999

# --- SISTEMA DE LOGIN ---
def login():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔐 Acesso Restrito - Gestão de Gates")
        col_l, col_r = st.columns(2)
        with col_l:
            user = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            if st.button("Entrar"):
                if user == st.secrets["credentials"]["master_user"] and \
                   password == st.secrets["credentials"]["master_password"]:
                    st.session_state.authenticated = True
                    st.session_state.user_role = "MASTER"
                    st.session_state.user_display = "Administrador (Master)" 
                    st.session_state.papel_real = "Gerência Geral"
                    st.rerun()
                else:
                    try:
                        # LEITURA BLINDADA DE USUÁRIOS
                        url_users = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Usuarios"
                        df_users = pd.read_csv(url_users)
                        df_users['Usuario'] = df_users['Usuario'].astype(str).str.strip()
                        df_users['Senha'] = df_users['Senha'].astype(str).str.strip()
                        user_match = df_users[(df_users['Usuario'] == user) & (df_users['Senha'] == password)]
                        
                        if not user_match.empty:
                            st.session_state.authenticated = True
                            st.session_state.user_role = "USER"
                            nome_na_tabela = user_match['Nome'].iloc[0] if 'Nome' in user_match.columns else user
                            st.session_state.user_display = nome_na_tabela if pd.notnull(nome_na_tabela) else user
                            st.session_state.papel_real = user_match['Papel'].iloc[0]
                            st.rerun()
                        else:
                            st.error("Usuário ou senha inválidos")
                    except Exception as e:
                        st.error(f"Erro ao conectar com tabela de usuários: {e}")
        return False
    return True

if login():
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    @st.cache_data(ttl=10) # Reduzi para 10 segundos para ser mais rápido
    def load_pedidos():
        # 1. Lê a Planilha (Base original)
        sheet_id = "1EXZg04wRlKRDUTo0dBTQTelABBhDDgQaGbaRF95s0lI"
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=Pedidos"
        df = pd.read_csv(url)
        df = df.dropna(subset=['ID_Item'])
        df['ID_Item'] = df['ID_Item'].astype(str).str.strip()
        
        # 2. Lê o Supabase (A verdade atualizada)
        try:
            # BUSCAMOS TAMBÉM DONO E DATA_ENTREGA
            res = supabase.table("pedidos").select("id_item, status_atual, dono, data_entrega").execute()
            if res.data:
                df_supa = pd.DataFrame(res.data)
                df_supa['id_item'] = df_supa['id_item'].astype(str).str.strip()
                
                # Criamos mapas para cada informação que o Supabase deve "mandar"
                status_map = dict(zip(df_supa['id_item'], df_supa['status_atual']))
                dono_map = dict(zip(df_supa['id_item'], df_supa['dono']))
                data_map = dict(zip(df_supa['id_item'], df_supa['data_entrega']))
                
                # SUBSTITUIÇÃO COM PRIORIDADE AO SUPABASE
                df['Status_Atual'] = df['ID_Item'].map(status_map).fillna(df['Status_Atual'])
                df['Dono'] = df['ID_Item'].map(dono_map).fillna(df['Dono'])
                df['Data_Entrega'] = df['ID_Item'].map(data_map).fillna(df['Data_Entrega'])
                
        except Exception as e:
            st.warning(f"Nota: Usando dados da planilha (Alguns campos podem estar desatualizados: {e})")

        # 3. Limpeza e Ordenação
        df['sort_num'] = df['Item'].apply(extrair_numero_item)
        return df.drop_duplicates(subset=['ID_Item'], keep='first')
        
    @st.cache_data(ttl=60)
    def load_historico():
        try:
            df = conn.read(worksheet="Pedidos_Concluidos")
            return df
        except:
            return pd.DataFrame()

    df_global = load_pedidos()
    df_concluidos_global = load_historico()

    # --- FUNÇÕES DE SINCRONIZAÇÃO SUPABASE (PARALELO) ---
    def salvar_no_supabase(id_item, novo_status, row_dados=None):
        """Atualiza a tabela principal de pedidos no Supabase"""
        try:
            payload = {"id_item": str(id_item), "status_atual": str(novo_status)}
            if row_dados is not None:
                # --- TRATAMENTO DE NÚMEROS (VÍRGULA PARA PONTO) ---
                qtd_limpa = str(row_dados.get('Quantidade', 0)).replace(',', '.')
            try:
                qtd_final = float(qtd_limpa)
            except:
                qtd_final = 0.0

            payload.update({
                "ctr": str(row_dados['CTR']),
                "obra": str(row_dados.get('Obra', '')),
                "item_projeto": str(row_dados.get('Item', '')),
                "pedido": str(row_dados['Pedido']),
                "dono": str(row_dados['Dono']),
                "data_entrega": str(row_dados['Data_Entrega']) if pd.notnull(row_dados['Data_Entrega']) else None,
                "quantidade": qtd_final,
                "unidade": str(row_dados.get('Unidade', 'un'))
            })
            supabase.table("pedidos").upsert(payload).execute()
        except Exception as e: 
                st.warning(f"Erro sincronia Supabase (Pedidos): {e}")
        
    def log_auditoria_supabase(log_dict):
        """Registra alteração na tabela de auditoria do Supabase"""
        try:
            payload = {
                "data": str(log_dict.get('data', '')),
                "pedido": str(log_dict.get('pedido', '')),
                "usuario": str(log_dict.get('usuario', '')), 
                "o_que_mudou": str(log_dict.get('o_que_mudou', '')),
                "impacto_no_prazo": str(log_dict.get('impacto_no_prazo', 'Não')),
                "impacto_financeiro": str(log_dict.get('impacto_financeiro', 'Não')),
                "ctr": str(log_dict.get('ctr', '')),
                "dono": str(log_dict.get('dono', ''))
            }
            supabase.table("auditoria").insert(payload).execute()
        except Exception as e:
            st.error(f"Erro ao registrar Auditoria: {e}")
        
    def atualizar_status_lote(lista_ids, novo_status, df_referencia):
        """Atualiza o status apenas no Supabase, ignorando o Sheets"""
        try:
            # 1. GRAVAR DIRETO NO SUPABASE
            for id_item in lista_ids:
                try:
                    # Buscamos a linha do item para ter os dados completos
                    row = df_referencia[df_referencia['ID_Item'].astype(str) == str(id_item)].iloc[0]
                    # Chamamos a função de sincronia que já testamos e deu certo
                    salvar_no_supabase(id_item, novo_status, row)
                except Exception as e_item:
                    st.error(f"Erro no item {id_item}: {e_item}")
                    continue
            
            # 2. LIMPAR O CACHE E AVISAR O USUÁRIO
            st.cache_data.clear()
            st.success(f"Sucesso! Status atualizado para '{novo_status}' no Banco de Dados.")
            
        except Exception as e:
            st.error(f"Erro geral: {e}")
            
    # --- MENU LATERAL ---
    if os.path.exists("Status Apresentação.png"):
        st.sidebar.image("Status Apresentação.png", use_container_width=True)
    else: st.sidebar.title("STATUS MARCENARIA")

    st.sidebar.markdown(f"**👤 {st.session_state.user_display}**")
    papel_usuario = st.session_state.papel_real
    st.sidebar.info(f"Função: {papel_usuario}")
    
    if st.sidebar.button("Log Out"):
        st.session_state.authenticated = False
        st.rerun()

    st.sidebar.markdown("---")
    
    opcoes_menu = [
        "📉 Monitor por Pedido (CTR)", 
        "📊 Resumo e Prazos (Itens)", 
        "📈 Indicadores de Performance", 
        "🚨 Auditoria", 
        "📋 Central de Relatórios", # Novo Módulo
        "🛠️ Portão de Retrabalho",
        "💰 Gate 1: Material", 
        "✅ Gate 2: Aceite Técnico", 
        "🏭 Gate 3: Production", 
        "🚛 Gate 4: Entrega", 
        "⚠️ Alteração de Pedido",
        "📥 Importar Itens (Sistema)",
        "🛠️ Recuperação de Pedidos",
        "⚙️ SINCRONIZAÇÃO SUPABASE",
        "🏁 Concluir Pedidos (Baixa)"
    ]

    if papel_usuario == "Dono do Pedido (DP)":
        for item in ["🚨 Auditoria", "📈 Indicadores de Performance", "🛠️ Portão de Retrabalho", "🛠️ Recuperação de Pedidos", "⚙️ SINCRONIZAÇÃO SUPABASE", "🏁 Concluir Pedidos (Baixa)"]:
            if item in opcoes_menu: opcoes_menu.remove(item)
        
    menu = st.sidebar.radio("Navegação", opcoes_menu)

   # --- ABA: CONCLUÍDO (BAIXA DEFINITIVA) - VERSÃO BLINDADA ---
    if menu == "🏁 Concluir Pedidos (Baixa)":
        st.header("🏁 Baixa Definitiva de Pedidos")
        st.info("Pedidos concluídos saem da lista de ativos e vão para o histórico de entregas no Banco de Dados.")
        
        if papel_usuario not in ["Gerência Geral", "PCP"]:
            st.error("Acesso restrito ao PCP e Gerência.")
        else:
            # Filtramos quem já chegou no final do fluxo (Leitura via DF Global já sincronizado)
            df_concluir = df_global[df_global['Status_Atual'] == "CONCLUÍDO ✅"]
            
            if df_concluir.empty:
                st.warning("Não há itens marcados como 'CONCLUÍDO ✅' para dar baixa no sistema.")
            else:
                ctr_lista = [""] + sorted(df_concluir['CTR'].unique().tolist())
                ctr_sel = st.selectbox("Selecione a CTR para dar baixa:", ctr_lista)
                
                if ctr_sel:
                    itens_baixa = df_concluir[df_concluir['CTR'] == ctr_sel]
                    selecionados = st.multiselect("Selecione os itens para arquivar:", 
                                                  options=itens_baixa['ID_Item'].tolist(), 
                                                  format_func=lambda x: f"{itens_baixa[itens_baixa['ID_Item'] == x]['Pedido'].iloc[0]}",
                                                  default=itens_baixa['ID_Item'].tolist())
                    
                    if selecionados:
                        if st.button("🚀 DAR BAIXA E ARQUIVAR SELECIONADOS"):
                            try:
                                # 1. Atualiza Status no Supabase para ARQUIVADO (A única verdade agora)
                                for id_item in selecionados:
                                    supabase.table("pedidos").update({"status_atual": "ARQUIVADO"}).eq("id_item", id_item).execute()
                                    
                                    # Registro de Log para Auditoria
                                    row_baixa = itens_baixa[itens_baixa['ID_Item'] == id_item].iloc[0]
                                    log_baixa = {
                                        "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                        "Pedido": str(row_baixa['Pedido']),
                                        "Usuario": st.session_state.user_display,
                                        "Dono": str(row_baixa['Dono']),
                                        "O que mudou": "BAIXA DEFINITIVA: Item movido para o histórico arquivado.",
                                        "Impacto no Prazo": "Não", "Impacto Financeiro": "Não", "CTR": str(ctr_sel)
                                    }
                                    log_auditoria_supabase(log_baixa)

                                st.success(f"✅ {len(selecionados)} itens arquivados com sucesso no Supabase!")
                                st.cache_data.clear()
                                time.sleep(1.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao processar baixa definitiva: {e}")

   # --- FUNÇÃO DE CHECKLIST (GATES) - VERSÃO BLINDADA ---
    def checklist_gate(gate_id, aba, itens_checklist, responsavel_r, executor_e, msg_bloqueio, proximo_status, objetivo, momento, df_p):
        st.header(f"Ficha de Controle: {gate_id}")
        st.markdown(f"**Objetivo:** {objetivo} | **Momento:** {momento}")
        st.info(f"⚖️ **R:** {responsavel_r} | 🔨 **E:** {executor_e}")
        
        try:
            # Lógica de status requerida
            status_requerido = "Aguardando Materiais (G1)" if gate_id == "GATE 1 (MAT)" else \
                               "Aguardando Aceite Técnico (G2)" if gate_id == "GATE 2 (TEC)" else \
                               "Aguardando Produção (G3)" if gate_id == "GATE 3" else \
                               "Aguardando Entrega (G4)"

            ctrs_com_itens_pendentes = df_p[df_p['Status_Atual'] == status_requerido]['CTR'].unique().tolist()
            ctr_lista = [""] + sorted(ctrs_com_itens_pendentes)
            ctr_sel = st.selectbox(f"Selecione a CTR para {gate_id}", ctr_lista, key=f"ctr_gate_{aba}")
            
            if ctr_sel:
                itens_pendentes = df_p[(df_p['CTR'] == ctr_sel) & (df_p['Status_Atual'] == status_requerido)].sort_values(by='sort_num')
                if itens_pendentes.empty:
                    st.info(f"Não há mais itens pendentes.")
                    return

                selecionados = st.multiselect("Itens disponíveis para validação:", 
                                              options=itens_pendentes['ID_Item'].tolist(), 
                                              format_func=lambda x: f"{itens_pendentes[itens_pendentes['ID_Item'] == x]['Pedido'].iloc[0]}", 
                                              default=itens_pendentes['ID_Item'].tolist(), 
                                              key=f"multi_{aba}")
                
                if selecionados:
                    pode_assinar = (papel_usuario == responsavel_r or papel_usuario == executor_e or papel_usuario == "Gerência Geral")
                    if papel_usuario == "Consulta": pode_assinar = False

                    with st.form(f"form_batch_{aba}"):
                        respostas = {}
                        for secao, itens in itens_checklist.items():
                            st.markdown(f"#### 🔹 {secao}")
                            for item in itens: 
                                respostas[item] = st.checkbox(item, key=f"chk_{gate_id}_{aba}_{item.replace(' ', '_')}")
                        
                        obs = st.text_area("Observações Técnicas")
                        if st.form_submit_button("VALIDAR LOTE SELECIONADO 🚀", disabled=not pode_assinar):
                            if not all(respostas.values()): 
                                st.error(f"❌ BLOQUEIO: {msg_bloqueio}")
                            else:
                                # 1. Sincronia APENAS via Supabase (Evita o erro de Spreadsheet)
                                for id_item in selecionados:
                                    dono_item = itens_pendentes[itens_pendentes['ID_Item'] == id_item]['Dono'].iloc[0]
                                    item_nome = itens_pendentes[itens_pendentes['ID_Item'] == id_item]['Pedido'].iloc[0]
                                    
                                    log_entry = {
                                        "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                        "Pedido": item_nome, 
                                        "Usuario": st.session_state.user_display,
                                        "Dono": dono_item,
                                        "O que mudou": f"AVANÇO: {gate_id} para {proximo_status}. Obs: {obs}",
                                        "Impacto no Prazo": "Não", 
                                        "Impacto Financeiro": "Não", 
                                        "CTR": ctr_sel
                                    }
                                    
                                    # Grava Logs e Checklists no Supabase
                                    log_auditoria_supabase(log_entry)
                                    try:
                                        supabase.table("checklists_gates").insert({
                                            "gate": gate_id, "id_item": id_item, "validado_por": st.session_state.user_display,
                                            "obs": obs, "respostas": respostas
                                        }).execute()
                                    except: pass

                                # 2. Atualiza Status Principal no Supabase
                                atualizar_status_lote(selecionados, proximo_status, df_p)
                                
                                st.success(f"🚀 {len(selecionados)} itens validados no Banco de Dados!")
                                disparar_foguete()
                                time.sleep(1)
                                st.rerun()
        except Exception as e: 
            st.error(f"Erro na Ficha de Controle: {e}")

    # --- PÁGINAS DO MONITOR ---

    if menu == "📉 Monitor por Pedido (CTR)":
        st.header("📉 Monitor de Produção por CTR")
        try:
            df_p = df_global.copy()
            c_f1, c_f2 = st.columns(2)
            filtro_gestor = c_f1.multiselect("Filtrar por Gestor", sorted(df_p['Dono'].unique()))
            filtro_ctr = c_f2.multiselect("Filtrar por CTR", sorted(df_p['CTR'].unique()))
            if filtro_gestor: df_p = df_p[df_p['Dono'].isin(filtro_gestor)]
            if filtro_ctr: df_p = df_p[df_p['CTR'].isin(filtro_ctr)]
            df_p['Data_Entrega_DT'] = pd.to_datetime(df_p['Data_Entrega'], errors='coerce')
            ctrs = df_p.groupby('CTR').agg({'ID_Item': 'count', 'Data_Entrega_DT': 'min', 'Dono': 'first'}).reset_index()
            
            for _, row in ctrs.sort_values(by='Data_Entrega_DT').iterrows():
                ctr_sel = row['CTR']
                itens_obra = df_p[df_p['CTR'] == ctr_sel].sort_values(by='sort_num').copy()
                total_itens = len(itens_obra)
                dias = (row['Data_Entrega_DT'].date() - date.today()).days if pd.notnull(row['Data_Entrega_DT']) else None
                with st.container():
                    c1, c2, c3 = st.columns([4, 3, 3])
                    c1.markdown(f"### {ctr_sel}")
                    c1.write(f"📅 Entrega Crítica: {row['Data_Entrega_DT'].strftime('%d/%m/%Y') if pd.notnull(row['Data_Entrega_DT']) else 'S/D'}")
                    c2.markdown(f"👤 **Gestor:** {row['Dono']}")
                    with c2.popover(f"🔍 Detalhar Itens ({total_itens})", use_container_width=True):
                        for _, item in itens_obra.iterrows():
                            i_dt = pd.to_datetime(item['Data_Entrega'], errors='coerce')
                            i_dias = (i_dt.date() - date.today()).days if pd.notnull(i_dt) else None
                            cor = "#28a745" if i_dias is not None and i_dias > 3 else "#FF0000" if i_dias is not None else "grey"
                            circulo = f'<span class="semaforo" style="background-color: {cor};"></span>'
                            st.markdown(f"{circulo} **{item['Pedido']}** | 📍 {item['Status_Atual']} | 📅 {i_dt.strftime('%d/%m') if pd.notnull(i_dt) else 'S/D'}", unsafe_allow_html=True)
                            
                            if item['Status_Atual'] != "⚠️ Em Retrabalho":
                                with st.expander("🚨 Sinalizar Retrabalho"):
                                    motivo_ret = st.text_input("Motivo do Retrabalho", key=f"ret_{item['ID_Item']}")
                                    if st.button("CONFIRMAR RETRABALHO", key=f"btn_ret_{item['ID_Item']}"):
                                        if not motivo_ret: st.warning("Descreva o motivo.")
                                        else:
                                            atualizar_status_lote([item['ID_Item']], "⚠️ Em Retrabalho", df_p)
                                            log_r = {
                                                "Data": datetime.now().strftime("%d/%m/%Y %H:%M"), 
                                                "Pedido": item['Pedido'], 
                                                "Usuario": st.session_state.user_display, 
                                                "Dono": item['Dono'],
                                                "O que mudou": f"ENTRADA RETRABALHO: {motivo_ret}", 
                                                "Impacto no Prazo": "Sim", 
                                                "Impacto Financeiro": "Sim", 
                                                "CTR": ctr_sel
                                            }
                                            df_alt = conn.read(worksheet="Alteracoes", ttl=0)
                                            conn.update(worksheet="Alteracoes", data=pd.concat([df_alt, pd.DataFrame([log_r])], ignore_index=True))
                                            log_auditoria_supabase(log_r)
                                            
                                            try:
                                                df_hist_ret = conn.read(worksheet="Historico_Retrabalho", ttl=0)
                                                log_h = {"Data": log_r['Data'], "ID_Item": item['ID_Item'], "Pedido": item['Pedido'], "Dono": item['Dono'], "CTR": ctr_sel, "Motivo_Entrada": motivo_ret}
                                                conn.update(worksheet="Historico_Retrabalho", data=pd.concat([df_hist_ret, pd.DataFrame([log_h])], ignore_index=True))
                                            except: pass
                                            st.success("Item movido para retrabalho!"); time.sleep(1); st.rerun()

                    if dias is None: status_html = '<span style="color: grey;">⚪ SEM DATA</span>'
                    elif dias < 0: status_html = f'<div class="alerta-pulsante">❌ ATRASO CRÍTICO</div>'
                    elif dias <= 3: status_html = f'<div class="alerta-pulsante">🔴 URGENTE</div>'
                    else: status_html = '<div class="no-prazo">🟢 NO PRAZO</div>'
                    c3.markdown(status_html, unsafe_allow_html=True)
                    st.markdown("---")

            if not df_concluidos_global.empty:
                st.markdown("### 🏁 Histórico de Pedidos Concluídos")
                with st.expander("Ver itens arquivados desta consulta"):
                    df_c_filtro = df_concluidos_global.copy()
                    if filtro_ctr: df_c_filtro = df_c_filtro[df_c_filtro['CTR'].isin(filtro_ctr)]
                    if filtro_gestor: df_c_filtro = df_c_filtro[df_c_filtro['Dono'].isin(filtro_gestor)]
                    if df_c_filtro.empty: st.info("Nenhum item concluído para os filtros.")
                    else: st.dataframe(df_c_filtro[['CTR', 'Pedido', 'Dono', 'Data_Finalizacao', 'Performance']], use_container_width=True)

        except Exception as e: st.error(f"Erro no monitor: {e}")

    elif menu == "📊 Resumo e Prazos (Itens)":
        st.header("🚦 Monitor de Produção (Itens)")
        try:
            df_p = df_global.copy().sort_values(by=['Data_Entrega', 'sort_num'])
            c_f1, c_f2 = st.columns(2)
            filtro_gestor = c_f1.multiselect("Filtrar por Gestor", sorted(df_p['Dono'].unique()), key="f_gest_itens")
            filtro_ctr = c_f2.multiselect("Filtrar por CTR", sorted(df_p['CTR'].unique()), key="f_ctr_itens")
            if filtro_gestor: df_p = df_p[df_p['Dono'].isin(filtro_gestor)]
            if filtro_ctr: df_p = df_p[df_p['CTR'].isin(filtro_ctr)]
            df_p['Data_Entrega'] = pd.to_datetime(df_p['Data_Entrega'], errors='coerce')
            for idx, row in df_p.iterrows():
                dias = (row['Data_Entrega'].date() - date.today()).days if pd.notnull(row['Data_Entrega']) else None
                status_html = ""
                if dias is None: status_html = '<span style="color: grey;">⚪ SEM DATA</span>'
                elif dias < 0: status_html = f'<div class="alerta-pulsante">❌ ATRASO ({abs(dias)}d)</div>'
                elif dias <= 3: status_html = f'<div class="alerta-pulsante">🔴 URGENTE ({dias}d)</div>'
                else: status_html = '<div class="no-prazo">🟢 NO PRAZO</div>'
                c1, c2, c3, c4 = st.columns([2, 4, 2, 2])
                with c1: st.write(f"**{row['CTR']}**")
                with c2: st.write(f"**{row['Pedido']}**\n👤 {row['Dono']}")
                with c3: st.write(f"📍 {row['Status_Atual']}\n📅 {row['Data_Entrega'].strftime('%d/%m/%Y') if pd.notnull(row['Data_Entrega']) else 'S/D'}")
                with c4: st.markdown(status_html, unsafe_allow_html=True)
                st.markdown("---")

            if not df_concluidos_global.empty:
                st.markdown("### 🏁 Itens Arquivados")
                with st.expander("Clique para expandir o histórico de baixas"):
                    df_c_filtro = df_concluidos_global.copy()
                    if filtro_ctr: df_c_filtro = df_c_filtro[df_c_filtro['CTR'].isin(filtro_ctr)]
                    if filtro_gestor: df_c_filtro = df_c_filtro[df_c_filtro['Dono'].isin(filtro_gestor)]
                    st.dataframe(df_c_filtro[['CTR', 'Pedido', 'Data_Entrega', 'Data_Finalizacao', 'Performance']], use_container_width=True)

        except Exception as e: st.error(f"Erro no monitor: {e}")

    elif menu == "🛠️ Portão de Retrabalho":
        st.header("🛠️ Gestão de Retrabalho")
        
        # --- RESGATE DE ITENS (CORRIGIDO: BUSCA NO BANCO) ---
        with st.expander("⏪ Resgatar Item Concluído para Retrabalho"):
            # Buscamos no DF_GLOBAL (que já tem os dados do Supabase) 
            # apenas quem já terminou o fluxo mas ainda não sumiu do sistema
            df_concluidos_real = df_global[df_global['Status_Atual'].isin(["CONCLUÍDO ✅", "ARQUIVADO"])]
            
            if df_concluidos_real.empty:
                st.info("Não há itens concluídos ou arquivados no banco de dados para resgate.")
            else:
                ctr_resgate = st.selectbox("Selecione a CTR do item concluído:", [""] + sorted(df_concluidos_real['CTR'].unique().tolist()))
                if ctr_resgate:
                    itens_para_resgatar = df_concluidos_real[df_concluidos_real['CTR'] == ctr_resgate]
                    item_sel = st.selectbox("Qual item deseja retornar para Retrabalho?", 
                                           options=itens_para_resgatar['ID_Item'].tolist(),
                                           format_func=lambda x: f"{itens_para_resgatar[itens_para_resgatar['ID_Item'] == x]['Pedido'].iloc[0]}")
                    
                    motivo_r = st.text_input("Motivo da reabertura:", key="resgate_motivo")
                    
                    if st.button("🚨 REABRIR E ENVIAR PARA RETRABALHO"):
                        if not motivo_r:
                            st.warning("Descreva o motivo.")
                        else:
                            try:
                                # Faz o item "voltar no tempo" no Supabase
                                row_info = itens_para_resgatar[itens_para_resgatar['ID_Item'] == item_sel].iloc[0]
                                salvar_no_supabase(item_sel, "Aguardando Produção (G3)", row_info)
                                
                                # Log da "vontolta"
                                log_auditoria_supabase({
                                    "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                    "Pedido": str(row_info['Pedido']),
                                    "Usuario": st.session_state.user_display,
                                    "Dono": str(row_info['Dono']),
                                    "O que mudou": f"REABERTURA DE ITEM CONCLUÍDO: {motivo_r}",
                                    "Impacto no Prazo": "Sim", "Impacto Financeiro": "Sim", "CTR": str(ctr_resgate)
                                })
                                
                                st.success("Item reaberto! Ele agora aparecerá na lista de Retrabalho abaixo.")
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao reabrir: {e}")

        st.divider()
        
        # --- 2. GESTÃO DE QUEM JÁ ESTÁ EM RETRABALHO ---
        try:
            # Filtro seguro para evitar erro caso a coluna não exista
            if 'Status_Atual' in df_global.columns:
                df_ret = df_global[df_global['Status_Atual'] == "⚠️ Em Retrabalho"]
            else:
                df_ret = pd.DataFrame()
            
            if df_ret.empty:
                st.success("✅ Nenhum item em retrabalho no momento.")
            else:
                ctrs_ret = [""] + sorted(df_ret['CTR'].unique().tolist())
                ctr_sel = st.selectbox("Selecione a CTR com retrabalho em andamento:", ctrs_ret)
                
                if ctr_sel:
                    itens_pend = df_ret[df_ret['CTR'] == ctr_sel]
                    selecionados = st.multiselect("Itens para validar:", 
                                                  options=itens_pend['ID_Item'].tolist(), 
                                                  format_func=lambda x: f"{itens_pend[itens_pend['ID_Item'] == x]['Pedido'].iloc[0]}")
                    
                    if selecionados:
                        with st.form("form_retrabalho"):
                            st.markdown("#### ✅ Checklist de Qualidade")
                            c1 = st.checkbox("Peça Danificada Identificada")
                            c2 = st.checkbox("Material Solicitado")
                            c3 = st.checkbox("Prioridade Produção Confirmada")
                            obs_ret = st.text_area("Observações do Reparo")
                            proximo_gate = st.selectbox("Retornar para qual portão?", ["Aguardando Produção (G3)", "Aguardando Entrega (G4)"])
                            
                            if st.form_submit_button("CONCLUIR RETRABALHO 🛠️"):
                                if not all([c1, c2, c3]):
                                    st.error("Marque todos os itens.")
                                else:
                                    # Gravação com proteção total
                                    try:
                                        for i in selecionados:
                                            supabase.table("checklists_gates").insert({
                                                "gate": "RETRABALHO", 
                                                "id_item": str(i), 
                                                "validado_por": st.session_state.user_display, 
                                                "obs": obs_ret,
                                                "respostas": {"Dano_Identificado": c1, "Material_Solicitado": c2, "Prioridade_PCP": c3}
                                            }).execute()
                                    except:
                                        st.warning("Nota: Checklist salvo apenas no fluxo (tabela checklists_gates não encontrada).")
                                    
                                    atualizar_status_lote(selecionados, proximo_gate, df_ret)
                                    st.success("Sucesso!")
                                    time.sleep(1)
                                    st.rerun()
        except Exception as e:
            st.error(f"Erro na interface de retrabalho: {e}")
            
    # --- ABA: CENTRAL DE RELATÓRIOS (NOVO) ---
    elif menu == "📋 Central de Relatórios":
        st.header("📋 Emissão de Relatórios por CTR")
        
        ctrs_disponiveis = sorted(df_global['CTR'].unique().tolist())
        ctr_rel = st.selectbox("Selecione a CTR para gerar o relatório:", [""] + ctrs_disponiveis)
        
        if ctr_rel:
            tipo_rel = st.radio("Selecione o Tipo de Relatório:", 
                                ["Dossiê Técnico (Fábrica)", "Relatório de Impedimentos (Gestão)", "Certificado de Qualidade (Cliente)"])
            
            # Coleta de Observações em todas as abas de Checklist
            abas_checklist = ["Checklist_G1", "Checklist_G2", "Checklist_G3", "Checklist_G4", "Checklist_Retrabalho"]
            todas_obs = []
            
            with st.spinner("Compilando dados..."):
                for aba in abas_checklist:
                    try:
                        df_tmp = conn.read(worksheet=aba, ttl="1m")
                        # Filtra apenas itens que pertencem à CTR selecionada
                        itens_da_ctr = df_global[df_global['CTR'] == ctr_rel]['ID_Item'].tolist()
                        df_tmp = df_tmp[df_tmp['ID_Item'].isin(itens_da_ctr)]
                        
                        if not df_tmp.empty:
                            df_tmp['Gate'] = aba.replace("Checklist_", "")
                            todas_obs.append(df_tmp[['Data', 'ID_Item', 'Validado_Por', 'Obs', 'Gate']])
                    except: continue
                
            if not todas_obs:
                st.warning("Nenhuma observação registrada para esta CTR ainda.")
            else:
                df_final_rel = pd.concat(todas_obs, ignore_index=True)
                # Cruzamento com Pedidos para pegar o nome amigável do item
                df_final_rel = df_final_rel.merge(df_global[['ID_Item', 'Pedido']], on='ID_Item', how='left')
                df_final_rel = df_final_rel.sort_values(by='Data', ascending=False)
                
                # Aplicação de filtros baseados no tipo de relatório
                if tipo_rel == "Relatório de Impedimentos (Gestão)":
                    df_final_rel = df_final_rel[df_final_rel['Obs'].str.contains('BLOQUEADO|PARADO|ERRO|FALTA|PROBLEMA', case=False, na=False)]
                elif tipo_rel == "Certificado de Qualidade (Cliente)":
                    df_final_rel = df_final_rel[df_final_rel['Gate'].isin(['G4', 'G3'])]

                st.subheader(f"📄 {tipo_rel}")
                st.info(f"CTR: {ctr_rel} | Total de Registros: {len(df_final_rel)}")
                
                # Exibição Scannable
                for _, r in df_final_rel.iterrows():
                    with st.expander(f"📅 {r['Data']} - {r['Pedido']} ({r['Gate']})"):
                        st.write(f"**Responsável:** {r['Validado_Por']}")
                        st.write(f"**Nota:** {r['Obs'] if r['Obs'] else 'Sem comentário adicional.'}")

                # Opção de Exportação Excel para Impressão
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final_rel[['Data', 'Gate', 'Pedido', 'Validado_Por', 'Obs']].to_excel(writer, index=False, sheet_name='Relatorio')
                    workbook = writer.book
                    worksheet = writer.sheets['Relatorio']
                    header_format = workbook.add_format({'bold': True, 'bg_color': '#634D3E', 'font_color': 'white'})
                    for col_num, value in enumerate(df_final_rel[['Data', 'Gate', 'Pedido', 'Validado_Por', 'Obs']].columns.values):
                        worksheet.write(0, col_num, value, header_format)
                
                st.download_button(
                    label="📥 Gerar Arquivo para Impressão (Excel)",
                    data=output.getvalue(),
                    file_name=f"Relatorio_{tipo_rel}_{ctr_rel}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    elif menu == "💰 Gate 1: Material":
        itens = {"Materiais": ["Lista validada", "Quantidades conferidas", "Materiais especiais"], "Compras": ["Fornecedores definidos", "Lead times confirmados", "Datas registradas"], "Financeiro": ["Impacto caixa validado", "Compra autorizada", "Forma de pagamento"]}
        checklist_gate("GATE 1 (MAT)", "Checklist_G2", itens, "Financeiro", "Compras", "Falta material ➡️ PARADO", "Aguardando Aceite Técnico (G2)", "Fábrica sem parada", "Na montagem", df_global)

    elif menu == "✅ Gate 2: Aceite Técnico":
        itens = {"Informações Comerciais": ["Pedido registrado", "Cliente identificado", "Tipo de obra definido", "Responsável identificado"], "Escopo Técnico": ["Projeto mínimo recebido", "Ambientes definidos", "Materiais principais", "Itens fora do padrão"], "Prazo (prévia)": ["Prazo solicitado registrado", "Prazo avaliado", "Risco de prazo"], "Governança": ["Dono do Pedido definido", "PCP validou viabilidade", "Aprovado formalmente"]}
        checklist_gate("GATE 2 (TEC)", "Checklist_G1", itens, "Dono do Pedido (DP)", "PCP", "Projeto incompleto ➡️ BLOQUEADO", "Aguardando Produção (G3)", "Impedir entrada mal definida", "Antes do plano", df_global)

    elif menu == "🏭 Gate 3: Production":
        itens = {"Planejamento": ["Sequenciado", "Capacidade validada", "Gargalo identificado", "Gargalo protegido"], "Projeto": ["Projeto técnico liberado", "Medidas conferidas", "Versão registrada"], "Comunicação": ["Produção ciente", "Prazo interno registrado", "Alterações registradas"]}
        checklist_gate("GATE 3", "Checklist_G3", itens, "PCP", "Produção", "Sem plano ➡️ BLOQUEADO", "Aguardando Entrega (G4)", "Produzir planejado", "No corte", df_global)

    elif menu == "🚛 Gate 4: Entrega":
        itens = {"Produto": ["Produção concluída", "Qualidade conferida", "Separados por pedido"], "Logística": ["Checklist carga", "Frota definida", "Rota planejada"], "Prazo": ["Data validada", "Cliente informado", "Equipe montagem alinhada"]}
        checklist_gate("GATE 4", "Checklist_G4", itens, "Dono do Pedido (DP)", "Logística", "Erro acabamento ➡️ NÃO carrega", "CONCLUÍDO ✅", "Entrega perfeita", "Na carga", df_global)

    elif menu == "📈 Indicadores de Performance":
        st.header("📈 Dashboard de Indicadores")
        try:
            df_p = df_global.copy()
            df_h = df_concluidos_global.copy()
            c_p1, c_p2, c_p3 = st.columns([2, 2, 4])
            data_ini = c_p1.date_input("Início", value=date.today() - timedelta(days=30))
            data_fim = c_p2.date_input("Fim", value=date.today())
            todos_gestores = sorted(list(set(df_p['Dono'].unique()) | set(df_h['Dono'].unique() if not df_h.empty else [])))
            gestor_sel = c_p3.multiselect("🔍 Filtrar por Dono do Pedido", todos_gestores, key="filtro_bi_gestor")
            
            try:
                df_hist_r = conn.read(worksheet="Historico_Retrabalho", ttl=10)
                df_hist_r['dt_obj'] = pd.to_datetime(df_hist_r['Data'], dayfirst=True).dt.date
                df_hist_r = df_hist_r[(df_hist_r['dt_obj'] >= data_ini) & (df_hist_r['dt_obj'] <= data_fim)]
                if gestor_sel: df_hist_r = df_hist_r[df_hist_r['Dono'].isin(gestor_sel)]
                total_ret = len(df_hist_r)
            except: total_ret = 0

            if gestor_sel:
                df_p = df_p[df_p['Dono'].isin(gestor_sel)]
                if not df_h.empty: df_h = df_h[df_h['Dono'].isin(gestor_sel)]

            st.subheader("🚧 Fluxo de Itens por Portão")
            gates_count = df_p['Status_Atual'].value_counts()
            c_g1, c_g2, c_g3, c_g4, c_r = st.columns(5)
            c_g1.metric("Materiais (G1)", gates_count.get("Aguardando Materiais (G1)", 0))
            c_g2.metric("Aceite Técnico (G2)", gates_count.get("Aguardando Aceite Técnico (G2)", 0))
            c_g3.metric("Produção (G3)", gates_count.get("Aguardando Produção (G3)", 0))
            c_g4.metric("Entrega (G4)", gates_count.get("Aguardando Entrega (G4)", 0))
            c_r.metric("⚠️ Retrabalhos (No Período)", total_ret)

            st.markdown("---")
            st.subheader("📊 Performance de Entregas (Arquivados)")
            if df_h.empty: st.info("Sem dados históricos para este filtro.")
            else:
                perf_counts = df_h['Performance'].value_counts()
                c_graf1, c_graf2 = st.columns(2)
                with c_graf1: 
                    st.write("**Eficiência de Prazo**")
                    st.bar_chart(perf_counts)
                with c_graf2:
                    taxa = (perf_counts.get("NO PRAZO", 0) / len(df_h) * 100) if len(df_h) > 0 else 0
                    st.metric("Taxa de Eficiência", f"{taxa:.1f}%")
                    st.write(f"Total: {len(df_h)} | ✅ No Prazo: {perf_counts.get('NO PRAZO', 0)} | ❌ Atraso: {perf_counts.get('ATRASADO', 0)}")
        except Exception as e: st.error(f"Erro nos indicadores: {e}")

    elif menu == "🚨 Auditoria":
        st.header("🚨 Auditoria de Alterações (Supabase)")
        st.info("Histórico em tempo real de todas as movimentações registradas no banco de dados.")

        try:
            # 1. Busca os logs (Ordenação feita via Pandas para evitar erro de versão da biblioteca)
            res = supabase.table("auditoria").select("*").execute()
            
            if not res.data:
                st.warning("Nenhum registro de auditoria encontrado no Banco de Dados.")
            else:
                df_auditoria = pd.DataFrame(res.data)
                
                # Ordenação manual pelo ID para garantir que o mais novo apareça no topo
                if 'id' in df_auditoria.columns:
                    df_auditoria = df_auditoria.sort_values(by='id', ascending=False)

                # 2. Filtros
                col1, col2, col3 = st.columns(3)
                
                usuarios = ["Todos"] + sorted(df_auditoria['usuario'].unique().tolist()) if 'usuario' in df_auditoria.columns else ["Todos"]
                user_sel = col1.selectbox("Filtrar por Usuário:", usuarios)
                
                ctrs = ["Todas"] + sorted(df_auditoria['ctr'].unique().astype(str).tolist()) if 'ctr' in df_auditoria.columns else ["Todas"]
                ctr_sel = col2.selectbox("Filtrar por CTR:", ctrs)
                
                busca = col3.text_input("Buscar no log (Pedido, Motivo...):")

                # Aplicando os filtros
                df_filtered = df_auditoria.copy()
                if user_sel != "Todos":
                    df_filtered = df_filtered[df_filtered['usuario'] == user_sel]
                if ctr_sel != "Todas":
                    df_filtered = df_filtered[df_filtered['ctr'] == ctr_sel]
                if busca:
                    df_filtered = df_filtered[df_filtered.astype(str).apply(lambda x: x.str.contains(busca, case=False)).any(axis=1)]

                # 3. Exibição
                cols_view = [c for c in ['data', 'usuario', 'ctr', 'pedido', 'o_que_mudou'] if c in df_filtered.columns]
                st.dataframe(df_filtered[cols_view], use_container_width=True, hide_index=True)
                
                if st.button("🔄 Atualizar Auditoria"):
                    st.rerun()
        except Exception as e:
            st.error(f"Erro ao carregar auditoria: {e}")

    elif menu == "⚠️ Alteração de Pedido":
        st.header("🔄 Alteração de Pedido em Lote (Supabase)")
        if papel_usuario not in ["Gerência Geral", "PCP"]: 
            st.error("Acesso negado.")
        else:
            try:
                df_p = df_global.copy()
                df_p['Data_Entrega_Str'] = pd.to_datetime(df_p['Data_Entrega'], errors='coerce').dt.strftime('%Y-%m-%d').fillna('')
                ctr_lista = [""] + sorted(df_p['CTR'].unique().tolist())
                ctr_sel = st.selectbox("Selecione a CTR", ctr_lista, key="ctr_alt_lote_final")
                
                if ctr_sel:
                    itens_ctr = df_p[df_p['CTR'] == ctr_sel]
                    selecionados = st.multiselect("Itens para alterar:", options=itens_ctr['ID_Item'].tolist(), 
                                                  format_func=lambda x: f"{itens_ctr[itens_ctr['ID_Item'] == x]['Pedido'].iloc[0]}")
                    
                    if selecionados:
                        with st.form("form_lote_completo", clear_on_submit=True):
                            c1, c2 = st.columns(2)
                            gestor_at = itens_ctr[itens_ctr['ID_Item'] == selecionados[0]]['Dono'].iloc[0]
                            novo_gestor = c1.text_input("Novo Gestor", value=gestor_at)
                            nova_data = c2.date_input("Nova Data de Entrega")
                            
                            st.markdown("---")
                            col_imp1, col_imp2 = st.columns(2)
                            imp_prazo = col_imp1.radio("Impacto no Prazo?", ["Não", "Sim"], horizontal=True)
                            imp_finan = col_imp2.radio("Impacto Financeiro?", ["Não", "Sim"], horizontal=True)
                            
                            motivo = st.text_area("Motivo Detalhado da Alteração")
                            
                            btn_lote = st.form_submit_button("APLICAR ALTERAÇÕES 🚀")
                            
                            if btn_lote:
                                if not motivo:
                                    st.error("❌ O motivo é obrigatório para auditoria!")
                                else:
                                    progresso = st.progress(0)
                                    for i, id_item in enumerate(selecionados):
                                        # 1. Update no Banco (Pedidos)
                                        supabase.table("pedidos").update({
                                            "dono": novo_gestor, 
                                            "data_entrega": str(nova_data)
                                        }).eq("id_item", id_item).execute()
                                        
                                        # 2. Envio do Log Completo
                                        item_info = itens_ctr[itens_ctr['ID_Item'] == id_item].iloc[0]
                                        log_entry = {
                                            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                            "pedido": str(item_info['Pedido']),
                                            "usuario": st.session_state.user_display,
                                            "o_que_mudou": f"LOTE: Data {nova_data}. Motivo: {motivo}",
                                            "impacto_no_prazo": imp_prazo,
                                            "impacto_financeiro": imp_finan,
                                            "ctr": str(ctr_sel),
                                            "dono": str(novo_gestor)
                                        }
                                        log_auditoria_supabase(log_entry)
                                        progresso.progress((i + 1) / len(selecionados))
                                    
                                    st.success(f"✅ Sucesso! {len(selecionados)} itens atualizados.")
                                    st.cache_data.clear()
                                    time.sleep(2) # Pausa para você ver a mensagem antes do reset
                                    st.rerun()
            except Exception as e:
                st.error(f"Erro crítico: {e}")
                
    elif menu == "📥 Importar Itens (Sistema)":
        st.header("📥 Importar Itens da Marcenaria")
        if papel_usuario not in ["Gerência Geral", "PCP"]: st.error("Acesso negado.")
        else:
            up = st.file_uploader("Arquivo egsDataGrid", type=["csv", "xlsx"])
            if up:
                try:
                    df_up = pd.read_csv(up) if up.name.endswith('csv') else pd.read_excel(up)
                    if st.button("Confirmar Importação"):
                        df_base = conn.read(worksheet="Pedidos", ttl=0)
                        novos = []
                        for _, r in df_up.iterrows():
                            uid = f"{r['Centro de custo']}-{r['Id Programação']}"
                            dt_crua = pd.to_datetime(r['Data Entrega'], errors='coerce')
                            dt_limpa = dt_crua.strftime('%Y-%m-%d') if pd.notnull(dt_crua) else ""
                            if str(uid) not in df_base['ID_Item'].astype(str).values:
                                payload_novo = {"ID_Item": uid, "CTR": r['Centro de custo'], "Obra": r['Obra'], "Item": r['Item'], "Pedido": r['Produto'], "Dono": r['Gestor'], "Status_Atual": "Aguardando Materiais (G1)", "Data_Entrega": dt_limpa, "Quantidade": r['Quantidade'], "Unidade": r['Unidade']}
                                novos.append(payload_novo)
                        if novos: 
                            final_df = pd.concat([df_base, pd.DataFrame(novos)], ignore_index=True)
                            final_df = final_df.drop_duplicates(subset=['ID_Item'], keep='first')
                            conn.update(worksheet="Pedidos", data=final_df)
                            for n in novos:
                                salvar_no_supabase(n['ID_Item'], "Aguardando Materiais (G1)", n)
                            st.success(f"✅ {len(novos)} novos itens importados!")
                        else: st.warning("⚠️ Nenhum item novo encontrado.")
                        st.cache_data.clear()
                except Exception as e: st.error(f"Erro na importação: {e}")

    elif menu == "⚙️ SINCRONIZAÇÃO SUPABASE":
        st.header("⚙️ Sincronização em Massa")
        c1, c2, c3 = st.columns(3)
        
        with c1:
            st.subheader("1. Ativos")
            if st.button("🚀 SINCRONIZAR ATIVOS"):
                with st.spinner("Sincronizando ativos..."):
                    for idx, row in df_global.iterrows():
                        salvar_no_supabase(row['ID_Item'], row['Status_Atual'], row)
                st.success("Pedidos ativos sincronizados!")

        with c2:
            st.subheader("2. Histórico")
            if st.button("🏁 SINCRONIZAR HISTÓRICO"):
                with st.spinner("Migrando baixas..."):
                    sheet_id = "1EXZg04wRlKRDUTo0dBTQTelABBhDDgQaGbaRF95s0lI"
                    url_sync = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=Pedidos_Concluidos"
                    df_hist_full = pd.read_csv(url_sync)
                    prog = st.progress(0)
                    for i, row in df_hist_full.iterrows():
                        salvar_no_supabase(row['ID_Item'], "ARQUIVADO", row)
                        prog.progress((i + 1) / len(df_hist_full))
                st.success("Histórico sincronizado na tabela 'pedidos'!")

        with c3:
            st.subheader("3. Alterações (2.500+)")
            if st.button("🚨 SINCRONIZAR LOGS"):
                with st.spinner("Migrando auditoria..."):
                    sheet_id = "1EXZg04wRlKRDUTo0dBTQTelABBhDDgQaGbaRF95s0lI"
                    url_logs = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=Alteracoes"
                    df_aud_full = pd.read_csv(url_logs)
                    prog_a = st.progress(0)
                    lote = []
                    for i, row in df_aud_full.iterrows():
                        lote.append({
                            "Data": str(row['Data']), 
                            "Pedido": str(row['Pedido']),
                            "Usuario": str(row['Usuario']), 
                            "O que mudou": str(row['O que mudou']),
                            "Impacto no Prazo": str(row['Impacto no Prazo']),
                            "Impacto Financeiro": str(row['Impacto Financeiro']),
                            "CTR": str(row['CTR']), 
                            "Dono": str(row.get('Dono', ''))
                        })
                        if len(lote) >= 50:
                            supabase.table("alteracoes").insert(lote).execute()
                            lote = []
                        prog_a.progress((i + 1) / len(df_aud_full))
                    if lote: supabase.table("alteracoes").insert(lote).execute()
                st.success("Alterações migradas para o Supabase!")

    elif menu == "🛠️ Recuperação de Pedidos":
        st.header("🛠️ Recuperação e Limpeza de Dados")
        if st.button("⚠️ EXECUTAR LIMPEZA DE DUPLICADOS NA PLANILHA ⚠️"):
            df_clean = conn.read(worksheet="Pedidos", ttl=0)
            df_clean = df_clean.drop_duplicates(subset=['ID_Item'], keep='first')
            conn.update(worksheet="Pedidos", data=df_clean)
            st.success("Limpeza concluída!")
            st.cache_data.clear(); st.rerun()

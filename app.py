import os
import re
import time
import io
from datetime import datetime, date, timedelta

import pandas as pd
import streamlit as st
from supabase import create_client
from streamlit_gsheets import GSheetsConnection


# =========================================================
# CONFIGURAÇÃO INICIAL
# =========================================================
st.set_page_config(
    page_title="Status - Gestão Integral por Item",
    layout="wide",
    page_icon="🏗️",
)

SHEET_ID = "1EXZg04wRlKRDUTo0dBTQTelABBhDDgQaGbaRF95s0lI"


# =========================================================
# CONEXÕES
# =========================================================
@st.cache_resource
def init_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


supabase = init_supabase()

# Mantido temporariamente apenas para:
# - login por aba Usuarios no Sheets
# - histórico antigo Pedidos_Concluidos
# - alguns relatórios legados
conn = st.connection("gsheets", type=GSheetsConnection)


# =========================================================
# AUTO REFRESH
# =========================================================
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

refresh_interval = 300
if time.time() - st.session_state.last_refresh > refresh_interval:
    st.session_state.last_refresh = time.time()
    st.rerun()


# =========================================================
# CSS
# =========================================================
st.markdown(
    """
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
    """,
    unsafe_allow_html=True,
)


# =========================================================
# UTILITÁRIOS
# =========================================================
def disparar_foguete():
    st.markdown('<div class="rocket-container">🚀</div>', unsafe_allow_html=True)


def extrair_numero_item(texto):
    try:
        nums = re.findall(r"\d+", str(texto))
        return int(nums[0]) if nums else 9999
    except Exception:
        return 9999


def html_status_prazo(dias):
    if dias is None:
        return '<span style="color: grey;">⚪ SEM DATA</span>'
    if dias < 0:
        return '<div class="alerta-pulsante">❌ ATRASO CRÍTICO</div>'
    if dias <= 3:
        return '<div class="alerta-pulsante">🔴 URGENTE</div>'
    return '<div class="no-prazo">🟢 NO PRAZO</div>'


# =========================================================
# LOGIN
# =========================================================
def login():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔐 Acesso Restrito - Gestão de Gates")
        col_l, _ = st.columns(2)

        with col_l:
            user = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")

            if st.button("Entrar"):
                if (
                    user == st.secrets["credentials"]["master_user"]
                    and password == st.secrets["credentials"]["master_password"]
                ):
                    st.session_state.authenticated = True
                    st.session_state.user_role = "MASTER"
                    st.session_state.user_display = "Administrador (Master)"
                    st.session_state.papel_real = "Gerência Geral"
                    st.rerun()

                try:
                    url_users = (
                        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?"
                        f"tqx=out:csv&sheet=Usuarios"
                    )
                    df_users = pd.read_csv(url_users)
                    df_users["Usuario"] = df_users["Usuario"].astype(str).str.strip()
                    df_users["Senha"] = df_users["Senha"].astype(str).str.strip()

                    user_match = df_users[
                        (df_users["Usuario"] == user)
                        & (df_users["Senha"] == password)
                    ]

                    if not user_match.empty:
                        st.session_state.authenticated = True
                        st.session_state.user_role = "USER"
                        nome_na_tabela = (
                            user_match["Nome"].iloc[0] if "Nome" in df_users.columns else user
                        )
                        st.session_state.user_display = (
                            nome_na_tabela if pd.notnull(nome_na_tabela) else user
                        )
                        st.session_state.papel_real = user_match["Papel"].iloc[0]
                        st.rerun()

                    st.error("Usuário ou senha inválidos")
                except Exception as e:
                    st.error(f"Erro ao conectar com tabela de usuários: {e}")

        return False

    return True


# =========================================================
# LEITURA DE DADOS
# =========================================================
@st.cache_data(ttl=15)
def load_pedidos():
    try:
        response = supabase.table("pedidos").select("*").execute()
        data = response.data or []

        if not data:
            return pd.DataFrame(
                columns=[
                    "ID_Item",
                    "CTR",
                    "Obra",
                    "Item",
                    "Pedido",
                    "Dono",
                    "Status_Atual",
                    "Data_Entrega",
                    "Quantidade",
                    "Unidade",
                    "sort_num",
                ]
            )

        df = pd.DataFrame(data)

        if "id_item" not in df.columns:
            st.error("A tabela 'pedidos' não possui a coluna 'id_item'.")
            return pd.DataFrame()

        df = df.dropna(subset=["id_item"]).copy()
        df["id_item"] = df["id_item"].astype(str).str.strip()

        df = df.rename(
            columns={
                "id_item": "ID_Item",
                "ctr": "CTR",
                "obra": "Obra",
                "item_projeto": "Item",
                "pedido": "Pedido",
                "dono": "Dono",
                "status_atual": "Status_Atual",
                "data_entrega": "Data_Entrega",
                "quantidade": "Quantidade",
                "unidade": "Unidade",
            }
        )

        for col in [
            "CTR",
            "Obra",
            "Item",
            "Pedido",
            "Dono",
            "Status_Atual",
            "Data_Entrega",
            "Quantidade",
            "Unidade",
        ]:
            if col not in df.columns:
                df[col] = ""

        df["sort_num"] = df["Item"].apply(extrair_numero_item)
        return df.drop_duplicates(subset=["ID_Item"], keep="first")

    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_historico_legacy():
    try:
        return conn.read(worksheet="Pedidos_Concluidos")
    except Exception:
        return pd.DataFrame()


# =========================================================
# ESCRITA NO SUPABASE
# =========================================================
def salvar_no_supabase(id_item, novo_status, row_dados=None):
    try:
        payload = {
            "id_item": str(id_item),
            "status_atual": str(novo_status),
        }

        if row_dados is not None:
            qtd_limpa = str(row_dados.get("Quantidade", 0)).replace(",", ".")
            try:
                qtd_final = float(qtd_limpa)
            except Exception:
                qtd_final = 0.0

            payload.update(
                {
                    "ctr": str(row_dados.get("CTR", "")),
                    "obra": str(row_dados.get("Obra", "")),
                    "item_projeto": str(row_dados.get("Item", "")),
                    "pedido": str(row_dados.get("Pedido", "")),
                    "dono": str(row_dados.get("Dono", "")),
                    "data_entrega": (
                        str(row_dados.get("Data_Entrega"))
                        if pd.notnull(row_dados.get("Data_Entrega"))
                        else None
                    ),
                    "quantidade": qtd_final,
                    "unidade": str(row_dados.get("Unidade", "un")),
                }
            )

        supabase.table("pedidos").upsert(payload).execute()
    except Exception as e:
        st.warning(f"Erro sincronia Supabase (Pedidos): {e}")


def log_auditoria_supabase(log_dict):
    try:
        payload = {
            "data": str(log_dict.get("data") or log_dict.get("Data") or ""),
            "pedido": str(log_dict.get("pedido") or log_dict.get("Pedido") or ""),
            "usuario": str(log_dict.get("usuario") or log_dict.get("Usuario") or ""),
            "o_que_mudou": str(log_dict.get("o_que_mudou") or log_dict.get("O que mudou") or ""),
            "impacto_no_prazo": str(log_dict.get("impacto_no_prazo") or log_dict.get("Impacto no Prazo") or "Não"),
            "impacto_financeiro": str(log_dict.get("impacto_financeiro") or log_dict.get("Impacto Financeiro") or "Não"),
            "ctr": str(log_dict.get("ctr") or log_dict.get("CTR") or ""),
            "dono": str(log_dict.get("dono") or log_dict.get("Dono") or ""),
        }
        # ajustado para a tabela que você mostrou no Supabase
        supabase.table("alteracoes").insert(payload).execute()
    except Exception as e:
        st.error(f"Erro ao salvar log no Supabase: {e}")


def atualizar_status_lote(lista_ids, novo_status, df_referencia):
    try:
        for id_item in lista_ids:
            try:
                row = df_referencia[
                    df_referencia["ID_Item"].astype(str) == str(id_item)
                ].iloc[0]
                salvar_no_supabase(id_item, novo_status, row)
            except Exception as e_item:
                st.error(f"Erro no item {id_item}: {e_item}")
                continue

        st.cache_data.clear()
        st.success(f"Sucesso! Status atualizado para '{novo_status}' no banco de dados.")
    except Exception as e:
        st.error(f"Erro geral: {e}")


# =========================================================
# GATE
# =========================================================
def checklist_gate(
    gate_id,
    aba,
    itens_checklist,
    responsavel_r,
    executor_e,
    msg_bloqueio,
    proximo_status,
    objetivo,
    momento,
    df_p,
    papel_usuario,
):
    st.header(f"Ficha de Controle: {gate_id}")
    st.markdown(f"**Objetivo:** {objetivo} | **Momento:** {momento}")
    st.info(f"⚖️ **R:** {responsavel_r} | 🔨 **E:** {executor_e}")

    try:
        status_requerido = (
            "Aguardando Materiais (G1)"
            if gate_id == "GATE 1 (MAT)"
            else "Aguardando Aceite Técnico (G2)"
            if gate_id == "GATE 2 (TEC)"
            else "Aguardando Produção (G3)"
            if gate_id == "GATE 3"
            else "Aguardando Entrega (G4)"
        )

        ctrs_com_itens_pendentes = (
            df_p[df_p["Status_Atual"] == status_requerido]["CTR"].dropna().unique().tolist()
        )
        ctr_lista = [""] + sorted(ctrs_com_itens_pendentes)
        ctr_sel = st.selectbox(f"Selecione a CTR para {gate_id}", ctr_lista, key=f"ctr_gate_{aba}")

        if not ctr_sel:
            return

        itens_pendentes = df_p[
            (df_p["CTR"] == ctr_sel) & (df_p["Status_Atual"] == status_requerido)
        ].sort_values(by="sort_num")

        if itens_pendentes.empty:
            st.info("Não há mais itens pendentes.")
            return

        selecionados = st.multiselect(
            "Itens disponíveis para validação:",
            options=itens_pendentes["ID_Item"].tolist(),
            format_func=lambda x: f"{itens_pendentes[itens_pendentes['ID_Item'] == x]['Pedido'].iloc[0]}",
            default=itens_pendentes["ID_Item"].tolist(),
            key=f"multi_{aba}",
        )

        if not selecionados:
            return

        pode_assinar = (
            papel_usuario == responsavel_r
            or papel_usuario == executor_e
            or papel_usuario == "Gerência Geral"
        )
        if papel_usuario == "Consulta":
            pode_assinar = False

        with st.form(f"form_batch_{aba}"):
            respostas = {}
            for secao, itens in itens_checklist.items():
                st.markdown(f"#### 🔹 {secao}")
                for item in itens:
                    respostas[item] = st.checkbox(
                        item, key=f"chk_{gate_id}_{aba}_{item.replace(' ', '_')}"
                    )

            obs = st.text_area("Observações Técnicas")
            submitted = st.form_submit_button(
                "VALIDAR LOTE SELECIONADO 🚀", disabled=not pode_assinar
            )

            if not submitted:
                return

            if not all(respostas.values()):
                st.error(f"❌ BLOQUEIO: {msg_bloqueio}")
                return

            for id_item in selecionados:
                dono_item = itens_pendentes[itens_pendentes["ID_Item"] == id_item]["Dono"].iloc[0]
                item_nome = itens_pendentes[itens_pendentes["ID_Item"] == id_item]["Pedido"].iloc[0]

                log_entry = {
                    "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "Pedido": item_nome,
                    "Usuario": st.session_state.user_display,
                    "Dono": dono_item,
                    "O que mudou": f"AVANÇO: {gate_id} para {proximo_status}. Obs: {obs}",
                    "Impacto no Prazo": "Não",
                    "Impacto Financeiro": "Não",
                    "CTR": ctr_sel,
                }
                log_auditoria_supabase(log_entry)

                try:
                    supabase.table("checklists_gates").insert(
                        {
                            "gate": gate_id,
                            "id_item": id_item,
                            "validado_por": st.session_state.user_display,
                            "obs": obs,
                            "respostas": respostas,
                        }
                    ).execute()
                except Exception:
                    pass

            atualizar_status_lote(selecionados, proximo_status, df_p)
            st.success(f"🚀 {len(selecionados)} itens validados no banco de dados!")
            disparar_foguete()
            time.sleep(1)
            st.rerun()

    except Exception as e:
        st.error(f"Erro na ficha de controle: {e}")


# =========================================================
# BLOCO PRINCIPAL LOGADO
# =========================================================
if login():
    df_global = load_pedidos()
    df_concluidos_global = load_historico_legacy()

    st.sidebar.success("Login OK")
    st.sidebar.write(f"Pedidos carregados: {len(df_global)}")

    if os.path.exists("Status Apresentação.png"):
        st.sidebar.image("Status Apresentação.png", use_container_width=True)
    else:
        st.sidebar.title("STATUS MARCENARIA")

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
        "📋 Central de Relatórios",
        "🛠️ Portão de Retrabalho",
        "💰 Gate 1: Material",
        "✅ Gate 2: Aceite Técnico",
        "🏭 Gate 3: Production",
        "🚛 Gate 4: Entrega",
        "⚠️ Alteração de Pedido",
        "📥 Importar Itens (Sistema)",
        "⚙️ SINCRONIZAÇÃO SUPABASE",
        "🏁 Concluir Pedidos (Baixa)",
    ]

    if papel_usuario == "Dono do Pedido (DP)":
        for item in [
            "🚨 Auditoria",
            "📈 Indicadores de Performance",
            "🛠️ Portão de Retrabalho",
            "⚙️ SINCRONIZAÇÃO SUPABASE",
            "🏁 Concluir Pedidos (Baixa)",
        ]:
            if item in opcoes_menu:
                opcoes_menu.remove(item)

    menu = st.sidebar.radio("Navegação", opcoes_menu)

    # =====================================================
    # TELAS
    # =====================================================
    if menu == "📉 Monitor por Pedido (CTR)":
        st.header("📉 Monitor de Produção por CTR")
        try:
            df_p = df_global.copy()
            c_f1, c_f2 = st.columns(2)
            filtro_gestor = c_f1.multiselect("Filtrar por Gestor", sorted(df_p["Dono"].dropna().unique()))
            filtro_ctr = c_f2.multiselect("Filtrar por CTR", sorted(df_p["CTR"].dropna().unique()))

            if filtro_gestor:
                df_p = df_p[df_p["Dono"].isin(filtro_gestor)]
            if filtro_ctr:
                df_p = df_p[df_p["CTR"].isin(filtro_ctr)]

            df_p["Data_Entrega_DT"] = pd.to_datetime(df_p["Data_Entrega"], errors="coerce")
            ctrs = (
                df_p.groupby("CTR")
                .agg({"ID_Item": "count", "Data_Entrega_DT": "min", "Dono": "first"})
                .reset_index()
            )

            for _, row in ctrs.sort_values(by="Data_Entrega_DT").iterrows():
                ctr_sel = row["CTR"]
                itens_obra = df_p[df_p["CTR"] == ctr_sel].sort_values(by="sort_num").copy()
                total_itens = len(itens_obra)
                dias = (
                    (row["Data_Entrega_DT"].date() - date.today()).days
                    if pd.notnull(row["Data_Entrega_DT"])
                    else None
                )

                with st.container():
                    c1, c2, c3 = st.columns([4, 3, 3])
                    c1.markdown(f"### {ctr_sel}")
                    c1.write(
                        f"📅 Entrega Crítica: {row['Data_Entrega_DT'].strftime('%d/%m/%Y') if pd.notnull(row['Data_Entrega_DT']) else 'S/D'}"
                    )
                    c2.markdown(f"👤 **Gestor:** {row['Dono']}")

                    with c2.popover(f"🔍 Detalhar Itens ({total_itens})", use_container_width=True):
                        for _, item in itens_obra.iterrows():
                            i_dt = pd.to_datetime(item["Data_Entrega"], errors="coerce")
                            i_dias = (i_dt.date() - date.today()).days if pd.notnull(i_dt) else None
                            cor = "#28a745" if i_dias is not None and i_dias > 3 else "#FF0000" if i_dias is not None else "grey"
                            circulo = f'<span class="semaforo" style="background-color: {cor};"></span>'
                            st.markdown(
                                f"{circulo} **{item['Pedido']}** | 📍 {item['Status_Atual']} | 📅 {i_dt.strftime('%d/%m') if pd.notnull(i_dt) else 'S/D'}",
                                unsafe_allow_html=True,
                            )

                    c3.markdown(html_status_prazo(dias), unsafe_allow_html=True)
                    st.markdown("---")

        except Exception as e:
            st.error(f"Erro no monitor: {e}")

    elif menu == "📊 Resumo e Prazos (Itens)":
        st.header("🚦 Monitor de Produção (Itens)")
        try:
            df_p = df_global.copy().sort_values(by=["Data_Entrega", "sort_num"])
            c_f1, c_f2 = st.columns(2)
            filtro_gestor = c_f1.multiselect("Filtrar por Gestor", sorted(df_p["Dono"].dropna().unique()), key="f_gest_itens")
            filtro_ctr = c_f2.multiselect("Filtrar por CTR", sorted(df_p["CTR"].dropna().unique()), key="f_ctr_itens")

            if filtro_gestor:
                df_p = df_p[df_p["Dono"].isin(filtro_gestor)]
            if filtro_ctr:
                df_p = df_p[df_p["CTR"].isin(filtro_ctr)]

            df_p["Data_Entrega"] = pd.to_datetime(df_p["Data_Entrega"], errors="coerce")

            for _, row in df_p.iterrows():
                dias = (row["Data_Entrega"].date() - date.today()).days if pd.notnull(row["Data_Entrega"]) else None
                if dias is None:
                    status_html = '<span style="color: grey;">⚪ SEM DATA</span>'
                elif dias < 0:
                    status_html = f'<div class="alerta-pulsante">❌ ATRASO ({abs(dias)}d)</div>'
                elif dias <= 3:
                    status_html = f'<div class="alerta-pulsante">🔴 URGENTE ({dias}d)</div>'
                else:
                    status_html = '<div class="no-prazo">🟢 NO PRAZO</div>'

                c1, c2, c3, c4 = st.columns([2, 4, 2, 2])
                c1.write(f"**{row['CTR']}**")
                c2.write(f"**{row['Pedido']}**\n👤 {row['Dono']}")
                c3.write(
                    f"📍 {row['Status_Atual']}\n📅 {row['Data_Entrega'].strftime('%d/%m/%Y') if pd.notnull(row['Data_Entrega']) else 'S/D'}"
                )
                c4.markdown(status_html, unsafe_allow_html=True)
                st.markdown("---")

        except Exception as e:
            st.error(f"Erro no monitor: {e}")

    elif menu == "💰 Gate 1: Material":
        itens = {
            "Materiais": ["Lista validada", "Quantidades conferidas", "Materiais especiais"],
            "Compras": ["Fornecedores definidos", "Lead times confirmados", "Datas registradas"],
            "Financeiro": ["Impacto caixa validado", "Compra autorizada", "Forma de pagamento"],
        }
        checklist_gate(
            "GATE 1 (MAT)",
            "Checklist_G2",
            itens,
            "Financeiro",
            "Compras",
            "Falta material ➡️ PARADO",
            "Aguardando Aceite Técnico (G2)",
            "Fábrica sem parada",
            "Na montagem",
            df_global,
            papel_usuario,
        )

    elif menu == "✅ Gate 2: Aceite Técnico":
        itens = {
            "Informações Comerciais": [
                "Pedido registrado",
                "Cliente identificado",
                "Tipo de obra definido",
                "Responsável identificado",
            ],
            "Escopo Técnico": [
                "Projeto mínimo recebido",
                "Ambientes definidos",
                "Materiais principais",
                "Itens fora do padrão",
            ],
            "Prazo (prévia)": ["Prazo solicitado registrado", "Prazo avaliado", "Risco de prazo"],
            "Governança": ["Dono do Pedido definido", "PCP validou viabilidade", "Aprovado formalmente"],
        }
        checklist_gate(
            "GATE 2 (TEC)",
            "Checklist_G1",
            itens,
            "Dono do Pedido (DP)",
            "PCP",
            "Projeto incompleto ➡️ BLOQUEADO",
            "Aguardando Produção (G3)",
            "Impedir entrada mal definida",
            "Antes do plano",
            df_global,
            papel_usuario,
        )

    elif menu == "🏭 Gate 3: Production":
        itens = {
            "Planejamento": ["Sequenciado", "Capacidade validada", "Gargalo identificado", "Gargalo protegido"],
            "Projeto": ["Projeto técnico liberado", "Medidas conferidas", "Versão registrada"],
            "Comunicação": ["Produção ciente", "Prazo interno registrado", "Alterações registradas"],
        }
        checklist_gate(
            "GATE 3",
            "Checklist_G3",
            itens,
            "PCP",
            "Produção",
            "Sem plano ➡️ BLOQUEADO",
            "Aguardando Entrega (G4)",
            "Produzir planejado",
            "No corte",
            df_global,
            papel_usuario,
        )

    elif menu == "🚛 Gate 4: Entrega":
        itens = {
            "Produto": ["Produção concluída", "Qualidade conferida", "Separados por pedido"],
            "Logística": ["Checklist carga", "Frota definida", "Rota planejada"],
            "Prazo": ["Data validada", "Cliente informado", "Equipe montagem alinhada"],
        }
        checklist_gate(
            "GATE 4",
            "Checklist_G4",
            itens,
            "Dono do Pedido (DP)",
            "Logística",
            "Erro acabamento ➡️ NÃO carrega",
            "CONCLUÍDO ✅",
            "Entrega perfeita",
            "Na carga",
            df_global,
            papel_usuario,
        )

    elif menu == "🏁 Concluir Pedidos (Baixa)":
        st.header("🏁 Baixa Definitiva de Pedidos")
        st.info("Pedidos concluídos saem da lista de ativos e vão para o histórico arquivado no Supabase.")

        if papel_usuario not in ["Gerência Geral", "PCP"]:
            st.error("Acesso restrito ao PCP e Gerência.")
        else:
            df_concluir = df_global[df_global["Status_Atual"] == "CONCLUÍDO ✅"]
            if df_concluir.empty:
                st.warning("Não há itens marcados como 'CONCLUÍDO ✅' para dar baixa no sistema.")
            else:
                ctr_lista = [""] + sorted(df_concluir["CTR"].dropna().unique().tolist())
                ctr_sel = st.selectbox("Selecione a CTR para dar baixa:", ctr_lista)

                if ctr_sel:
                    itens_baixa = df_concluir[df_concluir["CTR"] == ctr_sel]
                    selecionados = st.multiselect(
                        "Selecione os itens para arquivar:",
                        options=itens_baixa["ID_Item"].tolist(),
                        format_func=lambda x: f"{itens_baixa[itens_baixa['ID_Item'] == x]['Pedido'].iloc[0]}",
                        default=itens_baixa["ID_Item"].tolist(),
                    )

                    if selecionados and st.button("🚀 DAR BAIXA E ARQUIVAR SELECIONADOS"):
                        try:
                            for id_item in selecionados:
                                supabase.table("pedidos").update({"status_atual": "ARQUIVADO"}).eq("id_item", id_item).execute()
                                row_baixa = itens_baixa[itens_baixa["ID_Item"] == id_item].iloc[0]
                                log_auditoria_supabase(
                                    {
                                        "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                        "Pedido": str(row_baixa["Pedido"]),
                                        "Usuario": st.session_state.user_display,
                                        "Dono": str(row_baixa["Dono"]),
                                        "O que mudou": "BAIXA DEFINITIVA: Item movido para o histórico arquivado.",
                                        "Impacto no Prazo": "Não",
                                        "Impacto Financeiro": "Não",
                                        "CTR": str(ctr_sel),
                                    }
                                )

                            st.success(f"✅ {len(selecionados)} itens arquivados com sucesso no Supabase!")
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao processar baixa definitiva: {e}")

    elif menu == "🚨 Auditoria":
        st.header("🚨 Auditoria de Alterações (Supabase)")
        st.info("Histórico em tempo real das movimentações registradas no banco de dados.")
        try:
            res = supabase.table("alteracoes").select("*").execute()
            if not res.data:
                st.warning("Nenhum registro de auditoria encontrado no banco de dados.")
            else:
                df_auditoria = pd.DataFrame(res.data)
                if "id" in df_auditoria.columns:
                    df_auditoria = df_auditoria.sort_values(by="id", ascending=False)
                st.dataframe(df_auditoria, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Erro ao carregar auditoria: {e}")

    elif menu == "📈 Indicadores de Performance":
        st.header("📈 Dashboard de Indicadores")
        try:
            df_p = df_global.copy()
            st.subheader("🚧 Fluxo de Itens por Portão")
            gates_count = df_p["Status_Atual"].value_counts()
            c_g1, c_g2, c_g3, c_g4 = st.columns(4)
            c_g1.metric("Materiais (G1)", gates_count.get("Aguardando Materiais (G1)", 0))
            c_g2.metric("Aceite Técnico (G2)", gates_count.get("Aguardando Aceite Técnico (G2)", 0))
            c_g3.metric("Produção (G3)", gates_count.get("Aguardando Produção (G3)", 0))
            c_g4.metric("Entrega (G4)", gates_count.get("Aguardando Entrega (G4)", 0))
        except Exception as e:
            st.error(f"Erro nos indicadores: {e}")

    elif menu == "⚠️ Alteração de Pedido":
        st.header("🔄 Alteração de Pedido em Lote")
        if papel_usuario not in ["Gerência Geral", "PCP"]:
            st.error("Acesso negado.")
        else:
            try:
                df_p = df_global.copy()
                ctr_lista = [""] + sorted(df_p["CTR"].dropna().unique().tolist())
                ctr_sel = st.selectbox("Selecione a CTR", ctr_lista, key="alt_lote_final")

                if ctr_sel:
                    itens_ctr = df_p[df_p["CTR"] == ctr_sel]
                    selecionados = st.multiselect(
                        "Itens:",
                        options=itens_ctr["ID_Item"].tolist(),
                        format_func=lambda x: f"{itens_ctr[itens_ctr['ID_Item'] == x]['Pedido'].iloc[0]}",
                    )

                    if selecionados:
                        with st.form("form_lote_definitivo"):
                            c1, c2 = st.columns(2)
                            gestor_at = itens_ctr[itens_ctr["ID_Item"] == selecionados[0]]["Dono"].iloc[0]
                            novo_gestor = c1.text_input("Novo Gestor", value=gestor_at)
                            nova_data = c2.date_input("Nova Data de Entrega")
                            st.write("---")
                            ci1, ci2 = st.columns(2)
                            imp_p = ci1.radio("Impacto no Prazo?", ["Não", "Sim"], horizontal=True)
                            imp_f = ci2.radio("Impacto Financeiro?", ["Não", "Sim"], horizontal=True)
                            motivo = st.text_area("Motivo da Alteração")

                            if st.form_submit_button("APLICAR ALTERAÇÕES 🚀"):
                                if not motivo:
                                    st.error("❌ O motivo é obrigatório!")
                                else:
                                    for id_item in selecionados:
                                        supabase.table("pedidos").update(
                                            {"dono": novo_gestor, "data_entrega": str(nova_data)}
                                        ).eq("id_item", id_item).execute()

                                        info = itens_ctr[itens_ctr["ID_Item"] == id_item].iloc[0]
                                        log_auditoria_supabase(
                                            {
                                                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                                "pedido": str(info["Pedido"]),
                                                "usuario": st.session_state.user_display,
                                                "o_que_mudou": f"LOTE: Data {nova_data}. Motivo: {motivo}",
                                                "impacto_no_prazo": imp_p,
                                                "impacto_financeiro": imp_f,
                                                "ctr": str(ctr_sel),
                                                "dono": str(novo_gestor),
                                            }
                                        )
                                    st.success(f"✅ Sucesso! {len(selecionados)} itens alterados.")
                                    st.cache_data.clear()
            except Exception as e:
                st.error(f"Erro: {e}")

    elif menu == "⚙️ SINCRONIZAÇÃO SUPABASE":
        st.header("⚙️ Sincronização em Massa")
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("1. Ativos")
            if st.button("🚀 SINCRONIZAR ATIVOS"):
                with st.spinner("Sincronizando ativos..."):
                    for _, row in df_global.iterrows():
                        salvar_no_supabase(row["ID_Item"], row["Status_Atual"], row)
                st.success("Pedidos ativos sincronizados!")

        with c2:
            st.subheader("2. Histórico")
            if st.button("🏁 SINCRONIZAR HISTÓRICO"):
                with st.spinner("Migrando baixas..."):
                    url_sync = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Pedidos_Concluidos"
                    df_hist_full = pd.read_csv(url_sync)
                    prog = st.progress(0)
                    for i, row in df_hist_full.iterrows():
                        salvar_no_supabase(row["ID_Item"], "ARQUIVADO", row)
                        prog.progress((i + 1) / len(df_hist_full))
                st.success("Histórico sincronizado na tabela 'pedidos'!")

    elif menu == "📥 Importar Itens (Sistema)":
        st.header("📥 Importar Itens da Marcenaria")
        st.info("Nesta versão limpa, a importação ainda pode ser adaptada no próximo bloco.")

    elif menu == "🛠️ Portão de Retrabalho":
        st.header("🛠️ Gestão de Retrabalho")
        st.info("Nesta versão limpa, vamos ajustar o retrabalho no próximo bloco.")

    elif menu == "📋 Central de Relatórios":
        st.header("📋 Emissão de Relatórios por CTR")
        st.info("Nesta versão limpa, vamos migrar os relatórios no próximo bloco.")

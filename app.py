import os
import time
import io
from datetime import datetime, date, timedelta

import pandas as pd
import streamlit as st
from services.supabase_client import get_supabase
from utils.helpers import disparar_foguete, extrair_numero_item, html_status_prazo
from services.pedidos_service import (
    load_pedidos,
    load_historico,
    salvar_no_supabase,
    atualizar_status_lote,
)
from services.auditoria_service import log_auditoria_supabase
# =========================================================
# CONFIGURAÇÃO INICIAL
# =========================================================
st.set_page_config(
    page_title="Status - Gestão Integral por Item",
    layout="wide",
    page_icon="🏗️",
)


# =========================================================
# CONEXÕES
# =========================================================
supabase = get_supabase()



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
                # 1) mantém o master do secrets
                if (
                    user == st.secrets["credentials"]["master_user"]
                    and password == st.secrets["credentials"]["master_password"]
                ):
                    st.session_state.authenticated = True
                    st.session_state.user_role = "MASTER"
                    st.session_state.user_display = "Administrador (Master)"
                    st.session_state.papel_real = "Gerência Geral"
                    st.rerun()

                # 2) agora consulta usuários no Supabase
                try:
                    res = (
                        supabase.table("usuarios")
                        .select("*")
                        .eq("usuario", user)
                        .eq("senha", password)
                        .eq("ativo", True)
                        .execute()
                    )

                    data = res.data or []

                    if data:
                        usuario_db = data[0]
                        st.session_state.authenticated = True
                        st.session_state.user_role = "USER"
                        st.session_state.user_display = usuario_db.get("nome") or user
                        st.session_state.papel_real = usuario_db.get("papel") or "Consulta"
                        st.rerun()
                    else:
                        st.error("Usuário ou senha inválidos")

                except Exception as e:
                    st.error(f"Erro ao conectar com usuários no Supabase: {e}")

        return False

    return True


# =========================================================
# LEITURA DE DADOS
# =========================================================


# =========================================================
# ESCRITA NO SUPABASE
# =========================================================





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

            atualizar_status_lote(supabase, selecionados, proximo_status, df_p)
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
    df_global = load_pedidos(supabase, extrair_numero_item)
    df_concluidos_global = load_historico(supabase)

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

    
    elif menu == "📥 Importar Itens (Sistema)":
        st.header("📥 Importar Itens da Marcenaria")
        if papel_usuario not in ["Gerência Geral", "PCP"]:
            st.error("Acesso negado.")
        else:
            up = st.file_uploader("Arquivo egsDataGrid", type=["csv", "xlsx"])
            if up:
                try:
                    df_up = pd.read_csv(up) if up.name.endswith("csv") else pd.read_excel(up)
                    st.dataframe(df_up.head(10), use_container_width=True)

                    if st.button("Confirmar Importação"):
                        existentes = set(df_global["ID_Item"].astype(str).tolist()) if not df_global.empty else set()
                        novos = []

                        for _, r in df_up.iterrows():
                            uid = f"{r['Centro de custo']}-{r['Id Programação']}"
                            dt_crua = pd.to_datetime(r.get("Data Entrega"), errors="coerce")
                            dt_limpa = dt_crua.strftime("%Y-%m-%d") if pd.notnull(dt_crua) else None

                            if str(uid) not in existentes:
                                novos.append(
                                    {
                                        "ID_Item": str(uid),
                                        "CTR": r.get("Centro de custo", ""),
                                        "Obra": r.get("Obra", ""),
                                        "Item": r.get("Item", ""),
                                        "Pedido": r.get("Produto", ""),
                                        "Dono": r.get("Gestor", ""),
                                        "Status_Atual": "Aguardando Materiais (G1)",
                                        "Data_Entrega": dt_limpa,
                                        "Quantidade": r.get("Quantidade", 0),
                                        "Unidade": r.get("Unidade", "un"),
                                    }
                                )

                        if not novos:
                            st.warning("⚠️ Nenhum item novo encontrado.")
                        else:
                            for n in novos:
                                salvar_no_supabase(supabase, n["ID_Item"], n["Status_Atual"], n)
                            st.success(f"✅ {len(novos)} novos itens importados no Supabase!")
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                except Exception as e:
                    st.error(f"Erro na importação: {e}")

    elif menu == "🛠️ Portão de Retrabalho":
        st.header("🛠️ Gestão de Retrabalho")

        try:
            df_ret = df_global[df_global["Status_Atual"] == "⚠️ Em Retrabalho"] if "Status_Atual" in df_global.columns else pd.DataFrame()

            with st.expander("⏪ Reabrir item concluído para retrabalho"):
                df_concluidos_real = df_global[df_global["Status_Atual"].isin(["CONCLUÍDO ✅", "ARQUIVADO"])]

                if df_concluidos_real.empty:
                    st.info("Não há itens concluídos ou arquivados para resgate.")
                else:
                    ctr_resgate = st.selectbox(
                        "Selecione a CTR do item concluído:",
                        [""] + sorted(df_concluidos_real["CTR"].dropna().unique().tolist()),
                    )
                    if ctr_resgate:
                        itens_para_resgatar = df_concluidos_real[df_concluidos_real["CTR"] == ctr_resgate]
                        item_sel = st.selectbox(
                            "Qual item deseja retornar para retrabalho?",
                            options=itens_para_resgatar["ID_Item"].tolist(),
                            format_func=lambda x: f"{itens_para_resgatar[itens_para_resgatar['ID_Item'] == x]['Pedido'].iloc[0]}",
                        )
                        motivo_r = st.text_input("Motivo da reabertura:", key="resgate_motivo")

                        if st.button("🚨 REABRIR E ENVIAR PARA RETRABALHO"):
                            if not motivo_r:
                                st.warning("Descreva o motivo.")
                            else:
                                row_info = itens_para_resgatar[itens_para_resgatar["ID_Item"] == item_sel].iloc[0]
                                salvar_no_supabase(supabase, item_sel, "⚠️ Em Retrabalho", row_info)
                                log_auditoria_supabase(
                                    {
                                        "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                        "Pedido": str(row_info["Pedido"]),
                                        "Usuario": st.session_state.user_display,
                                        "Dono": str(row_info["Dono"]),
                                        "O que mudou": f"REABERTURA DE ITEM CONCLUÍDO: {motivo_r}",
                                        "Impacto no Prazo": "Sim",
                                        "Impacto Financeiro": "Sim",
                                        "CTR": str(ctr_resgate),
                                    }
                                )
                                st.success("Item reaberto com sucesso.")
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()

            st.divider()

            if df_ret.empty:
                st.success("✅ Nenhum item em retrabalho no momento.")
            else:
                ctrs_ret = [""] + sorted(df_ret["CTR"].dropna().unique().tolist())
                ctr_sel = st.selectbox("Selecione a CTR com retrabalho em andamento:", ctrs_ret)

                if ctr_sel:
                    itens_pend = df_ret[df_ret["CTR"] == ctr_sel]
                    selecionados = st.multiselect(
                        "Itens para validar:",
                        options=itens_pend["ID_Item"].tolist(),
                        format_func=lambda x: f"{itens_pend[itens_pend['ID_Item'] == x]['Pedido'].iloc[0]}",
                    )

                    if selecionados:
                        with st.form("form_retrabalho"):
                            st.markdown("#### ✅ Checklist de Qualidade")
                            c1 = st.checkbox("Peça Danificada Identificada")
                            c2 = st.checkbox("Material Solicitado")
                            c3 = st.checkbox("Prioridade Produção Confirmada")
                            obs_ret = st.text_area("Observações do Reparo")
                            proximo_gate = st.selectbox(
                                "Retornar para qual portão?",
                                ["Aguardando Produção (G3)", "Aguardando Entrega (G4)"],
                            )

                            if st.form_submit_button("CONCLUIR RETRABALHO 🛠️"):
                                if not all([c1, c2, c3]):
                                    st.error("Marque todos os itens.")
                                else:
                                    for i in selecionados:
                                        try:
                                            supabase.table("checklists_gates").insert(
                                                {
                                                    "gate": "RETRABALHO",
                                                    "id_item": str(i),
                                                    "validado_por": st.session_state.user_display,
                                                    "obs": obs_ret,
                                                    "respostas": {
                                                        "Dano_Identificado": c1,
                                                        "Material_Solicitado": c2,
                                                        "Prioridade_PCP": c3,
                                                    },
                                                }
                                            ).execute()
                                        except Exception:
                                            pass

                                        row_info = itens_pend[itens_pend["ID_Item"] == i].iloc[0]
                                        log_auditoria_supabase(
                                            {
                                                "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                                "Pedido": str(row_info["Pedido"]),
                                                "Usuario": st.session_state.user_display,
                                                "Dono": str(row_info["Dono"]),
                                                "O que mudou": f"SAÍDA DE RETRABALHO para {proximo_gate}. Obs: {obs_ret}",
                                                "Impacto no Prazo": "Sim",
                                                "Impacto Financeiro": "Não",
                                                "CTR": str(ctr_sel),
                                            }
                                        )

                                    atualizar_status_lote(supabase, selecionados, proximo_gate, itens_pend)
                                    st.success("Retrabalho concluído com sucesso.")
                                    time.sleep(1)
                                    st.rerun()
        except Exception as e:
            st.error(f"Erro na interface de retrabalho: {e}")

    elif menu == "📋 Central de Relatórios":
        st.header("📋 Emissão de Relatórios por CTR")

        try:
            ctrs_disponiveis = sorted(df_global["CTR"].dropna().unique().tolist()) if not df_global.empty else []
            ctr_rel = st.selectbox("Selecione a CTR para gerar o relatório:", [""] + ctrs_disponiveis)

            if ctr_rel:
                tipo_rel = st.radio(
                    "Selecione o Tipo de Relatório:",
                    [
                        "Dossiê Técnico (Fábrica)",
                        "Relatório de Impedimentos (Gestão)",
                        "Certificado de Qualidade (Cliente)",
                    ],
                )

                itens_da_ctr = df_global[df_global["CTR"] == ctr_rel]["ID_Item"].tolist()
                res = supabase.table("checklists_gates").select("*").execute()
                data = res.data or []

                if not data:
                    st.warning("Nenhum checklist encontrado no banco de dados.")
                else:
                    df_chk = pd.DataFrame(data)
                    if "id_item" not in df_chk.columns:
                        st.warning("A tabela de checklists não possui a coluna id_item.")
                    else:
                        df_chk["id_item"] = df_chk["id_item"].astype(str)
                        df_final_rel = df_chk[df_chk["id_item"].isin([str(x) for x in itens_da_ctr])].copy()

                        if df_final_rel.empty:
                            st.warning("Nenhum registro encontrado para esta CTR.")
                        else:
                            df_final_rel = df_final_rel.rename(
                                columns={
                                    "id_item": "ID_Item",
                                    "validado_por": "Validado_Por",
                                    "obs": "Obs",
                                    "gate": "Gate",
                                }
                            )
                            if "created_at" in df_final_rel.columns:
                                df_final_rel["Data"] = pd.to_datetime(df_final_rel["created_at"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
                            elif "Data" not in df_final_rel.columns:
                                df_final_rel["Data"] = ""

                            df_final_rel = df_final_rel.merge(
                                df_global[["ID_Item", "Pedido"]], on="ID_Item", how="left"
                            )
                            df_final_rel = df_final_rel.sort_values(by="Data", ascending=False)

                            if tipo_rel == "Relatório de Impedimentos (Gestão)":
                                df_final_rel = df_final_rel[
                                    df_final_rel["Obs"].astype(str).str.contains(
                                        "BLOQUEADO|PARADO|ERRO|FALTA|PROBLEMA",
                                        case=False,
                                        na=False,
                                    )
                                ]
                            elif tipo_rel == "Certificado de Qualidade (Cliente)":
                                df_final_rel = df_final_rel[
                                    df_final_rel["Gate"].isin(["GATE 4", "GATE 3", "RETRABALHO"])
                                ]

                            st.subheader(f"📄 {tipo_rel}")
                            st.info(f"CTR: {ctr_rel} | Total de Registros: {len(df_final_rel)}")

                            for _, r in df_final_rel.iterrows():
                                with st.expander(f"📅 {r['Data']} - {r['Pedido']} ({r['Gate']})"):
                                    st.write(f"**Responsável:** {r.get('Validado_Por', '')}")
                                    st.write(f"**Nota:** {r.get('Obs', '') or 'Sem comentário adicional.'}")

                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                                cols_export = [c for c in ["Data", "Gate", "Pedido", "Validado_Por", "Obs"] if c in df_final_rel.columns]
                                df_final_rel[cols_export].to_excel(writer, index=False, sheet_name="Relatorio")
                                workbook = writer.book
                                worksheet = writer.sheets["Relatorio"]
                                header_format = workbook.add_format(
                                    {"bold": True, "bg_color": "#634D3E", "font_color": "white"}
                                )
                                for col_num, value in enumerate(cols_export):
                                    worksheet.write(0, col_num, value, header_format)

                            st.download_button(
                                label="📥 Gerar Arquivo para Impressão (Excel)",
                                data=output.getvalue(),
                                file_name=f"Relatorio_{tipo_rel}_{ctr_rel}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
        except Exception as e:
            st.error(f"Erro nos relatórios: {e}")

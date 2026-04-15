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
from services.auth_service import login
from ui.indicadores import render_indicadores
from ui.auditoria import render_auditoria
from ui.monitor_ctr import render_monitor_ctr
from ui.resumo_itens import render_resumo_itens
from ui.relatorios import render_relatorios
from ui.alteracao_lote import render_alteracao_lote
from ui.baixa_definitiva import render_baixa_definitiva
from ui.retrabalho import render_retrabalho
from ui.gates import checklist_gate
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



# =========================================================
# LEITURA DE DADOS
# =========================================================


# =========================================================
# ESCRITA NO SUPABASE
# =========================================================





# =========================================================
# GATE
# =========================================================


# =========================================================
# BLOCO PRINCIPAL LOGADO
# =========================================================
if login(supabase):
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
        render_monitor_ctr(df_global, df_concluidos_global, supabase, html_status_prazo)
    

    elif menu == "📊 Resumo e Prazos (Itens)":
        render_resumo_itens(df_global, df_concluidos_global)
        
    elif menu == "💰 Gate 1: Material":
        itens = {
            "Materiais": ["Lista validada", "Quantidades conferidas", "Materiais especiais"],
            "Compras": ["Fornecedores definidos", "Lead times confirmados", "Datas registradas"],
            "Financeiro": ["Impacto caixa validado", "Compra autorizada", "Forma de pagamento"],
        }
        checklist_gate(
            supabase,
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
            supabase,
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
            supabase,
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
            supabase,
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
        render_baixa_definitiva(df_global, supabase, papel_usuario)

    elif menu == "🚨 Auditoria":
        render_auditoria(supabase)
       
    elif menu == "📈 Indicadores de Performance":
        render_indicadores(df_global)

    elif menu == "⚠️ Alteração de Pedido":
        render_alteracao_lote(df_global, supabase, papel_usuario)

    
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
        render_retrabalho(df_global, supabase, papel_usuario)

    elif menu == "📋 Central de Relatórios":
        render_relatorios(df_global, supabase)

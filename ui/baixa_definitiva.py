from datetime import datetime

import streamlit as st

from services.auditoria_service import log_auditoria_supabase
from services.pedidos_service import atualizar_status_lote


def render_baixa_definitiva(df_global, supabase, papel_usuario):
    st.header("📦 Baixa Definitiva de Pedido")

    if papel_usuario not in ["Gerência Geral", "PCP"]:
        st.error("Acesso negado.")
        return

    try:
        df_p = df_global.copy()

        ctr_lista = [""] + sorted(df_p["CTR"].dropna().unique().tolist())
        ctr_sel = st.selectbox("Selecione a CTR", ctr_lista)

        if not ctr_sel:
            return

        itens_ctr = df_p[df_p["CTR"] == ctr_sel]

        selecionados = st.multiselect(
            "Selecione os itens para arquivar:",
            options=itens_ctr["ID_Item"].tolist(),
            format_func=lambda x: f"{itens_ctr[itens_ctr['ID_Item'] == x]['Pedido'].iloc[0]}",
        )

        if not selecionados:
            return

        motivo = st.text_area("Motivo da baixa definitiva")

        if st.button("📦 CONFIRMAR BAIXA DEFINITIVA"):
            if not motivo:
                st.error("❌ Informe o motivo da baixa.")
                return

            for id_item in selecionados:
                atualizar_status_lote(
                    supabase,
                    [id_item],
                    "ARQUIVADO",
                    df_p,
                )

                info = itens_ctr[itens_ctr["ID_Item"] == id_item].iloc[0]

                log_auditoria_supabase(
                    supabase,
                    {
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "pedido": str(info["Pedido"]),
                        "usuario": st.session_state.user_display,
                        "o_que_mudou": f"BAIXA DEFINITIVA: {motivo}",
                        "impacto_no_prazo": "Não",
                        "impacto_financeiro": "Não",
                        "ctr": str(ctr_sel),
                        "dono": str(info["Dono"]),
                    },
                )

            st.success(f"✅ {len(selecionados)} itens arquivados com sucesso!")
            st.cache_data.clear()
            st.rerun()

    except Exception as e:
        st.error(f"Erro na baixa definitiva: {e}")

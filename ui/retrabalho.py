import streamlit as st
import pandas as pd
from datetime import datetime

from services.pedidos_service import atualizar_status_lote
from services.auditoria_service import log_auditoria_supabase


def render_retrabalho(df_global, supabase, papel_usuario):
    st.header("🔧 Portão de Retrabalho")

    try:
        df_p = df_global.copy()
        df_r = df_p[df_p["Status_Atual"] == "⚠️ Em Retrabalho"]

        if df_r.empty:
            st.info("Nenhum item em retrabalho no momento.")
            return

        ctr_lista = [""] + sorted(df_r["CTR"].dropna().unique().tolist())
        ctr_sel = st.selectbox("Selecione a CTR", ctr_lista)

        if not ctr_sel:
            return

        itens_ctr = df_r[df_r["CTR"] == ctr_sel]

        selecionados = st.multiselect(
            "Itens em retrabalho:",
            options=itens_ctr["ID_Item"].tolist(),
            format_func=lambda x: f"{itens_ctr[itens_ctr['ID_Item'] == x]['Pedido'].iloc[0]}",
        )

        if not selecionados:
            return

        destino = st.selectbox(
            "Enviar novamente para:",
            [
                "Aguardando Materiais (G1)",
                "Aguardando Aceite Técnico (G2)",
                "Aguardando Produção (G3)",
                "Aguardando Entrega (G4)",
            ],
        )

        motivo = st.text_area("Motivo da saída do retrabalho")

        if st.button("🔄 REENVIAR PARA FLUXO"):
            if not motivo:
                st.error("Informe o motivo.")
                return

            for id_item in selecionados:
                atualizar_status_lote(supabase, [id_item], destino, df_p)

                info = itens_ctr[itens_ctr["ID_Item"] == id_item].iloc[0]

                log_auditoria_supabase(
                    supabase,
                    {
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "pedido": str(info["Pedido"]),
                        "usuario": st.session_state.user_display,
                        "o_que_mudou": f"SAÍDA RETRABALHO → {destino}: {motivo}",
                        "impacto_no_prazo": "Sim",
                        "impacto_financeiro": "Sim",
                        "ctr": str(ctr_sel),
                        "dono": str(info["Dono"]),
                    },
                )

            st.success("Itens reenviados para o fluxo!")
            st.cache_data.clear()
            st.rerun()

    except Exception as e:
        st.error(f"Erro no retrabalho: {e}")

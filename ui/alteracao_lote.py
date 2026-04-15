from datetime import datetime

import streamlit as st

from services.auditoria_service import log_auditoria_supabase


def render_alteracao_lote(df_global, supabase, papel_usuario):
    st.header("🔄 Alteração de Pedido em Lote")

    if papel_usuario not in ["Gerência Geral", "PCP"]:
        st.error("Acesso negado.")
        return

    try:
        df_p = df_global.copy()
        ctr_lista = [""] + sorted(df_p["CTR"].dropna().unique().tolist())
        ctr_sel = st.selectbox("Selecione a CTR", ctr_lista, key="alt_lote_final")

        if not ctr_sel:
            return

        itens_ctr = df_p[df_p["CTR"] == ctr_sel]
        selecionados = st.multiselect(
            "Itens:",
            options=itens_ctr["ID_Item"].tolist(),
            format_func=lambda x: f"{itens_ctr[itens_ctr['ID_Item'] == x]['Pedido'].iloc[0]}",
        )

        if not selecionados:
            return

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

            submitted = st.form_submit_button("APLICAR ALTERAÇÕES 🚀")

            if not submitted:
                return

            if not motivo:
                st.error("❌ O motivo é obrigatório!")
                return

            for id_item in selecionados:
                supabase.table("pedidos").update(
                    {"dono": novo_gestor, "data_entrega": str(nova_data)}
                ).eq("id_item", id_item).execute()

                info = itens_ctr[itens_ctr["ID_Item"] == id_item].iloc[0]
                log_auditoria_supabase(
                    supabase,
                    {
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "pedido": str(info["Pedido"]),
                        "usuario": st.session_state.user_display,
                        "o_que_mudou": f"LOTE: Data {nova_data}. Motivo: {motivo}",
                        "impacto_no_prazo": imp_p,
                        "impacto_financeiro": imp_f,
                        "ctr": str(ctr_sel),
                        "dono": str(novo_gestor),
                        "tipo_evento": "ALTERACAO_LOTE",
                    },
                )

            st.success(f"✅ Sucesso! {len(selecionados)} itens alterados.")
            st.cache_data.clear()

    except Exception as e:
        st.error(f"Erro: {e}")

import streamlit as st


def render_indicadores(df_global):
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

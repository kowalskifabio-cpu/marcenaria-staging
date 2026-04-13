import pandas as pd
import streamlit as st


def render_auditoria(supabase):
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

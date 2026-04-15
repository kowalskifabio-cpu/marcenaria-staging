import pandas as pd
import streamlit as st


def render_auditoria(supabase):
    st.header("🚨 Auditoria de Alterações (Supabase)")
    st.warning("VERSAO NOVA DA AUDITORIA - TESTE 01")
    st.info("Histórico em tempo real das movimentações registradas no banco de dados.")

    try:
        res = (
            supabase.table("alteracoes")
            .select("*")
            .order("id", desc=True)
            .limit(200)
            .execute()
        )

        st.write("DEBUG TOTAL RETORNADO:", len(res.data) if res.data else 0)

        if not res.data:
            st.warning("Nenhum registro de auditoria encontrado no banco de dados.")
            return

        df_auditoria = pd.DataFrame(res.data)

        st.write("DEBUG IDs TOPO:", df_auditoria["id"].head(10).tolist() if "id" in df_auditoria.columns else "sem coluna id")

        st.dataframe(df_auditoria, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Erro ao carregar auditoria: {e}")

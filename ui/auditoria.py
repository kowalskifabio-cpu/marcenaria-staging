import pandas as pd
import streamlit as st


def render_auditoria(supabase):
    st.header("🚨 Auditoria de Alterações (Supabase)")
    st.info("Histórico em tempo real das movimentações registradas no banco de dados.")

    try:
        res = (
            supabase.table("alteracoes")
            .select("*")
            .order("id", desc=True)
            .limit(200)
            .execute()
        )

        if not res.data:
            st.warning("Nenhum registro de auditoria encontrado no banco de dados.")
            return

        df_auditoria = pd.DataFrame(res.data)

        # ===== INDICADORES =====
        total_registros = len(df_auditoria)

        retrabalho = df_auditoria[
            df_auditoria["o_que_mudou"].astype(str).str.contains("RETRABALHO", na=False)
        ]

        total_retrabalho = len(retrabalho)

        perc_retrabalho = (
            (total_retrabalho / total_registros) * 100 if total_registros > 0 else 0
        )

        col1, col2, col3 = st.columns(3)

        col1.metric("Total de Eventos", total_registros)
        col2.metric("Retrabalhos", total_retrabalho)
        col3.metric("% Retrabalho", f"{perc_retrabalho:.1f}%")

        st.markdown("---")

        st.dataframe(df_auditoria, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Erro ao carregar auditoria: {e}")

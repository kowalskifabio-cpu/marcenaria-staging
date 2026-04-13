from datetime import date
import pandas as pd
import streamlit as st


def render_resumo_itens(df_global, df_concluidos_global):
    st.header("🚦 Monitor de Produção (Itens)")

    try:
        df_p = df_global.copy().sort_values(by=["Data_Entrega", "sort_num"])

        c_f1, c_f2 = st.columns(2)
        filtro_gestor = c_f1.multiselect(
            "Filtrar por Gestor",
            sorted(df_p["Dono"].dropna().unique()),
            key="f_gest_itens",
        )
        filtro_ctr = c_f2.multiselect(
            "Filtrar por CTR",
            sorted(df_p["CTR"].dropna().unique()),
            key="f_ctr_itens",
        )

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

        if not df_concluidos_global.empty:
            st.markdown("### 🏁 Itens Arquivados")
            with st.expander("Clique para expandir o histórico de baixas"):
                df_c_filtro = df_concluidos_global.copy()

                if filtro_ctr:
                    df_c_filtro = df_c_filtro[df_c_filtro["CTR"].isin(filtro_ctr)]
                if filtro_gestor:
                    df_c_filtro = df_c_filtro[df_c_filtro["Dono"].isin(filtro_gestor)]

                cols = [c for c in ["CTR", "Pedido", "Data_Entrega", "Data_Finalizacao", "Performance"] if c in df_c_filtro.columns]
                if cols:
                    st.dataframe(df_c_filtro[cols], use_container_width=True)
                else:
                    st.dataframe(df_c_filtro, use_container_width=True)

    except Exception as e:
        st.error(f"Erro no monitor: {e}")

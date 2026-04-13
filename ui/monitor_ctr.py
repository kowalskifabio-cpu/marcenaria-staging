from datetime import date
import pandas as pd
import streamlit as st

from services.auditoria_service import log_auditoria_supabase
from services.pedidos_service import atualizar_status_lote


def render_monitor_ctr(df_global, df_concluidos_global, supabase, html_status_prazo):
    st.header("📉 Monitor de Produção por CTR")

    try:
        df_p = df_global.copy()

        c_f1, c_f2 = st.columns(2)
        filtro_gestor = c_f1.multiselect(
            "Filtrar por Gestor",
            sorted(df_p["Dono"].dropna().unique())
        )
        filtro_ctr = c_f2.multiselect(
            "Filtrar por CTR",
            sorted(df_p["CTR"].dropna().unique())
        )

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

                        if item["Status_Atual"] != "⚠️ Em Retrabalho":
                            with st.expander("🚨 Sinalizar Retrabalho"):
                                motivo_ret = st.text_input(
                                    "Motivo do Retrabalho",
                                    key=f"ret_{item['ID_Item']}"
                                )

                                if st.button("CONFIRMAR RETRABALHO", key=f"btn_ret_{item['ID_Item']}"):
                                    if not motivo_ret:
                                        st.warning("Descreva o motivo.")
                                    else:
                                        st.write("ID_ITEM ENVIADO:", item["ID_Item"])
                                        atualizar_status_lote(
                                            supabase,
                                            [str(item["ID_Item"]).strip()],
                                            "⚠️ Em Retrabalho",
                                            df_p,
                                        )

                                        log_r = {
                                            "Data": pd.Timestamp.now().strftime("%d/%m/%Y %H:%M"),
                                            "Pedido": item["Pedido"],
                                            "Usuario": st.session_state.user_display,
                                            "Dono": item["Dono"],
                                            "O que mudou": f"ENTRADA RETRABALHO: {motivo_ret}",
                                            "Impacto no Prazo": "Sim",
                                            "Impacto Financeiro": "Sim",
                                            "CTR": ctr_sel,
                                        }

                                        log_auditoria_supabase(supabase, log_r)

                                        st.success("Item movido para retrabalho!")
                                        st.cache_data.clear()
                                        st.rerun()

                c3.markdown(html_status_prazo(dias), unsafe_allow_html=True)
                st.markdown("---")

        if not df_concluidos_global.empty:
            st.markdown("### 🏁 Histórico de Pedidos Concluídos")
            with st.expander("Ver itens arquivados desta consulta"):
                df_c_filtro = df_concluidos_global.copy()

                if filtro_ctr:
                    df_c_filtro = df_c_filtro[df_c_filtro["CTR"].isin(filtro_ctr)]
                if filtro_gestor:
                    df_c_filtro = df_c_filtro[df_c_filtro["Dono"].isin(filtro_gestor)]

                if df_c_filtro.empty:
                    st.info("Nenhum item concluído para os filtros.")
                else:
                    cols = [c for c in ["CTR", "Pedido", "Dono", "Data_Finalizacao", "Performance"] if c in df_c_filtro.columns]
                    st.dataframe(df_c_filtro[cols], use_container_width=True)

    except Exception as e:
        st.error(f"Erro no monitor: {e}")

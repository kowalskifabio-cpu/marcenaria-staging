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
            .limit(500)
            .execute()
        )

        if not res.data:
            st.warning("Nenhum registro de auditoria encontrado no banco de dados.")
            return

        df_auditoria = pd.DataFrame(res.data)

        if "data" in df_auditoria.columns:
            df_auditoria["data_dt"] = pd.to_datetime(
                df_auditoria["data"],
                format="%d/%m/%Y %H:%M",
                errors="coerce",
                dayfirst=True,
            )
        else:
            df_auditoria["data_dt"] = pd.NaT

        st.subheader("Filtros")

        colf1, colf2, colf3 = st.columns(3)

        lista_gestores = (
            sorted(df_auditoria["dono"].dropna().astype(str).unique().tolist())
            if "dono" in df_auditoria.columns
            else []
        )
        lista_ctr = (
            sorted(df_auditoria["ctr"].dropna().astype(str).unique().tolist())
            if "ctr" in df_auditoria.columns
            else []
        )

        filtro_gestor = colf1.multiselect("Filtrar por Gestor", lista_gestores)
        filtro_ctr = colf2.multiselect("Filtrar por CTR", lista_ctr)

        data_min = df_auditoria["data_dt"].min()
        data_max = df_auditoria["data_dt"].max()

        if pd.notnull(data_min) and pd.notnull(data_max):
            filtro_data_inicial = colf3.date_input("Data inicial", value=data_min.date())
            filtro_data_final = st.date_input("Data final", value=data_max.date())
        else:
            filtro_data_inicial = None
            filtro_data_final = None

        df_filtrado = df_auditoria.copy()

        if filtro_gestor:
            df_filtrado = df_filtrado[df_filtrado["dono"].astype(str).isin(filtro_gestor)]

        if filtro_ctr:
            df_filtrado = df_filtrado[df_filtrado["ctr"].astype(str).isin(filtro_ctr)]

        if filtro_data_inicial and filtro_data_final:
            df_filtrado = df_filtrado[
                (df_filtrado["data_dt"].dt.date >= filtro_data_inicial)
                & (df_filtrado["data_dt"].dt.date <= filtro_data_final)
            ]

        total_registros = len(df_filtrado)

        retrabalho = df_filtrado[
            df_filtrado["tipo_evento"].astype(str) == "RETRABALHO"
        ] if "tipo_evento" in df_filtrado.columns else pd.DataFrame()
        
        total_retrabalho = len(retrabalho)

        perc_retrabalho = (
            (total_retrabalho / total_registros) * 100 if total_registros > 0 else 0
        )

        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Eventos", total_registros)
        col2.metric("Retrabalhos", total_retrabalho)
        col3.metric("% Retrabalho", f"{perc_retrabalho:.1f}%")

        st.markdown("---")

        st.subheader("Retrabalho por Gestor")

        if "dono" in df_filtrado.columns:
            base_retrabalho = df_filtrado[
                df_filtrado["tipo_evento"].astype(str) == "RETRABALHO"
            ].copy() if "tipo_evento" in df_filtrado.columns else pd.DataFrame()

            if base_retrabalho.empty:
                st.info("Nenhum retrabalho encontrado para os filtros aplicados.")
            else:
                total_por_gestor = (
                    df_filtrado.groupby("dono")
                    .size()
                    .reset_index(name="total_eventos")
                )

                retrabalho_por_gestor = (
                    base_retrabalho.groupby("dono")
                    .size()
                    .reset_index(name="retrabalhos")
                )

                resumo_gestor = total_por_gestor.merge(
                    retrabalho_por_gestor,
                    on="dono",
                    how="left"
                )

                resumo_gestor["retrabalhos"] = resumo_gestor["retrabalhos"].fillna(0).astype(int)

                resumo_gestor["%_retrabalho"] = (
                    (resumo_gestor["retrabalhos"] / resumo_gestor["total_eventos"]) * 100
                ).round(1)

                resumo_gestor = resumo_gestor.sort_values(
                    by="%_retrabalho",
                    ascending=False
                )

                st.dataframe(
                    resumo_gestor,
                    use_container_width=True,
                    hide_index=True
                )

        st.markdown("---")

        cols_exibir = [
            c for c in [
                "id",
                "data",
                "pedido",
                "usuario",
                "tipo_evento",
                "o_que_mudou",
                "impacto_no_prazo",
                "impacto_financeiro",
                "ctr",
                "dono",
            ]
            if c in df_filtrado.columns
        ]

        st.dataframe(
            df_filtrado[cols_exibir],
            use_container_width=True,
            hide_index=True,
        )

    except Exception as e:
        st.error(f"Erro ao carregar auditoria: {e}")

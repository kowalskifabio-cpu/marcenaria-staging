from datetime import date
import pandas as pd
import streamlit as st


def render_indicadores(df_global, df_concluidos_global):
    st.header("📊 Dashboard de Indicadores")

    try:
        df_p = df_global.copy()
        df_h = df_concluidos_global.copy() if df_concluidos_global is not None else pd.DataFrame()

        # ===== TRATAMENTO DE DATAS =====
        if "Data_Entrega" in df_p.columns:
            df_p["data_entrega_dt"] = pd.to_datetime(df_p["Data_Entrega"], errors="coerce")
        else:
            df_p["data_entrega_dt"] = pd.NaT

        if not df_h.empty:
            if "Data_Entrega" in df_h.columns:
                df_h["data_entrega_dt"] = pd.to_datetime(df_h["Data_Entrega"], errors="coerce")
            else:
                df_h["data_entrega_dt"] = pd.NaT

        # ===== FILTROS =====
        st.subheader("Filtros")

        colf1, colf2, colf3, colf4 = st.columns(4)

        lista_gestores = sorted(df_p["Dono"].dropna().astype(str).unique().tolist()) if "Dono" in df_p.columns else []
        lista_ctr = sorted(df_p["CTR"].dropna().astype(str).unique().tolist()) if "CTR" in df_p.columns else []

        filtro_gestor = colf1.multiselect("Gestor", lista_gestores)
        filtro_ctr = colf2.multiselect("CTR", lista_ctr)

        data_min = df_p["data_entrega_dt"].min()
        data_max = df_p["data_entrega_dt"].max()

        if pd.notnull(data_min) and pd.notnull(data_max):
            filtro_data_inicial = colf3.date_input("Data inicial", value=data_min.date(), key="ind_data_ini")
            filtro_data_final = colf4.date_input("Data final", value=data_max.date(), key="ind_data_fim")
        else:
            filtro_data_inicial = None
            filtro_data_final = None

        df_filtrado = df_p.copy()

        if filtro_gestor:
            df_filtrado = df_filtrado[df_filtrado["Dono"].astype(str).isin(filtro_gestor)]

        if filtro_ctr:
            df_filtrado = df_filtrado[df_filtrado["CTR"].astype(str).isin(filtro_ctr)]

        if filtro_data_inicial and filtro_data_final:
            df_filtrado = df_filtrado[
                (df_filtrado["data_entrega_dt"].dt.date >= filtro_data_inicial)
                & (df_filtrado["data_entrega_dt"].dt.date <= filtro_data_final)
            ]

        # histórico filtrado com a mesma lógica
        df_h_filtrado = df_h.copy() if not df_h.empty else pd.DataFrame()

        if not df_h_filtrado.empty:
            if filtro_gestor and "Dono" in df_h_filtrado.columns:
                df_h_filtrado = df_h_filtrado[df_h_filtrado["Dono"].astype(str).isin(filtro_gestor)]

            if filtro_ctr and "CTR" in df_h_filtrado.columns:
                df_h_filtrado = df_h_filtrado[df_h_filtrado["CTR"].astype(str).isin(filtro_ctr)]

            if filtro_data_inicial and filtro_data_final:
                df_h_filtrado = df_h_filtrado[
                    (df_h_filtrado["data_entrega_dt"].dt.date >= filtro_data_inicial)
                    & (df_h_filtrado["data_entrega_dt"].dt.date <= filtro_data_final)
                ]

        # ===== INDICADORES GERAIS =====
        hoje = date.today()

        total_ativos = len(df_filtrado)

        atrasados = df_filtrado[
            (df_filtrado["data_entrega_dt"].notna())
            & (df_filtrado["data_entrega_dt"].dt.date < hoje)
            & (~df_filtrado["Status_Atual"].astype(str).isin(["CONCLUÍDO ✅", "ARQUIVADO"]))
        ]
        total_atrasados = len(atrasados)

        retrabalho = df_filtrado[
            df_filtrado["Status_Atual"].astype(str) == "⚠️ Em Retrabalho"
        ]
        total_retrabalho = len(retrabalho)

        perc_retrabalho = (total_retrabalho / total_ativos * 100) if total_ativos > 0 else 0

        total_arquivados = len(df_h_filtrado) if not df_h_filtrado.empty else 0

        st.subheader("Resumo Executivo")

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Itens Ativos", total_ativos)
        col2.metric("Atrasados", total_atrasados)
        col3.metric("Em Retrabalho", total_retrabalho)
        col4.metric("% Retrabalho", f"{perc_retrabalho:.1f}%")
        col5.metric("Arquivados", total_arquivados)

        st.markdown("---")

        # ===== FLUXO POR GATE =====
        st.subheader("Fluxo de Itens por Gate")

        gates_map = {
            "Aguardando Materiais (G1)": "Materiais (G1)",
            "Aguardando Aceite Técnico (G2)": "Aceite Técnico (G2)",
            "Aguardando Produção (G3)": "Produção (G3)",
            "Aguardando Entrega (G4)": "Entrega (G4)",
        }

        gates_count = df_filtrado["Status_Atual"].astype(str).value_counts()

        cg1, cg2, cg3, cg4 = st.columns(4)
        cg1.metric("Materiais (G1)", gates_count.get("Aguardando Materiais (G1)", 0))
        cg2.metric("Aceite Técnico (G2)", gates_count.get("Aguardando Aceite Técnico (G2)", 0))
        cg3.metric("Produção (G3)", gates_count.get("Aguardando Produção (G3)", 0))
        cg4.metric("Entrega (G4)", gates_count.get("Aguardando Entrega (G4)", 0))

        st.markdown("---")

        # ===== RESUMO POR GESTOR =====
        st.subheader("Resumo por Gestor")

        if "Dono" not in df_filtrado.columns or df_filtrado.empty:
            st.info("Não há dados suficientes para montar o resumo por gestor.")
        else:
            base_gestor = df_filtrado.copy()

            resumo_gestor = (
                base_gestor.groupby("Dono")
                .size()
                .reset_index(name="ativos")
            )

            atrasados_gestor = (
                atrasados.groupby("Dono")
                .size()
                .reset_index(name="atrasados")
                if not atrasados.empty else pd.DataFrame(columns=["Dono", "atrasados"])
            )

            retrabalho_gestor = (
                retrabalho.groupby("Dono")
                .size()
                .reset_index(name="retrabalhos")
                if not retrabalho.empty else pd.DataFrame(columns=["Dono", "retrabalhos"])
            )

            resumo_gestor = resumo_gestor.merge(atrasados_gestor, on="Dono", how="left")
            resumo_gestor = resumo_gestor.merge(retrabalho_gestor, on="Dono", how="left")

            resumo_gestor["atrasados"] = resumo_gestor["atrasados"].fillna(0).astype(int)
            resumo_gestor["retrabalhos"] = resumo_gestor["retrabalhos"].fillna(0).astype(int)
            resumo_gestor["%_retrabalho"] = (
                (resumo_gestor["retrabalhos"] / resumo_gestor["ativos"]) * 100
            ).round(1)

            resumo_gestor = resumo_gestor.sort_values(by="%_retrabalho", ascending=False)

            st.dataframe(resumo_gestor, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ===== ITENS MAIS CRÍTICOS =====
        st.subheader("Itens Atrasados")

        if atrasados.empty:
            st.success("Nenhum item atrasado dentro dos filtros aplicados.")
        else:
            cols_atrasados = [
                c for c in ["CTR", "Pedido", "Dono", "Status_Atual", "Data_Entrega"]
                if c in atrasados.columns
            ]
            st.dataframe(
                atrasados[cols_atrasados].sort_values(by="Data_Entrega"),
                use_container_width=True,
                hide_index=True,
            )

    except Exception as e:
        st.error(f"Erro nos indicadores: {e}")

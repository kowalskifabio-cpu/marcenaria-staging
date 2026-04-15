import io

import pandas as pd
import streamlit as st


def render_relatorios(df_global, supabase):
    st.header("📋 Emissão de Relatórios por CTR")

    try:
        tipo_rel = st.radio(
            "Selecione o Tipo de Relatório:",
            [
                "Dossiê Técnico (Fábrica)",
                "Relatório de Impedimentos (Gestão)",
                "Certificado de Qualidade (Cliente)",
                "Pendências por Gate",
            ],
        )

        # =====================================================
        # NOVO RELATÓRIO: PENDÊNCIAS POR GATE
        # =====================================================
        if tipo_rel == "Pendências por Gate":
            st.subheader("🚨 Pendências por Gate")

            mapa_gates = {
                "Gate 1 - Materiais": "Aguardando Materiais (G1)",
                "Gate 2 - Aceite Técnico": "Aguardando Aceite Técnico (G2)",
                "Gate 3 - Produção": "Aguardando Produção (G3)",
                "Gate 4 - Entrega": "Aguardando Entrega (G4)",
            }

            colf1, colf2, colf3 = st.columns(3)

            gate_escolhido = colf1.selectbox(
                "Selecione o Gate",
                list(mapa_gates.keys()),
            )

            lista_gestores = (
                sorted(df_global["Dono"].dropna().astype(str).unique().tolist())
                if "Dono" in df_global.columns
                else []
            )
            filtro_gestor = colf2.multiselect("Filtrar por Gestor", lista_gestores)

            lista_ctr = (
                sorted(df_global["CTR"].dropna().astype(str).unique().tolist())
                if "CTR" in df_global.columns
                else []
            )
            filtro_ctr = colf3.multiselect("Filtrar por CTR", lista_ctr)

            status_pendente = mapa_gates[gate_escolhido]

            df_pendente = df_global.copy()
            df_pendente = df_pendente[
                df_pendente["Status_Atual"].astype(str) == status_pendente
            ].copy()

            if filtro_gestor:
                df_pendente = df_pendente[
                    df_pendente["Dono"].astype(str).isin(filtro_gestor)
                ]

            if filtro_ctr:
                df_pendente = df_pendente[
                    df_pendente["CTR"].astype(str).isin(filtro_ctr)
                ]

            total_pendentes = len(df_pendente)

            ctrs_pendentes = (
                df_pendente["CTR"].nunique()
                if "CTR" in df_pendente.columns and not df_pendente.empty
                else 0
            )

            gestores_pendentes = (
                df_pendente["Dono"].nunique()
                if "Dono" in df_pendente.columns and not df_pendente.empty
                else 0
            )

            c1, c2, c3 = st.columns(3)
            c1.metric("Itens Pendentes", total_pendentes)
            c2.metric("CTRs com Pendência", ctrs_pendentes)
            c3.metric("Gestores Envolvidos", gestores_pendentes)

            st.markdown("---")

            if df_pendente.empty:
                st.success("Nenhuma pendência encontrada para os filtros aplicados.")
                return

            st.subheader("Resumo por CTR")

            resumo_ctr = (
                df_pendente.groupby(["CTR", "Dono"])
                .size()
                .reset_index(name="itens_pendentes")
                .sort_values(by=["itens_pendentes", "CTR"], ascending=[False, True])
            )

            st.dataframe(resumo_ctr, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("Itens Pendentes")

            cols_exibir = [
                c for c in [
                    "CTR",
                    "Pedido",
                    "Item",
                    "Dono",
                    "Status_Atual",
                    "Data_Entrega",
                ]
                if c in df_pendente.columns
            ]

            st.dataframe(
                df_pendente[cols_exibir].sort_values(by=["CTR", "Dono", "Pedido"]),
                use_container_width=True,
                hide_index=True,
            )

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                resumo_ctr.to_excel(writer, index=False, sheet_name="Resumo_CTR")
                df_pendente[cols_exibir].to_excel(writer, index=False, sheet_name="Itens_Pendentes")

            st.download_button(
                label="📥 Exportar Pendências por Gate (Excel)",
                data=output.getvalue(),
                file_name=f"Pendencias_{gate_escolhido.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            return

        # =====================================================
        # RELATÓRIOS EXISTENTES
        # =====================================================
        ctrs_disponiveis = (
            sorted(df_global["CTR"].dropna().unique().tolist())
            if not df_global.empty
            else []
        )
        ctr_rel = st.selectbox(
            "Selecione a CTR para gerar o relatório:",
            [""] + ctrs_disponiveis,
        )

        if not ctr_rel:
            return

        itens_da_ctr = df_global[df_global["CTR"] == ctr_rel]["ID_Item"].tolist()
        res = supabase.table("checklists_gates").select("*").execute()
        data = res.data or []

        if not data:
            st.warning("Nenhum checklist encontrado no banco de dados.")
            return

        df_chk = pd.DataFrame(data)

        if "id_item" not in df_chk.columns:
            st.warning("A tabela de checklists não possui a coluna id_item.")
            return

        df_chk["id_item"] = df_chk["id_item"].astype(str)
        df_final_rel = df_chk[
            df_chk["id_item"].isin([str(x) for x in itens_da_ctr])
        ].copy()

        if df_final_rel.empty:
            st.warning("Nenhum registro encontrado para esta CTR.")
            return

        df_final_rel = df_final_rel.rename(
            columns={
                "id_item": "ID_Item",
                "validado_por": "Validado_Por",
                "obs": "Obs",
                "gate": "Gate",
            }
        )

        if "created_at" in df_final_rel.columns:
            df_final_rel["Data"] = pd.to_datetime(
                df_final_rel["created_at"], errors="coerce"
            ).dt.strftime("%d/%m/%Y %H:%M")
        elif "Data" not in df_final_rel.columns:
            df_final_rel["Data"] = ""

        df_final_rel = df_final_rel.merge(
            df_global[["ID_Item", "Pedido"]],
            on="ID_Item",
            how="left",
        )
        df_final_rel = df_final_rel.sort_values(by="Data", ascending=False)

        if tipo_rel == "Relatório de Impedimentos (Gestão)":
            df_final_rel = df_final_rel[
                df_final_rel["Obs"].astype(str).str.contains(
                    "BLOQUEADO|PARADO|ERRO|FALTA|PROBLEMA",
                    case=False,
                    na=False,
                )
            ]
        elif tipo_rel == "Certificado de Qualidade (Cliente)":
            df_final_rel = df_final_rel[
                df_final_rel["Gate"].isin(["GATE 4", "GATE 3", "RETRABALHO"])
            ]

        st.subheader(f"📄 {tipo_rel}")
        st.info(f"CTR: {ctr_rel} | Total de Registros: {len(df_final_rel)}")

        for _, r in df_final_rel.iterrows():
            with st.expander(f"📅 {r['Data']} - {r['Pedido']} ({r['Gate']})"):
                st.write(f"**Responsável:** {r.get('Validado_Por', '')}")
                st.write(f"**Nota:** {r.get('Obs', '') or 'Sem comentário adicional.'}")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            cols_export = [
                c
                for c in ["Data", "Gate", "Pedido", "Validado_Por", "Obs"]
                if c in df_final_rel.columns
            ]
            df_final_rel[cols_export].to_excel(
                writer, index=False, sheet_name="Relatorio"
            )

            workbook = writer.book
            worksheet = writer.sheets["Relatorio"]
            header_format = workbook.add_format(
                {"bold": True, "bg_color": "#634D3E", "font_color": "white"}
            )

            for col_num, value in enumerate(cols_export):
                worksheet.write(0, col_num, value, header_format)

        st.download_button(
            label="📥 Gerar Arquivo para Impressão (Excel)",
            data=output.getvalue(),
            file_name=f"Relatorio_{tipo_rel}_{ctr_rel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        st.error(f"Erro nos relatórios: {e}")

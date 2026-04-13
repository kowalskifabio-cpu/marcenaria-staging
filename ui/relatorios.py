import io

import pandas as pd
import streamlit as st


def render_relatorios(df_global, supabase):
    st.header("📋 Emissão de Relatórios por CTR")

    try:
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

        tipo_rel = st.radio(
            "Selecione o Tipo de Relatório:",
            [
                "Dossiê Técnico (Fábrica)",
                "Relatório de Impedimentos (Gestão)",
                "Certificado de Qualidade (Cliente)",
            ],
        )

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

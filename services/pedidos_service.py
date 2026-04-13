import pandas as pd
import streamlit as st


def load_pedidos(_supabase, extrair_numero_item):
    try:
        response = _supabase.table("pedidos").select("*").execute()
        data = response.data or []

        if not data:
            return pd.DataFrame(
                columns=[
                    "ID_Item",
                    "CTR",
                    "Obra",
                    "Item",
                    "Pedido",
                    "Dono",
                    "Status_Atual",
                    "Data_Entrega",
                    "Quantidade",
                    "Unidade",
                    "sort_num",
                ]
            )

        df = pd.DataFrame(data)

        if "id_item" not in df.columns:
            st.error("A tabela 'pedidos' não possui a coluna 'id_item'.")
            return pd.DataFrame()

        df = df.dropna(subset=["id_item"]).copy()
        df["id_item"] = df["id_item"].astype(str).str.strip()

        df = df.rename(
            columns={
                "id_item": "ID_Item",
                "ctr": "CTR",
                "obra": "Obra",
                "item_projeto": "Item",
                "pedido": "Pedido",
                "dono": "Dono",
                "status_atual": "Status_Atual",
                "data_entrega": "Data_Entrega",
                "quantidade": "Quantidade",
                "unidade": "Unidade",
            }
        )

        for col in [
            "CTR",
            "Obra",
            "Item",
            "Pedido",
            "Dono",
            "Status_Atual",
            "Data_Entrega",
            "Quantidade",
            "Unidade",
        ]:
            if col not in df.columns:
                df[col] = ""

        df["sort_num"] = df["Item"].apply(extrair_numero_item)
        return df.drop_duplicates(subset=["ID_Item"], keep="first")

    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
        return pd.DataFrame()


def load_historico(_supabase):
    try:
        response = (
            _supabase.table("pedidos")
            .select("*")
            .eq("status_atual", "ARQUIVADO")
            .execute()
        )

        data = response.data or []

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)

        if "id_item" not in df.columns:
            return pd.DataFrame()

        df = df.rename(
            columns={
                "id_item": "ID_Item",
                "ctr": "CTR",
                "obra": "Obra",
                "item_projeto": "Item",
                "pedido": "Pedido",
                "dono": "Dono",
                "status_atual": "Status_Atual",
                "data_entrega": "Data_Entrega",
                "quantidade": "Quantidade",
                "unidade": "Unidade",
            }
        )

        if "Data_Finalizacao" not in df.columns:
            df["Data_Finalizacao"] = ""

        if "Performance" not in df.columns:
            df["Performance"] = ""

        return df

    except Exception as e:
        st.error(f"Erro ao carregar histórico do Supabase: {e}")
        return pd.DataFrame()


def salvar_no_supabase(supabase, id_item, novo_status, row_dados=None):
    try:
        payload = {
            "id_item": str(id_item),
            "status_atual": str(novo_status),
        }

        if row_dados is not None:
            qtd_limpa = str(row_dados.get("Quantidade", 0)).replace(",", ".")
            try:
                qtd_final = float(qtd_limpa)
            except Exception:
                qtd_final = 0.0

            payload.update(
                {
                    "ctr": str(row_dados.get("CTR", "")),
                    "obra": str(row_dados.get("Obra", "")),
                    "item_projeto": str(row_dados.get("Item", "")),
                    "pedido": str(row_dados.get("Pedido", "")),
                    "dono": str(row_dados.get("Dono", "")),
                    "data_entrega": (
                        str(row_dados.get("Data_Entrega"))
                        if pd.notnull(row_dados.get("Data_Entrega"))
                        else None
                    ),
                    "quantidade": qtd_final,
                    "unidade": str(row_dados.get("Unidade", "un")),
                }
            )

        _supabase.table("pedidos").upsert(payload).execute()
    except Exception as e:
        st.warning(f"Erro sincronia Supabase (Pedidos): {e}")


def atualizar_status_lote(supabase, lista_ids, novo_status, df_referencia):
    try:
        for id_item in lista_ids:
            try:
                row = df_referencia[
                    df_referencia["ID_Item"].astype(str).str.strip() == str(id_item).strip()
                ].iloc[0]
                salvar_no_supabase(supabase, id_item, novo_status, row)
            except Exception as e_item:
                st.error(f"Erro no item {id_item}: {e_item}")
                continue

        st.cache_data.clear()
        st.success(f"Sucesso! Status atualizado para '{novo_status}' no banco de dados.")
    except Exception as e:
        st.error(f"Erro geral: {e}")

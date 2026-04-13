import streamlit as st


def log_auditoria_supabase(supabase, log_dict):
    try:
        payload = {
            "data": str(log_dict.get("data") or log_dict.get("Data") or ""),
            "pedido": str(log_dict.get("pedido") or log_dict.get("Pedido") or ""),
            "usuario": str(log_dict.get("usuario") or log_dict.get("Usuario") or ""),
            "o_que_mudou": str(log_dict.get("o_que_mudou") or log_dict.get("O que mudou") or ""),
            "impacto_no_prazo": str(
                log_dict.get("impacto_no_prazo")
                or log_dict.get("Impacto no Prazo")
                or "Não"
            ),
            "impacto_financeiro": str(
                log_dict.get("impacto_financeiro")
                or log_dict.get("Impacto Financeiro")
                or "Não"
            ),
            "ctr": str(log_dict.get("ctr") or log_dict.get("CTR") or ""),
            "dono": str(log_dict.get("dono") or log_dict.get("Dono") or ""),
        }

        supabase.table("alteracoes").insert(payload).execute()

    except Exception as e:
        st.error(f"Erro ao salvar log no Supabase: {e}")

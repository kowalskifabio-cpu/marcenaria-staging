import streamlit as st
import time
from datetime import datetime

from services.auditoria_service import log_auditoria_supabase
from services.pedidos_service import atualizar_status_lote
from utils.helpers import disparar_foguete
from utils.helpers import agora_br_str

def checklist_gate(
    supabase,
    gate_id,
    aba,
    itens_checklist,
    responsavel_r,
    executor_e,
    msg_bloqueio,
    proximo_status,
    objetivo,
    momento,
    df_p,
    papel_usuario,
):
    st.header(f"Ficha de Controle: {gate_id}")
    st.markdown(f"**Objetivo:** {objetivo} | **Momento:** {momento}")
    st.info(f"⚖️ **R:** {responsavel_r} | 🔨 **E:** {executor_e}")

    try:
        status_requerido = (
            "Aguardando Materiais (G1)"
            if gate_id == "GATE 1 (MAT)"
            else "Aguardando Aceite Técnico (G2)"
            if gate_id == "GATE 2 (TEC)"
            else "Aguardando Produção (G3)"
            if gate_id == "GATE 3"
            else "Aguardando Entrega (G4)"
        )

        ctrs_com_itens_pendentes = (
            df_p[df_p["Status_Atual"] == status_requerido]["CTR"].dropna().unique().tolist()
        )
        ctr_lista = [""] + sorted(ctrs_com_itens_pendentes)
        ctr_sel = st.selectbox(f"Selecione a CTR para {gate_id}", ctr_lista, key=f"ctr_gate_{aba}")

        if not ctr_sel:
            return

        itens_pendentes = df_p[
            (df_p["CTR"] == ctr_sel) & (df_p["Status_Atual"] == status_requerido)
        ].sort_values(by="sort_num")

        if itens_pendentes.empty:
            st.info("Não há mais itens pendentes.")
            return

        gestor_ctr = str(itens_pendentes["Dono"].dropna().iloc[0]) if "Dono" in itens_pendentes.columns and not itens_pendentes["Dono"].dropna().empty else "Não definido"
        st.markdown(f"**Gestor da CTR:** {gestor_ctr}")

        selecionados = st.multiselect(
            "Itens disponíveis para validação:",
            options=itens_pendentes["ID_Item"].tolist(),
            format_func=lambda x: f"{itens_pendentes[itens_pendentes['ID_Item'] == x]['Pedido'].iloc[0]}",
            default=itens_pendentes["ID_Item"].tolist(),
            key=f"multi_{aba}",
        )

        if not selecionados:
            return

        pode_assinar = (
            papel_usuario == responsavel_r
            or papel_usuario == executor_e
            or papel_usuario == "Gerência Geral"
        )
        if papel_usuario == "Consulta":
            pode_assinar = False
       
        lock_key = f"gate_lock_{gate_id}_{ctr_sel}"
        if lock_key not in st.session_state:
            st.session_state[lock_key] = 0.0

        with st.form(f"form_batch_{aba}"):
            respostas = {}
            for secao, itens in itens_checklist.items():
                st.markdown(f"#### 🔹 {secao}")
                for item in itens:
                    respostas[item] = st.checkbox(
                        item, key=f"chk_{gate_id}_{aba}_{item.replace(' ', '_')}"
                    )

            obs = st.text_area("Observações Técnicas")
            submitted = st.form_submit_button(
                "VALIDAR LOTE SELECIONADO 🚀", disabled=not pode_assinar
            )

            if not submitted:
                return

            agora_click = time.time()
            if agora_click - st.session_state[lock_key] < 3:
                st.warning("Ação já enviada. Aguarde um instante.")
                return

            st.session_state[lock_key] = agora_click
            
            if not all(respostas.values()):
                st.error(f"❌ BLOQUEIO: {msg_bloqueio}")
                return

            for id_item in selecionados:
                dono_item = itens_pendentes[itens_pendentes["ID_Item"] == id_item]["Dono"].iloc[0]
                item_nome = itens_pendentes[itens_pendentes["ID_Item"] == id_item]["Pedido"].iloc[0]

                log_entry = {
                    "Data": agora_br_str(),
                    "Pedido": item_nome,
                    "Usuario": st.session_state.user_display,
                    "Dono": dono_item,
                    "O que mudou": f"AVANÇO: {gate_id} para {proximo_status}. Obs: {obs}",
                    "Impacto no Prazo": "Não",
                    "Impacto Financeiro": "Não",
                    "CTR": ctr_sel,
                    "tipo_evento": "AVANCO_GATE",
                }
                log_auditoria_supabase(supabase, log_entry)
                
                try:
                    supabase.table("checklists_gates").insert(
                        {
                            "gate": gate_id,
                            "id_item": id_item,
                            "validado_por": st.session_state.user_display,
                            "obs": obs,
                            "respostas": respostas,
                        }
                    ).execute()
                except Exception:
                    pass

            atualizar_status_lote(supabase, selecionados, proximo_status, df_p)
            st.success(f"🚀 {len(selecionados)} itens validados no banco de dados!")
            disparar_foguete()
            time.sleep(1)
            st.rerun()

    except Exception as e:
        st.error(f"Erro na ficha de controle: {e}")

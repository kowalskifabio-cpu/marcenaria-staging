import re
import streamlit as st


def disparar_foguete():
    st.markdown('<div class="rocket-container">🚀</div>', unsafe_allow_html=True)


def extrair_numero_item(texto):
    try:
        nums = re.findall(r"\d+", str(texto))
        return int(nums[0]) if nums else 9999
    except Exception:
        return 9999


def html_status_prazo(dias):
    if dias is None:
        return '<span style="color: grey;">⚪ SEM DATA</span>'
    if dias < 0:
        return '<div class="alerta-pulsante">❌ ATRASO CRÍTICO</div>'
    if dias <= 3:
        return '<div class="alerta-pulsante">🔴 URGENTE</div>'
    return '<div class="no-prazo">🟢 NO PRAZO</div>'

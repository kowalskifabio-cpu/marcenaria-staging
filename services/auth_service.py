import streamlit as st


def login(supabase):
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔐 Acesso Restrito - Gestão de Gates")
        col_l, _ = st.columns(2)

        with col_l:
            user = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")

            if st.button("Entrar"):
                # Login master pelo secrets
                if (
                    user == st.secrets["credentials"]["master_user"]
                    and password == st.secrets["credentials"]["master_password"]
                ):
                    st.session_state.authenticated = True
                    st.session_state.user_role = "MASTER"
                    st.session_state.user_display = "Administrador (Master)"
                    st.session_state.papel_real = "Gerência Geral"
                    st.rerun()

                # Login normal via Supabase
                try:
                    res = (
                        supabase.table("usuarios")
                        .select("*")
                        .eq("usuario", user)
                        .eq("senha", password)
                        .eq("ativo", True)
                        .execute()
                    )

                    data = res.data or []

                    if data:
                        usuario_db = data[0]
                        st.session_state.authenticated = True
                        st.session_state.user_role = "USER"
                        st.session_state.user_display = usuario_db.get("nome") or user
                        st.session_state.papel_real = usuario_db.get("papel") or "Consulta"
                        st.rerun()
                    else:
                        st.error("Usuário ou senha inválidos")

                except Exception as e:
                    st.error(f"Erro ao conectar com usuários no Supabase: {e}")

        return False

    return True

import bcrypt
import streamlit as st
from models import SessionLocal, Usuario, init_db

def hash_password(password):
    """Gera um hash seguro da senha."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    """Verifica se a senha bate com o hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def criar_usuario_inicial():
    """Cria o usuário admin padrão se o banco estiver vazio."""
    db = SessionLocal()
    user = db.query(Usuario).first()
    if not user:
        hashed = hash_password("admin123") 
        novo_user = Usuario(username="admin", password_hash=hashed)
        db.add(novo_user)
        db.commit()
    db.close()

def check_login(username, password):
    """Verifica credenciais no banco."""
    db = SessionLocal()
    user = db.query(Usuario).filter(Usuario.username == username).first()
    db.close()
    
    if user and verify_password(password, user.password_hash):
        return True
    return False

def login_page():
    """Renderiza a tela de login."""
    st.markdown("## ⚖️ JurisFlow - Acesso Restrito")
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        with st.form("login_form"):
            user = st.text_input("Usuário")
            pwd = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
            
            if submitted:
                if check_login(user, pwd):
                    st.session_state.logged_in = True
                    st.session_state.username = user
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")
        return False
    return True

def logout():
    """Realiza logout."""
    st.session_state.logged_in = False
    st.rerun()
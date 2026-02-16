import bcrypt
import streamlit as st
from models import SessionLocal, Usuario, init_db

def hash_password(password):
    """Gera um hash seguro da senha usando bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    """Verifica se a senha fornecida corresponde ao hash salvo."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def criar_usuario_inicial():
    """Cria um usuário 'admin' padrão se o banco de dados estiver vazio."""
    db = SessionLocal()
    user = db.query(Usuario).first()
    if not user:
        # Senha padrão: admin123
        hashed_password = hash_password("admin123") 
        novo_user = Usuario(username="admin", password_hash=hashed_password)
        db.add(novo_user)
        db.commit()
    db.close()

def check_login(username, password):
    """Verifica as credenciais no banco de dados."""
    db = SessionLocal()
    user = db.query(Usuario).filter(Usuario.username == username).first()
    db.close()
    
    if user and verify_password(password, user.password_hash):
        return True
    return False

def login_page():
    """Renderiza a página de login e controla o estado da sessão."""
    st.markdown("## ⚖️ JurisFlow - Acesso Restrito")
    
    # Inicializa o estado de login se não existir
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    # Se não estiver logado, mostra o formulário
    if not st.session_state.logged_in:
        with st.form("login_form"):
            usuario_input = st.text_input("Usuário")
            senha_input = st.text_input("Senha", type="password")
            botao_entrar = st.form_submit_button("Entrar no Sistema")
            
            if botao_entrar:
                if check_login(usuario_input, senha_input):
                    st.session_state.logged_in = True
                    st.session_state.username = usuario_input
                    st.rerun() # Recarrega a página para entrar
                else:
                    st.error("Usuário ou senha incorretos.")
        return False
    
    # Se estiver logado, retorna True para permitir acesso ao app principal
    return True

def logout():
    """Realiza o logout do usuário e recarrega a página."""
    st.session_state.logged_in = False
    st.rerun()
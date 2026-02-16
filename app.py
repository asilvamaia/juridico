import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, func
import base64
import mimetypes
import io

# Importações Locais
import models
from models import Cliente, Processo, Audiencia, DiarioProcessual, Financeiro, Advogado, get_db, init_db, SessionLocal
import auth
import services

# --- Configuração da Página ---
st.set_page_config(
    page_title="JurisFlow",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicialização do Banco e Usuário Admin
init_db()
auth.criar_usuario_inicial()

# --- Funções Auxiliares de UI ---

def format_date_br(dt):
    """Formata data para DD/MM/AAAA"""
    if isinstance(dt, (datetime, date)):
        return dt.strftime("%d/%m/%Y")
    return "-"

def format_moeda(valor):
    """Formata valor float para R$"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def render_file_preview(filepath, filename):
    """Renderiza visualização ou botão de download."""
    try:
        mime_type, _ = mimetypes.guess_type(filepath)
        
        with open(filepath, "rb") as f:
            file_data = f.read()

        st.markdown(f"**Visualizando:** `{filename}`")
        
        with st.container(border=True):
            if mime_type and mime_type.startswith("image"):
                st.image(file_data, caption=filename, use_container_width=True)
            elif mime_type == "application/pdf":
                base64_pdf = base64.b64encode(file_data).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            else:
                st.info(f"O formato do arquivo ({mime_type}) não suporta pré-visualização direta.")

        st.download_button(
            label="⬇️ Baixar Arquivo Original",
            data=file_data,
            file_name=filename,
            mime=mime_type,
            key=f"dl_btn_{filename}"
        )
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")

# --- Telas do Sistema ---

def show_advogados(db: Session):
    st.header("⚖️ Cadastro de Advogados (Banca)")
    st.info("Cadastre aqui os advogados que aparecerão nas procurações.")
    
    tab1, tab2 = st.tabs(["Listar", "Novo Advogado"])
    
    with tab2:
        with st.form("new_adv"):
            nome = st.text_input("Nome Completo")
            oab = st.text_input("OAB (Ex: OAB/SP 123.456)")
            nac = st.text_input("Nacionalidade", value="brasileiro(a)")
            ec = st.text_input("Estado Civil", value="casado(a)")
            end = st.text_area("Endereço Profissional")
            
            if st.form_submit_button("Salvar Advogado"):
                if nome and oab:
                    adv = Advogado(nome=nome, oab=oab, nacionalidade=nac, estado_civil=ec, endereco=end)
                    db.add(adv)
                    db.commit()
                    st.success("Advogado cadastrado!")
                    st.rerun()
                else:
                    st.error("Nome e OAB são obrigatórios.")

    with tab1:
        advs = db.query(Advogado).all()
        if advs:
            for a in advs:
                with st.expander(f"🎓 {a.nome} - {a.oab}"):
                    st.write(f"**Endereço:** {a.endereco}")
                    if st.button("Excluir Advogado", key=f"del_adv_{a.id}"):
                        db.delete(a)
                        db.commit()
                        st.success("Removido com sucesso.")
                        st.rerun()
        else:
            st.info("Nenhum advogado cadastrado.")

def show_calculadora_prazos():
    st.header("📆 Calculadora de Prazos Processuais")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        dt_pub = c1.date_input("Data da Publicação/Intimação", value=date.today(), format="DD/MM/YYYY")
        dias = c2.number_input("Prazo em Dias Úteis", min_value=1, value=15)
        
        if st.button("Calcular Vencimento"):
            resultado = services.calcular_prazo_util(dt_pub, dias)
            st.markdown("---")
            c_res1, c_res2 = st.columns(2)
            c_res1.success(f"📅 Data Fatal: **{resultado.strftime('%d/%m/%Y')}**")
            c_res1.caption(f"Dia da semana: {resultado.strftime('%A')}")
            c_res2.info("⚠️ Nota: O sistema considera feriados nacionais.")

def show_dashboard(db: Session):
    st.header("📊 Dashboard Geral")
    
    col1, col2, col3, col4 = st.columns(4)
    total_clientes = db.query(Cliente).count()
    total_processos = db.query(Processo).filter(Processo.status == "Em andamento").count()
    receitas = db.query(func.sum(Financeiro.valor)).filter(Financeiro.tipo == "Honorário", Financeiro.status == "Pago").scalar() or 0
    a_receber = db.query(func.sum(Financeiro.valor)).filter(Financeiro.tipo == "Honorário", Financeiro.status == "Pendente").scalar() or 0
    
    col1.metric("Clientes Ativos", total_clientes)
    col2.metric("Processos em Andamento", total_processos)
    col3.metric("Honorários Recebidos", format_moeda(receitas))
    col4.metric("A Receber", format_moeda(a_receber))

    st.markdown("---")
    st.subheader("🔔 Próximos Compromissos")
    prox_eventos = db.query(Audiencia).filter(Audiencia.concluido == 0).order_by(Audiencia.data_hora).limit(5).all()
    
    if prox_eventos:
        data = []
        for evt in prox_eventos:
            proc = db.query(Processo).get(evt.processo_id)
            cliente_nome = proc.cliente.nome if proc and proc.cliente else "N/A"
            data.append([evt.data_hora.strftime("%d/%m/%Y %H:%M"), evt.tipo, cliente_nome, evt.titulo])
        st.table(pd.DataFrame(data, columns=["Data", "Tipo", "Cliente", "Título"]))
    else:
        st.info("Nenhum compromisso pendente.")

def show_clientes(db: Session):
    st.header("📁 Gestão de Clientes")
    tab1, tab2 = st.tabs(["Listar/Buscar", "Novo Cliente"])
    
    with tab1:
        search = st.text_input("Buscar por Nome ou CPF/CNPJ", "")
        query = db.query(Cliente)
        if search:
            query = query.filter(or_(Cliente.nome.ilike(f"%{search}%"), Cliente.cpf_cnpj.ilike(f"%{search}%")))
        clientes = query.all()
        advogados = db.query(Advogado).all()
        
        if clientes:
            for cli in clientes:
                with st.expander(f"👤 {cli.nome} - {cli.cpf_cnpj}"):
                    # Visualização
                    c1, c2 = st.columns(2)
                    c1.write(f"**Email:** {cli.email}")
                    c2.write(f"**Telefone:** {cli.telefone}")
                    st.write(f"**Endereço:** {cli.endereco}")
                    
                    st.markdown("---")
                    
                    # --- GERADOR DE PROCURAÇÃO ---
                    st.markdown("##### 📄 Geração de Documentos")
                    if not advogados:
                        st.warning("⚠️ Cadastre um advogado na aba 'Advogados' para habilitar a procuração.")
                    else:
                        c_doc1, c_doc2 = st.columns([0.7, 0.3])
                        with c_doc1:
                            adv_opts = {f"{a.nome} ({a.oab})": a.id for a in advogados}
                            sel_adv = st.selectbox("Advogado Responsável", list(adv_opts.keys()), key=f"sel_adv_{cli.id}")
                            
                            if st.button("Gerar Procuração (Word)", key=f"btn_doc_{cli.id}"):
                                adv_obj = db.query(Advogado).get(adv_opts[sel_adv])
                                docx_file = services.gerar_procuracao(cli, adv_obj)
                                if docx_file:
                                    st.download_button(
                                        label="⬇️ Baixar DOCX",
                                        data=docx_file,
                                        file_name=f"Procuracao_{cli.nome}.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                        key=f"dl_doc_{cli.id}"
                                    )
                                else:
                                    st.error("Template não encontrado na pasta 'templates'.")
                    
                    st.markdown("---")
                    if st.button("🗑️ Excluir Cliente", key=f"del_cli_{cli.id}"):
                        db.delete(cli)
                        db.commit()
                        st.success("Cliente excluído!")
                        st.rerun()

        else:
            st.info("Nenhum cliente encontrado.")

    with tab2:
        with st.form("form_cliente"):
            nome = st.text_input("Nome Completo")
            cpf = st.text_input("CPF/CNPJ")
            tel = st.text_input("Telefone")
            email = st.text_input("E-mail")
            end = st.text_area("Endereço")
            obs = st.text_area("Observações")
            submit = st.form_submit_button("Cadastrar Cliente")
            
            if submit and nome:
                novo = Cliente(nome=nome, cpf_cnpj=cpf, telefone=tel, email=email, endereco=end, observacoes=obs)
                db.add(novo)
                db.commit()
                services.criar_estrutura_cliente(nome, novo.id)
                st.success(f"Cliente {nome} cadastrado!")
                st.rerun()

def show_processos(db: Session):
    st.header("⚖️ Controle de Processos")
    tab1, tab2 = st.tabs(["Meus Processos", "Novo Processo"])
    
    clientes_list = db.query(Cliente).all()
    if not clientes_list:
        st.warning("Cadastre clientes antes de criar processos.")
        return
    cli_dict = {f"{c.nome} ({c.cpf_cnpj})": c.id for c in clientes_list}

    # NOVO PROCESSO
    with tab2:
        with st.form("form_processo"):
            cli_sel = st.selectbox("Selecione o Cliente", list(cli_dict.keys()))
            num_proc = st.text_input("Número do Processo")
            tribunal = st.text_input("Vara / Tribunal")
            status = st.selectbox("Status", ["Em andamento", "Suspenso", "Sentenciado", "Arquivado"])
            dt_inicio = st.date_input("Data de Início", value=date.today(), format="DD/MM/YYYY")
            
            if st.form_submit_button("Salvar Processo") and num_proc:
                cli_id = cli_dict[cli_sel]
                novo_proc = Processo(
                    cliente_id=cli_id, numero_processo=num_proc, tribunal=tribunal,
                    status=status, data_inicio=dt_inicio
                )
                db.add(novo_proc)
                db.commit()
                services.criar_estrutura_processo(db.query(Cliente).get(cli_id).nome, cli_id, num_proc)
                st.success("Processo criado!")
                st.rerun()

    # LISTA
    with tab1:
        procs = db.query(Processo).join(Cliente).all()
        for p in procs:
            with st.expander(f"{p.numero_processo} - {p.cliente.nome} ({p.status})"):
                
                t1, t2, t3, t4 = st.tabs(["📂 Arquivos (IA)", "📝 Diário", "💰 Financeiro", "⚙️ Editar"])
                
                # --- ABA ARQUIVOS (IA GEMMA 3) ---
                with t1:
                    uploaded = st.file_uploader("Upload", key=f"up_{p.id}", accept_multiple_files=True)
                    if uploaded:
                        for f in uploaded:
                            services.salvar_arquivo(f, p.cliente.nome, p.cliente.id, p.numero_processo)
                        st.rerun()
                    
                    files = services.listar_arquivos(p.cliente.nome, p.cliente.id, p.numero_processo)
                    for f in files:
                        c1, c2 = st.columns([0.7, 0.3])
                        c1.text(f"📄 {f}")
                        
                        # Botão IA
                        if f.lower().endswith(".pdf"):
                            if c2.button("✨ Resumir (Gemma 3)", key=f"ai_{p.id}_{f}"):
                                with st.spinner("Analisando PDF..."):
                                    full_path = services.get_caminho_arquivo(p.cliente.nome, p.cliente.id, p.numero_processo, f)
                                    texto = services.extrair_texto_pdf(full_path)
                                    # Usa chave da sessão
                                    resumo = services.resumir_com_google(texto, st.session_state.get("google_key"))
                                    st.session_state[f"res_{p.id}_{f}"] = resumo
                        
                        # Mostra Resumo
                        if f"res_{p.id}_{f}" in st.session_state:
                            st.info(st.session_state[f"res_{p.id}_{f}"])
                        
                        # Botão Ver
                        if c2.button("Ver", key=f"v_{p.id}_{f}"):
                            path = services.get_caminho_arquivo(p.cliente.nome, p.cliente.id, p.numero_processo, f)
                            render_file_preview(path, f)

                # --- ABA DIÁRIO ---
                with t2:
                    novo_diario = st.text_input("Nova nota", key=f"nt_{p.id}")
                    if st.button("Adicionar", key=f"btn_nt_{p.id}"):
                        db.add(DiarioProcessual(processo_id=p.id, texto=novo_diario))
                        db.commit()
                        st.rerun()
                    for n in db.query(DiarioProcessual).filter(DiarioProcessual.processo_id == p.id).order_by(desc(DiarioProcessual.data_registro)):
                        st.text(f"{n.data_registro.strftime('%d/%m %H:%M')} - {n.texto}")

                # --- ABA FINANCEIRO ---
                with t3:
                    with st.form(f"fin_{p.id}"):
                        c1, c2, c3 = st.columns(3)
                        desc_fin = c1.text_input("Descrição")
                        valor_fin = c2.number_input("Valor", min_value=0.0)
                        tipo = c3.selectbox("Tipo", ["Honorário", "Despesa"])
                        if st.form_submit_button("Lançar"):
                            db.add(Financeiro(processo_id=p.id, descricao=desc_fin, valor=valor_fin, tipo=tipo))
                            db.commit()
                            st.rerun()
                    
                    fins = db.query(Financeiro).filter(Financeiro.processo_id == p.id).all()
                    for f in fins:
                        st.write(f"{f.descricao}: {format_moeda(f.valor)} ({f.tipo} - {f.status})")

                # --- ABA EDITAR ---
                with t4:
                    with st.form(f"ed_{p.id}"):
                        ns = st.selectbox("Status", ["Em andamento", "Arquivado"], key=f"st_{p.id}")
                        if st.form_submit_button("Atualizar"):
                            p.status = ns
                            db.commit()
                            st.rerun()

def show_agenda(db: Session):
    st.header("📅 Agenda")
    c1, c2 = st.columns([1, 2])
    
    with c1:
        procs = db.query(Processo).all()
        if procs:
            opts = {p.numero_processo: p.id for p in procs}
            with st.form("new_evt"):
                pk = st.selectbox("Processo", list(opts.keys()))
                tit = st.text_input("Título")
                dt = st.date_input("Data")
                if st.form_submit_button("Agendar"):
                    db.add(Audiencia(processo_id=opts[pk], titulo=tit, data_hora=datetime.combine(dt, datetime.min.time())))
                    db.commit()
                    st.success("Agendado!")
                    st.rerun()
    
    with c2:
        evts = db.query(Audiencia).filter(Audiencia.concluido == 0).order_by(Audiencia.data_hora).all()
        for e in evts:
            st.write(f"📅 {e.data_hora.strftime('%d/%m/%Y')} - {e.titulo}")

def show_relatorios(db: Session):
    st.header("💾 Backup")
    if st.button("Gerar Backup Completo"):
        zip_path = services.criar_backup()
        with open(zip_path, "rb") as f:
            st.download_button("Baixar ZIP", f, "backup_jurisflow.zip")

def main():
    if not auth.login_page(): return
    
    st.sidebar.title(f"Olá, {st.session_state.username}")
    
    # --- GESTÃO DE CHAVES (SECRETS) ---
    api_key = None
    try:
        # Tenta ler do Secrets (Nuvem ou Arquivo Local)
        if "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
    except (FileNotFoundError, KeyError):
        # Se não encontrar arquivo ou chave, ignora e segue
        pass
    except Exception:
        pass
    
    # Se achou no Secrets, usa ela.
    if api_key:
        st.session_state["google_key"] = api_key
    # Se NÃO achou, pede na tela.
    else:
        st.sidebar.markdown("### 🤖 Configuração IA")
        k = st.sidebar.text_input("API Key (Google)", type="password", help="Chave necessária para usar o Gemma 3")
        if k:
            st.session_state["google_key"] = k
    # ----------------------------------

    menu = st.sidebar.radio("Menu", ["Dashboard", "Clientes", "Advogados", "Processos", "Agenda", "Calculadora", "Relatórios"])
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair"): auth.logout()

    db = SessionLocal()
    try:
        if menu == "Dashboard": show_dashboard(db)
        elif menu == "Clientes": show_clientes(db)
        elif menu == "Advogados": show_advogados(db)
        elif menu == "Processos": show_processos(db)
        elif menu == "Agenda": show_agenda(db)
        elif menu == "Calculadora": show_calculadora_prazos()
        elif menu == "Relatórios": show_relatorios(db)
    finally:
        db.close()

if __name__ == "__main__":
    main()
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, func
import base64
import mimetypes

# Importações Locais
import models
from models import Cliente, Processo, Audiencia, DiarioProcessual, get_db, init_db, SessionLocal
import auth
import services

# Configuração da Página
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
    return ""

def render_file_preview(filepath, filename):
    """Renderiza visualização ou botão de download baseado no tipo do arquivo."""
    try:
        mime_type, _ = mimetypes.guess_type(filepath)
        
        # Leitura do arquivo
        with open(filepath, "rb") as f:
            file_data = f.read()

        col_a, col_b = st.columns([1, 4])
        
        with col_a:
             # Botão de Download Universal (Funciona para todos)
            st.download_button(
                label="⬇️ Baixar",
                data=file_data,
                file_name=filename,
                mime=mime_type,
                key=f"btn_dl_{filename}"
            )

        with col_b:
            # Lógica de Visualização
            if mime_type:
                if mime_type.startswith("image"):
                    st.image(file_data, caption=filename, use_container_width=True)
                
                elif mime_type == "application/pdf":
                    # Embed PDF
                    base64_pdf = base64.b64encode(file_data).decode('utf-8')
                    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf"></iframe>'
                    st.markdown(pdf_display, unsafe_allow_html=True)
                
                elif mime_type in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"]:
                    st.info(f"Visualização direta não suportada para Excel. Clique em Baixar.")
                
                else:
                    st.info(f"Arquivo {filename} disponível para download.")
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")

def show_dashboard(db: Session):
    st.header("📊 Dashboard Geral")
    
    col1, col2, col3, col4 = st.columns(4)
    
    total_clientes = db.query(Cliente).count()
    total_processos = db.query(Processo).filter(Processo.status == "Em andamento").count()
    
    hoje = datetime.now()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)
    
    audiencias_semana = db.query(Audiencia).filter(
        Audiencia.data_hora >= inicio_semana,
        Audiencia.data_hora <= fim_semana,
        Audiencia.concluido == 0
    ).count()

    prazos_prox = db.query(Audiencia).filter(
        Audiencia.tipo == "Prazo",
        Audiencia.concluido == 0,
        Audiencia.data_hora <= hoje + timedelta(days=3)
    ).count()

    col1.metric("Clientes Cadastrados", total_clientes)
    col2.metric("Processos Ativos", total_processos)
    col3.metric("Eventos na Semana", audiencias_semana)
    col4.metric("Prazos Críticos (3 dias)", prazos_prox, delta_color="inverse")

    st.subheader("🔔 Próximos Compromissos")
    prox_eventos = db.query(Audiencia).filter(Audiencia.concluido == 0).order_by(Audiencia.data_hora).limit(5).all()
    
    if prox_eventos:
        data = []
        for evt in prox_eventos:
            proc = db.query(Processo).get(evt.processo_id)
            cliente = proc.cliente.nome if proc else "N/A"
            data.append([evt.data_hora.strftime("%d/%m/%Y %H:%M"), evt.tipo, cliente, evt.titulo])
        
        df = pd.DataFrame(data, columns=["Data", "Tipo", "Cliente", "Título"])
        st.table(df)
    else:
        st.info("Nenhum compromisso pendente.")

def show_clientes(db: Session):
    st.header("📁 Gestão de Clientes")
    
    tab1, tab2 = st.tabs(["Listar/Buscar/Editar", "Novo Cliente"])
    
    with tab1:
        search = st.text_input("Buscar por Nome ou CPF/CNPJ", "")
        query = db.query(Cliente)
        if search:
            query = query.filter(or_(Cliente.nome.ilike(f"%{search}%"), Cliente.cpf_cnpj.ilike(f"%{search}%")))
        
        clientes = query.all()
        
        if clientes:
            for cli in clientes:
                with st.expander(f"👤 {cli.nome} - {cli.cpf_cnpj}"):
                    # Controle de Estado para Edição
                    edit_mode = st.toggle("✏️ Editar Dados", key=f"toggle_edit_{cli.id}")
                    
                    if not edit_mode:
                        # Modo Visualização
                        c1, c2 = st.columns(2)
                        c1.write(f"**Email:** {cli.email}")
                        c1.write(f"**Telefone:** {cli.telefone}")
                        c2.write(f"**Endereço:** {cli.endereco}")
                        st.write(f"**Observações:** {cli.observacoes}")
                        st.caption(f"Cadastrado em: {format_date_br(cli.data_cadastro)}")
                        
                        if st.button("🗑️ Excluir Cliente", key=f"del_cli_{cli.id}"):
                            db.delete(cli)
                            db.commit()
                            st.success("Cliente excluído!")
                            st.rerun()
                    else:
                        # Modo Edição
                        with st.form(key=f"form_edit_cli_{cli.id}"):
                            ed_nome = st.text_input("Nome", value=cli.nome)
                            ed_cpf = st.text_input("CPF/CNPJ", value=cli.cpf_cnpj)
                            ed_tel = st.text_input("Telefone", value=cli.telefone)
                            ed_email = st.text_input("E-mail", value=cli.email)
                            ed_end = st.text_area("Endereço", value=cli.endereco)
                            ed_obs = st.text_area("Observações", value=cli.observacoes)
                            
                            if st.form_submit_button("💾 Salvar Alterações"):
                                cli.nome = ed_nome
                                cli.cpf_cnpj = ed_cpf
                                cli.telefone = ed_tel
                                cli.email = ed_email
                                cli.endereco = ed_end
                                cli.observacoes = ed_obs
                                db.commit()
                                st.success("Dados atualizados com sucesso!")
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
            
            if submit and nome and cpf:
                novo = Cliente(nome=nome, cpf_cnpj=cpf, telefone=tel, email=email, endereco=end, observacoes=obs)
                try:
                    db.add(novo)
                    db.commit()
                    services.criar_estrutura_cliente(nome, novo.id)
                    st.success(f"Cliente {nome} cadastrado com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")

def show_processos(db: Session):
    st.header("⚖️ Controle de Processos")
    
    tab1, tab2 = st.tabs(["Meus Processos", "Novo Processo"])
    
    clientes_list = db.query(Cliente).all()
    if not clientes_list:
        st.warning("Cadastre clientes antes de criar processos.")
        return

    cli_dict = {f"{c.nome} ({c.cpf_cnpj})": c.id for c in clientes_list}

    # Novo Processo
    with tab2:
        with st.form("form_processo"):
            cli_sel = st.selectbox("Selecione o Cliente", list(cli_dict.keys()))
            num_proc = st.text_input("Número do Processo")
            tribunal = st.text_input("Vara / Tribunal")
            tipo = st.selectbox("Tipo de Ação", ["Cível", "Trabalhista", "Criminal", "Família", "Tributário", "Outros"])
            parte = st.text_input("Parte Contrária")
            status = st.selectbox("Status", ["Em andamento", "Suspenso", "Sentenciado", "Arquivado", "Recurso"])
            # Formato Data DD/MM/AAAA
            dt_inicio = st.date_input("Data de Início", value=date.today(), format="DD/MM/YYYY")
            obs = st.text_area("Observações")
            estrategia = st.text_area("🧠 Estratégia (Privado)", help="Visível apenas aqui")
            
            submit = st.form_submit_button("Salvar Processo")
            
            if submit and num_proc:
                cli_id = cli_dict[cli_sel]
                novo_proc = Processo(
                    cliente_id=cli_id, numero_processo=num_proc, tribunal=tribunal,
                    tipo_acao=tipo, parte_contraria=parte, status=status,
                    data_inicio=dt_inicio, observacoes=obs, estrategia=estrategia
                )
                try:
                    db.add(novo_proc)
                    db.commit()
                    cli_obj = db.query(Cliente).get(cli_id)
                    services.criar_estrutura_processo(cli_obj.nome, cli_id, num_proc)
                    st.success("Processo criado com sucesso!")
                except Exception as e:
                    st.error(f"Erro: {e}")

    # Lista e Edição
    with tab1:
        procs = db.query(Processo).join(Cliente).all()
        for p in procs:
            with st.expander(f"{p.numero_processo} - {p.cliente.nome} ({p.status})"):
                
                # Edição do Processo
                edit_proc_mode = st.toggle("✏️ Editar Processo", key=f"edit_proc_tg_{p.id}")
                
                if edit_proc_mode:
                    with st.form(key=f"form_edit_proc_{p.id}"):
                        ed_num = st.text_input("Número", value=p.numero_processo)
                        ed_trib = st.text_input("Tribunal", value=p.tribunal)
                        ed_tipo = st.selectbox("Tipo", ["Cível", "Trabalhista", "Criminal", "Família", "Tributário", "Outros"], index=["Cível", "Trabalhista", "Criminal", "Família", "Tributário", "Outros"].index(p.tipo_acao) if p.tipo_acao in ["Cível", "Trabalhista", "Criminal", "Família", "Tributário", "Outros"] else 0)
                        ed_parte = st.text_input("Parte Contrária", value=p.parte_contraria)
                        ed_status = st.selectbox("Status", ["Em andamento", "Suspenso", "Sentenciado", "Arquivado", "Recurso"], index=["Em andamento", "Suspenso", "Sentenciado", "Arquivado", "Recurso"].index(p.status) if p.status in ["Em andamento", "Suspenso", "Sentenciado", "Arquivado", "Recurso"] else 0)
                        ed_dt = st.date_input("Data Início", value=p.data_inicio, format="DD/MM/YYYY")
                        ed_obs = st.text_area("Observações", value=p.observacoes)
                        ed_est = st.text_area("Estratégia", value=p.estrategia)
                        
                        if st.form_submit_button("💾 Atualizar Processo"):
                            p.numero_processo = ed_num
                            p.tribunal = ed_trib
                            p.tipo_acao = ed_tipo
                            p.parte_contraria = ed_parte
                            p.status = ed_status
                            p.data_inicio = ed_dt
                            p.observacoes = ed_obs
                            p.estrategia = ed_est
                            db.commit()
                            st.success("Processo atualizado!")
                            st.rerun()
                else:
                    # Visualização
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Tribunal:** {p.tribunal}")
                    c1.write(f"**Ação:** {p.tipo_acao}")
                    c2.write(f"**Contra:** {p.parte_contraria}")
                    c2.write(f"**Data:** {format_date_br(p.data_inicio)}")
                    c3.info(f"Status: {p.status}")
                    
                    st.markdown("---")
                    st.write(f"**Obs:** {p.observacoes}")
                    if st.checkbox("Ver Estratégia", key=f"view_est_{p.id}"):
                        st.warning(f"🔒 **Estratégia:** {p.estrategia}")

                    # Sub-abas
                    t_sub1, t_sub2 = st.tabs(["📂 Arquivos", "📝 Diário"])
                    
                    # Uploads e Visualização
                    with t_sub1:
                        uploaded = st.file_uploader("Anexar documento", key=f"up_{p.id}", accept_multiple_files=True)
                        if uploaded:
                            for f in uploaded:
                                services.salvar_arquivo(f, p.cliente.nome, p.cliente.id, p.numero_processo)
                            st.success("Arquivos salvos!")
                            st.rerun()
                        
                        st.markdown("##### Arquivos Anexados:")
                        files = services.listar_arquivos(p.cliente.nome, p.cliente.id, p.numero_processo)
                        
                        if files:
                            for f in files:
                                with st.container(border=True):
                                    st.markdown(f"**📄 {f}**")
                                    # Botões de ação para o arquivo
                                    ca, cb = st.columns([0.1, 0.9])
                                    with ca:
                                        if st.button("❌", key=f"del_{p.id}_{f}", help="Excluir arquivo"):
                                            services.excluir_arquivo(p.cliente.nome, p.cliente.id, p.numero_processo, f)
                                            st.rerun()
                                    with cb:
                                        if st.button("👁️ Visualizar / Baixar", key=f"view_{p.id}_{f}"):
                                            # Ao clicar, abre a visualização
                                            full_path = services.get_caminho_arquivo(p.cliente.nome, p.cliente.id, p.numero_processo, f)
                                            render_file_preview(full_path, f)
                        else:
                            st.caption("Nenhum arquivo anexado.")

                    # Diário
                    with t_sub2:
                        novo_diario = st.text_input("Nova nota", key=f"note_{p.id}")
                        if st.button("Adicionar Nota", key=f"btn_note_{p.id}"):
                            nota = DiarioProcessual(processo_id=p.id, texto=novo_diario)
                            db.add(nota)
                            db.commit()
                            st.rerun()
                        
                        notas = db.query(DiarioProcessual).filter(DiarioProcessual.processo_id == p.id).order_by(desc(DiarioProcessual.data_registro)).all()
                        for n in notas:
                            st.text(f"{n.data_registro.strftime('%d/%m/%Y %H:%M')} - {n.texto}")

def show_agenda(db: Session):
    st.header("📅 Agenda Jurídica")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Novo Evento")
        procs = db.query(Processo).all()
        proc_options = {f"{p.numero_processo} - {p.cliente.nome}": p.id for p in procs}
        
        with st.form("form_agenda"):
            sel_proc_key = st.selectbox("Processo", list(proc_options.keys()))
            titulo = st.text_input("Título (ex: Audiência de Instrução)")
            dt = st.date_input("Data", format="DD/MM/YYYY")
            hr = st.time_input("Hora")
            tipo = st.selectbox("Tipo", ["Audiência", "Prazo", "Reunião", "Outro"])
            obs = st.text_area("Detalhes")
            
            if st.form_submit_button("Agendar"):
                dt_full = datetime.combine(dt, hr)
                evt = Audiencia(processo_id=proc_options[sel_proc_key], titulo=titulo, data_hora=dt_full, tipo=tipo, observacoes=obs)
                db.add(evt)
                db.commit()
                st.success("Agendado!")

    with col2:
        st.subheader("Compromissos")
        filtro = st.selectbox("Filtrar", ["Todos", "Pendentes", "Concluídos"])
        
        query = db.query(Audiencia).order_by(Audiencia.data_hora)
        if filtro == "Pendentes":
            query = query.filter(Audiencia.concluido == 0)
        elif filtro == "Concluídos":
            query = query.filter(Audiencia.concluido == 1)
            
        eventos = query.all()
        
        df_data = []
        for e in eventos:
            proc = db.query(Processo).get(e.processo_id)
            status_icon = "✅" if e.concluido else "⏳"
            df_data.append({
                "Data": e.data_hora.strftime("%d/%m/%Y %H:%M"),
                "Evento": e.titulo,
                "Tipo": e.tipo,
                "Processo": proc.numero_processo,
                "Status": status_icon,
                "ID": e.id,
                "Concluido": e.concluido
            })
            
        if df_data:
            st.dataframe(pd.DataFrame(df_data).drop(columns=["ID", "Concluido"]), use_container_width=True)
            
            st.write("---")
            st.caption("Ações rápidas sobre eventos:")
            sel_evt = st.selectbox("Selecione um evento para alterar", [f"{d['Data']} - {d['Evento']}" for d in df_data])
            if st.button("Marcar como Concluído/Pendente"):
                idx = [f"{d['Data']} - {d['Evento']}" for d in df_data].index(sel_evt)
                evt_id = df_data[idx]['ID']
                evt_obj = db.query(Audiencia).get(evt_id)
                evt_obj.concluido = 1 if evt_obj.concluido == 0 else 0
                db.commit()
                st.rerun()

def show_relatorios(db: Session):
    st.header("📊 Relatórios e Backups")
    
    st.subheader("1. Exportar Dados")
    if st.button("Gerar Relatório de Clientes (CSV)"):
        clientes = db.query(Cliente).all()
        data = [{"Nome": c.nome, "CPF": c.cpf_cnpj, "Email": c.email, "Cadastro": format_date_br(c.data_cadastro)} for c in clientes]
        df = pd.DataFrame(data)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Baixar CSV", csv, "clientes.csv", "text/csv")

    st.markdown("---")
    st.subheader("2. Backup do Sistema")
    if st.button("Gerar Backup Completo (.zip)"):
        with st.spinner("Compactando arquivos e banco de dados..."):
            zip_path = services.criar_backup()
            with open(zip_path, "rb") as f:
                st.download_button("Baixar Backup", f, file_name=str(zip_path).split('\\')[-1])

# --- Main Flow ---

def main():
    if not auth.login_page():
        return

    st.sidebar.title(f"Olá, {st.session_state.username}")
    menu = st.sidebar.radio(
        "Menu",
        ["Dashboard", "Clientes", "Processos", "Agenda", "Relatórios"],
        index=0
    )
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair"):
        auth.logout()

    db = SessionLocal()
    
    try:
        if menu == "Dashboard":
            show_dashboard(db)
        elif menu == "Clientes":
            show_clientes(db)
        elif menu == "Processos":
            show_processos(db)
        elif menu == "Agenda":
            show_agenda(db)
        elif menu == "Relatórios":
            show_relatorios(db)
    finally:
        db.close()

if __name__ == "__main__":
    main()
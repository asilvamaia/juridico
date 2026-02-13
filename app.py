import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, func

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

# --- Funções de UI Auxiliares ---

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
    
    tab1, tab2 = st.tabs(["Listar/Buscar", "Novo Cliente"])
    
    with tab1:
        search = st.text_input("Buscar por Nome ou CPF/CNPJ", "")
        query = db.query(Cliente)
        if search:
            query = query.filter(or_(Cliente.nome.ilike(f"%{search}%"), Cliente.cpf_cnpj.ilike(f"%{search}%")))
        
        clientes = query.all()
        
        if clientes:
            for cli in clientes:
                with st.expander(f"👤 {cli.nome} - {cli.cpf_cnpj}"):
                    c1, c2 = st.columns(2)
                    c1.write(f"**Email:** {cli.email}")
                    c1.write(f"**Telefone:** {cli.telefone}")
                    c2.write(f"**Endereço:** {cli.endereco}")
                    st.write(f"**Observações:** {cli.observacoes}")
                    
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
            
            if submit and nome and cpf:
                novo = Cliente(nome=nome, cpf_cnpj=cpf, telefone=tel, email=email, endereco=end, observacoes=obs)
                try:
                    db.add(novo)
                    db.commit()
                    # Criar pasta física
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

    with tab2:
        with st.form("form_processo"):
            cli_sel = st.selectbox("Selecione o Cliente", list(cli_dict.keys()))
            num_proc = st.text_input("Número do Processo")
            tribunal = st.text_input("Vara / Tribunal")
            tipo = st.selectbox("Tipo de Ação", ["Cível", "Trabalhista", "Criminal", "Família", "Tributário", "Outros"])
            parte = st.text_input("Parte Contrária")
            status = st.selectbox("Status", ["Em andamento", "Suspenso", "Sentenciado", "Arquivado", "Recurso"])
            dt_inicio = st.date_input("Data de Início", value=date.today())
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
                    # Criar pasta física
                    cli_obj = db.query(Cliente).get(cli_id)
                    services.criar_estrutura_processo(cli_obj.nome, cli_id, num_proc)
                    st.success("Processo criado com sucesso!")
                except Exception as e:
                    st.error(f"Erro: {e}")

    with tab1:
        procs = db.query(Processo).join(Cliente).all()
        for p in procs:
            with st.expander(f"{p.numero_processo} - {p.cliente.nome} ({p.status})"):
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Tribunal:** {p.tribunal}")
                c1.write(f"**Ação:** {p.tipo_acao}")
                c2.write(f"**Contra:** {p.parte_contraria}")
                c2.write(f"**Data:** {p.data_inicio}")
                c3.info(f"Status: {p.status}")
                
                st.markdown("---")
                st.write(f"**Obs:** {p.observacoes}")
                if st.checkbox("Ver Estratégia", key=f"view_est_{p.id}"):
                    st.warning(f"🔒 **Estratégia:** {p.estrategia}")

                # --- Módulos Internos do Processo ---
                t_sub1, t_sub2, t_sub3 = st.tabs(["📂 Arquivos", "📝 Diário", "⚙️ Editar Status"])
                
                # Uploads
                with t_sub1:
                    uploaded = st.file_uploader("Anexar documento", key=f"up_{p.id}", accept_multiple_files=True)
                    if uploaded:
                        for f in uploaded:
                            services.salvar_arquivo(f, p.cliente.nome, p.cliente.id, p.numero_processo)
                        st.success("Arquivos salvos!")
                    
                    st.markdown("##### Arquivos Anexados:")
                    files = services.listar_arquivos(p.cliente.nome, p.cliente.id, p.numero_processo)
                    for f in files:
                        col_f1, col_f2 = st.columns([0.8, 0.2])
                        col_f1.text(f"📄 {f}")
                        if col_f2.button("❌", key=f"del_{p.id}_{f}"):
                            services.excluir_arquivo(p.cliente.nome, p.cliente.id, p.numero_processo, f)
                            st.rerun()

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

                with t_sub3:
                    new_status = st.selectbox("Atualizar Status", ["Em andamento", "Suspenso", "Sentenciado", "Arquivado"], key=f"st_{p.id}", index=0)
                    if st.button("Atualizar", key=f"up_st_{p.id}"):
                        p.status = new_status
                        db.commit()
                        st.success("Status atualizado!")
                        st.rerun()

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
            dt = st.date_input("Data")
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
        
        # Agrupar por data para visualização tipo calendário
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
            
            # Ações rápidas
            st.write("---")
            st.caption("Ações rápidas sobre eventos:")
            sel_evt = st.selectbox("Selecione um evento para alterar", [f"{d['Data']} - {d['Evento']}" for d in df_data])
            if st.button("Marcar como Concluído/Pendente"):
                # Lógica simples para pegar o ID baseado na string selecionada
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
        data = [{"Nome": c.nome, "CPF": c.cpf_cnpj, "Email": c.email} for c in clientes]
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

    # Sidebar Navigation
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
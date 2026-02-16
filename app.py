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
from models import Cliente, Processo, Audiencia, DiarioProcessual, Financeiro, get_db, init_db, SessionLocal
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
    """Formata data (datetime ou date) para DD/MM/AAAA"""
    if isinstance(dt, (datetime, date)):
        return dt.strftime("%d/%m/%Y")
    return "-"

def format_moeda(valor):
    """Formata valor float para R$"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def render_file_preview(filepath, filename):
    """Renderiza visualização ou botão de download baseado no tipo do arquivo."""
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

def show_calculadora_prazos():
    st.header("📆 Calculadora de Prazos Processuais")
    st.caption("Calcula dias úteis considerando feriados nacionais (Brasil).")
    
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
            c_res2.info("⚠️ Nota: O sistema considera feriados nacionais. Verifique feriados locais/municipais manualmente.")

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
    col4.metric("A Receber", format_moeda(a_receber), delta_color="normal")

    st.markdown("---")
    
    st.subheader("🔔 Próximos Compromissos")
    prox_eventos = db.query(Audiencia).filter(Audiencia.concluido == 0).order_by(Audiencia.data_hora).limit(5).all()
    
    if prox_eventos:
        data = []
        for evt in prox_eventos:
            proc = db.query(Processo).get(evt.processo_id)
            cliente_nome = proc.cliente.nome if proc and proc.cliente else "N/A"
            data.append([evt.data_hora.strftime("%d/%m/%Y %H:%M"), evt.tipo, cliente_nome, evt.titulo])
        
        df = pd.DataFrame(data, columns=["Data", "Tipo", "Cliente", "Título"])
        st.table(df)
    else:
        st.info("Nenhum compromisso pendente.")

def show_clientes(db: Session):
    st.header("📁 Gestão de Clientes")
    tab1, tab2 = st.tabs(["Listar/Buscar/Editar", "Novo Cliente"])
    
    # LISTAR E EDITAR
    with tab1:
        search = st.text_input("Buscar por Nome ou CPF/CNPJ", "")
        query = db.query(Cliente)
        if search:
            query = query.filter(or_(Cliente.nome.ilike(f"%{search}%"), Cliente.cpf_cnpj.ilike(f"%{search}%")))
        clientes = query.all()
        
        if clientes:
            for cli in clientes:
                with st.expander(f"👤 {cli.nome} - {cli.cpf_cnpj}"):
                    edit_mode = st.toggle("✏️ Editar Dados", key=f"toggle_edit_{cli.id}")
                    
                    if not edit_mode:
                        # Modo Visualização
                        c1, c2 = st.columns(2)
                        c1.write(f"**Email:** {cli.email}")
                        c1.write(f"**Telefone:** {cli.telefone}")
                        c2.write(f"**Endereço:** {cli.endereco}")
                        st.write(f"**Observações:** {cli.observacoes}")
                        st.caption(f"Cadastrado em: {format_date_br(cli.data_cadastro)}")
                        
                        st.markdown("---")
                        col_doc, col_del = st.columns([0.8, 0.2])
                        
                        with col_doc:
                            if st.button(f"📄 Gerar Procuração (Word)", key=f"btn_doc_{cli.id}"):
                                docx_file = services.gerar_procuracao(cli)
                                if docx_file:
                                    st.download_button(
                                        label="⬇️ Baixar Procuração Preenchida",
                                        data=docx_file,
                                        file_name=f"Procuracao_{cli.nome}.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                        key=f"dl_doc_{cli.id}"
                                    )
                                else:
                                    st.warning("⚠️ Arquivo 'template_procuracao.docx' não encontrado na pasta 'templates'.")
                        
                        with col_del:
                            if st.button("🗑️ Excluir", key=f"del_cli_{cli.id}"):
                                cli_to_del = db.query(Cliente).get(cli.id)
                                if cli_to_del:
                                    db.delete(cli_to_del)
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
                                cliente_atual = db.query(Cliente).get(cli.id)
                                if cliente_atual:
                                    cliente_atual.nome = ed_nome
                                    cliente_atual.cpf_cnpj = ed_cpf
                                    cliente_atual.telefone = ed_tel
                                    cliente_atual.email = ed_email
                                    cliente_atual.endereco = ed_end
                                    cliente_atual.observacoes = ed_obs
                                    try:
                                        db.commit()
                                        st.success("Dados atualizados com sucesso!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro ao salvar: {e}")
        else:
            st.info("Nenhum cliente encontrado.")

    # NOVO CLIENTE
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

    # NOVO PROCESSO
    with tab2:
        with st.form("form_processo"):
            cli_sel = st.selectbox("Selecione o Cliente", list(cli_dict.keys()))
            num_proc = st.text_input("Número do Processo")
            tribunal = st.text_input("Vara / Tribunal")
            tipo = st.selectbox("Tipo de Ação", ["Cível", "Trabalhista", "Criminal", "Família", "Tributário", "Outros"])
            parte = st.text_input("Parte Contrária")
            status = st.selectbox("Status", ["Em andamento", "Suspenso", "Sentenciado", "Arquivado", "Recurso"])
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

    # LISTA DE PROCESSOS
    with tab1:
        procs = db.query(Processo).join(Cliente).all()
        for p in procs:
            with st.expander(f"{p.numero_processo} - {p.cliente.nome} ({p.status})"):
                
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Tribunal:** {p.tribunal}")
                c1.write(f"**Ação:** {p.tipo_acao}")
                c2.write(f"**Contra:** {p.parte_contraria}")
                c2.write(f"**Data:** {format_date_br(p.data_inicio)}")
                c3.info(f"Status: {p.status}")
                
                st.markdown("---")
                
                t_sub1, t_sub2, t_sub3, t_sub4 = st.tabs(["📂 Arquivos (IA)", "📝 Diário", "💰 Financeiro", "⚙️ Editar Processo"])
                
                # ABA ARQUIVOS + IA (GEMMA 3)
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
                                col_icon, col_name, col_act = st.columns([0.05, 0.55, 0.4])
                                col_icon.text("📄")
                                col_name.write(f"**{f}**")
                                
                                # Botões de Ação
                                bt_view, bt_ai, bt_del = col_act.columns([0.3, 0.4, 0.3])
                                
                                # Visualizar
                                if bt_view.button("👁️", key=f"view_{p.id}_{f}"):
                                    st.session_state[f"preview_{p.id}"] = f
                                
                                # IA GEMMA 3 (Via Secrets)
                                if f.lower().endswith(".pdf"):
                                    if bt_ai.button("✨ Resumir (Gemma 3)", key=f"ai_{p.id}_{f}"):
                                        with st.spinner(f"Analisando com Gemma 3 (via Google)..."):
                                            full_path = services.get_caminho_arquivo(p.cliente.nome, p.cliente.id, p.numero_processo, f)
                                            texto_pdf = services.extrair_texto_pdf(full_path)
                                            
                                            if "Erro" in texto_pdf:
                                                st.error(texto_pdf)
                                            else:
                                                api_key = st.session_state.get("google_key")
                                                resumo = services.resumir_com_google(texto_pdf, api_key)
                                                st.session_state[f"resumo_{p.id}_{f}"] = resumo
                                
                                # Excluir
                                if bt_del.button("❌", key=f"del_{p.id}_{f}"):
                                    services.excluir_arquivo(p.cliente.nome, p.cliente.id, p.numero_processo, f)
                                    st.rerun()

                            # Mostrar Visualização
                            if f"preview_{p.id}" in st.session_state and st.session_state[f"preview_{p.id}"] == f:
                                st.info(f"Visualizando: {f}")
                                full_path = services.get_caminho_arquivo(p.cliente.nome, p.cliente.id, p.numero_processo, f)
                                render_file_preview(full_path, f)
                                if st.button("Fechar Visualização", key=f"close_view_{p.id}"):
                                    del st.session_state[f"preview_{p.id}"]
                                    st.rerun()

                            # Mostrar Resumo IA
                            if f"resumo_{p.id}_{f}" in st.session_state:
                                with st.chat_message("assistant"):
                                    st.markdown(f"### 🤖 Resumo Gemma 3 - {f}")
                                    st.markdown(st.session_state[f"resumo_{p.id}_{f}"])
                                    if st.button("Fechar Resumo", key=f"close_ai_{p.id}_{f}"):
                                        del st.session_state[f"resumo_{p.id}_{f}"]
                                        st.rerun()
                    else:
                        st.caption("Nenhum arquivo anexado.")

                # ABA DIÁRIO
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

                # ABA FINANCEIRO
                with t_sub3:
                    st.subheader("Controle Financeiro")
                    with st.form(key=f"fin_form_{p.id}"):
                        c_f1, c_f2, c_f3 = st.columns(3)
                        desc_fin = c_f1.text_input("Descrição")
                        valor_fin = c_f2.number_input("Valor (R$)", min_value=0.0, step=100.0)
                        tipo_fin = c_f3.selectbox("Tipo", ["Honorário", "Despesa/Custa"])
                        c_f4, c_f5 = st.columns(2)
                        dt_venc = c_f4.date_input("Vencimento", value=date.today(), format="DD/MM/YYYY")
                        status_fin = c_f5.selectbox("Status", ["Pendente", "Pago"])
                        
                        if st.form_submit_button("➕ Adicionar"):
                            novo_fin = Financeiro(processo_id=p.id, descricao=desc_fin, valor=valor_fin, tipo=tipo_fin, data_vencimento=dt_venc, status=status_fin)
                            db.add(novo_fin)
                            db.commit()
                            st.rerun()
                    
                    fin_items = db.query(Financeiro).filter(Financeiro.processo_id == p.id).all()
                    if fin_items:
                        data_fin = []
                        total_hon = 0
                        total_desp = 0
                        for f in fin_items:
                            data_fin.append({"Vencimento": f.data_vencimento.strftime("%d/%m/%Y"), "Descrição": f.descricao, "Tipo": f.tipo, "Valor": format_moeda(f.valor), "Status": f.status, "ID": f.id})
                            if f.tipo == "Honorário": total_hon += f.valor
                            else: total_desp += f.valor
                        
                        st.dataframe(pd.DataFrame(data_fin).drop(columns=["ID"]), use_container_width=True)
                        st.caption(f"Total Honorários: {format_moeda(total_hon)} | Total Despesas: {format_moeda(total_desp)}")
                        
                        st.markdown("##### Atualizar Status")
                        fin_opts = [f"{d['Descrição']} - {d['Valor']}" for d in data_fin]
                        sel_fin = st.selectbox("Selecione o lançamento", fin_opts, key=f"sel_fin_{p.id}")
                        if st.button("Alternar Pago/Pendente", key=f"btn_fin_up_{p.id}"):
                            idx = fin_opts.index(sel_fin)
                            fin_id = data_fin[idx]['ID']
                            fin_obj = db.query(Financeiro).get(fin_id)
                            fin_obj.status = "Pago" if fin_obj.status == "Pendente" else "Pendente"
                            db.commit()
                            st.rerun()
                    else:
                        st.info("Nenhum lançamento.")

                # ABA EDITAR
                with t_sub4:
                    with st.form(key=f"form_edit_proc_{p.id}"):
                        ed_num = st.text_input("Número", value=p.numero_processo)
                        ed_trib = st.text_input("Tribunal", value=p.tribunal)
                        lista_tipos = ["Cível", "Trabalhista", "Criminal", "Família", "Tributário", "Outros"]
                        idx_tipo = lista_tipos.index(p.tipo_acao) if p.tipo_acao in lista_tipos else 0
                        ed_tipo = st.selectbox("Tipo", lista_tipos, index=idx_tipo)
                        ed_parte = st.text_input("Parte Contrária", value=p.parte_contraria)
                        lista_status = ["Em andamento", "Suspenso", "Sentenciado", "Arquivado", "Recurso"]
                        idx_status = lista_status.index(p.status) if p.status in lista_status else 0
                        ed_status = st.selectbox("Status", lista_status, index=idx_status)
                        ed_dt = st.date_input("Data Início", value=p.data_inicio, format="DD/MM/YYYY")
                        ed_obs = st.text_area("Observações", value=p.observacoes)
                        ed_est = st.text_area("Estratégia", value=p.estrategia)
                        
                        if st.form_submit_button("💾 Atualizar"):
                            proc_atual = db.query(Processo).get(p.id)
                            if proc_atual:
                                proc_atual.numero_processo = ed_num
                                proc_atual.tribunal = ed_trib
                                proc_atual.tipo_acao = ed_tipo
                                proc_atual.parte_contraria = ed_parte
                                proc_atual.status = ed_status
                                proc_atual.data_inicio = ed_dt
                                proc_atual.observacoes = ed_obs
                                proc_atual.estrategia = ed_est
                                try:
                                    db.commit()
                                    st.success("Atualizado!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro: {e}")

def show_agenda(db: Session):
    st.header("📅 Agenda Jurídica")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Novo Evento")
        procs = db.query(Processo).all()
        if not procs:
            st.warning("Cadastre processos para agendar.")
        else:
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
                "Processo": proc.numero_processo if proc else "N/A",
                "Status": status_icon,
                "ID": e.id,
                "Concluido": e.concluido
            })
            
        if df_data:
            st.dataframe(pd.DataFrame(df_data).drop(columns=["ID", "Concluido"]), use_container_width=True)
            
            st.write("---")
            st.caption("Ações rápidas:")
            
            evento_opcoes = [f"{d['Data']} - {d['Evento']}" for d in df_data]
            sel_evt = st.selectbox("Selecione um evento para alterar status", evento_opcoes)
            
            if st.button("Alternar Status (Concluído/Pendente)"):
                idx = evento_opcoes.index(sel_evt)
                evt_id = df_data[idx]['ID']
                
                evt_obj = db.query(Audiencia).get(evt_id)
                if evt_obj:
                    evt_obj.concluido = 1 if evt_obj.concluido == 0 else 0
                    db.commit()
                    st.rerun()
        else:
            st.info("Nenhum evento encontrado.")

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
    st.warning("Nota: Em ambientes de nuvem (Streamlit Cloud), o backup baixa apenas os dados da sessão atual se o disco não for persistente.")
    if st.button("Gerar Backup Completo (.zip)"):
        with st.spinner("Compactando arquivos e banco de dados..."):
            zip_path = services.criar_backup()
            with open(zip_path, "rb") as f:
                st.download_button(
                    label="Baixar Backup ZIP",
                    data=f,
                    file_name=str(zip_path).split('/')[-1],
                    mime="application/zip"
                )

# --- Main Flow ---

def main():
    if not auth.login_page():
        return

    # Sidebar Navigation
    st.sidebar.title(f"Olá, {st.session_state.username}")
    
    # --- INTEGRAÇÃO SECRETS PARA API ---
    # Busca a chave nos segredos. Se não existir, pede manualmente.
    if "GOOGLE_API_KEY" in st.secrets:
        st.session_state["google_key"] = st.secrets["GOOGLE_API_KEY"]
        # st.sidebar.success("✅ AI Ativada") # Opcional: mostrar confirmação visual
    else:
        st.sidebar.markdown("### 🤖 Configuração IA")
        key = st.sidebar.text_input("API Key (Gemma 3)", type="password", help="Chave do Google AI Studio")
        if key:
            st.session_state["google_key"] = key
    # -----------------------------------

    menu = st.sidebar.radio(
        "Menu",
        ["Dashboard", "Clientes", "Processos", "Agenda", "Calculadora Prazos", "Relatórios"],
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
        elif menu == "Calculadora Prazos":
            show_calculadora_prazos()
        elif menu == "Relatórios":
            show_relatorios(db)
    except Exception as e:
        st.error(f"Erro inesperado na aplicação: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
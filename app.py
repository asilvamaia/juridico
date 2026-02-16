import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, func
import base64
import mimetypes
import io
import time

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

# Inicialização do Banco de Dados e Usuário Admin
init_db()
auth.criar_usuario_inicial()

# --- Funções Auxiliares de Interface (UI) ---

def format_date_br(dt):
    """Formata data (datetime ou date) para o padrão brasileiro DD/MM/AAAA."""
    if isinstance(dt, (datetime, date)):
        return dt.strftime("%d/%m/%Y")
    return "-"

def format_moeda(valor):
    """Formata valor float para moeda Real (R$)."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def render_file_preview(filepath, filename):
    """Renderiza visualização de arquivos ou botão de download."""
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
    """Tela de Gestão de Advogados."""
    st.header("⚖️ Cadastro de Advogados (Banca)")
    st.info("Cadastre aqui os advogados que aparecerão nas procurações.")
    
    tab1, tab2 = st.tabs(["Listar Advogados", "Novo Advogado"])
    
    # Aba: Novo Advogado
    with tab2:
        with st.form("form_novo_advogado"):
            nome_completo = st.text_input("Nome Completo")
            numero_oab = st.text_input("OAB (Ex: OAB/SP 123.456)")
            nacionalidade = st.text_input("Nacionalidade", value="brasileiro(a)")
            estado_civil = st.text_input("Estado Civil", value="casado(a)")
            endereco_profissional = st.text_area("Endereço Profissional")
            
            submitted = st.form_submit_button("Salvar Advogado")
            
            if submitted:
                if nome_completo and numero_oab:
                    novo_advogado = Advogado(
                        nome=nome_completo,
                        oab=numero_oab,
                        nacionalidade=nacionalidade,
                        estado_civil=estado_civil,
                        endereco=endereco_profissional
                    )
                    db.add(novo_advogado)
                    db.commit()
                    
                    st.success("✅ Advogado cadastrado com sucesso!")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("⚠️ Nome e OAB são obrigatórios.")

    # Aba: Listar Advogados
    with tab1:
        advogados = db.query(Advogado).all()
        if advogados:
            for advogado in advogados:
                with st.expander(f"🎓 {advogado.nome} - {advogado.oab}"):
                    st.write(f"**Nacionalidade:** {advogado.nacionalidade}")
                    st.write(f"**Estado Civil:** {advogado.estado_civil}")
                    st.write(f"**Endereço:** {advogado.endereco}")
                    
                    st.markdown("---")
                    if st.button("🗑️ Excluir Advogado", key=f"del_adv_{advogado.id}"):
                        db.delete(advogado)
                        db.commit()
                        st.success("Advogado removido.")
                        time.sleep(1)
                        st.rerun()
        else:
            st.info("Nenhum advogado cadastrado.")

def show_calculadora_prazos():
    """Tela da Calculadora de Prazos."""
    st.header("📆 Calculadora de Prazos Processuais")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        data_publicacao = col1.date_input("Data da Publicação/Intimação", value=date.today(), format="DD/MM/YYYY")
        dias_prazo = col2.number_input("Prazo em Dias Úteis", min_value=1, value=15)
        
        if st.button("Calcular Vencimento"):
            resultado = services.calcular_prazo_util(data_publicacao, dias_prazo)
            
            st.markdown("---")
            col_res1, col_res2 = st.columns(2)
            col_res1.success(f"📅 Data Fatal: **{resultado.strftime('%d/%m/%Y')}**")
            col_res1.caption(f"Dia da semana: {resultado.strftime('%A')}")
            col_res2.info("⚠️ Nota: O sistema considera feriados nacionais. Verifique feriados locais/municipais manualmente.")

def show_dashboard(db: Session):
    """Tela Inicial - Dashboard."""
    st.header("📊 Dashboard Geral")
    
    col1, col2, col3, col4 = st.columns(4)
    
    total_clientes = db.query(Cliente).count()
    total_processos = db.query(Processo).filter(Processo.status == "Em andamento").count()
    
    total_receitas = db.query(func.sum(Financeiro.valor)).filter(Financeiro.tipo == "Honorário", Financeiro.status == "Pago").scalar() or 0
    total_a_receber = db.query(func.sum(Financeiro.valor)).filter(Financeiro.tipo == "Honorário", Financeiro.status == "Pendente").scalar() or 0
    
    col1.metric("Clientes Ativos", total_clientes)
    col2.metric("Processos em Andamento", total_processos)
    col3.metric("Honorários Recebidos", format_moeda(total_receitas))
    col4.metric("A Receber", format_moeda(total_a_receber))

    st.markdown("---")
    
    st.subheader("🔔 Próximos Compromissos")
    proximos_eventos = db.query(Audiencia).filter(Audiencia.concluido == 0).order_by(Audiencia.data_hora).limit(5).all()
    
    if proximos_eventos:
        dados_tabela = []
        for evento in proximos_eventos:
            processo = db.query(Processo).get(evento.processo_id)
            cliente_nome = processo.cliente.nome if processo and processo.cliente else "N/A"
            dados_tabela.append([
                evento.data_hora.strftime("%d/%m/%Y %H:%M"), 
                evento.tipo, 
                cliente_nome, 
                evento.titulo
            ])
            
        df_eventos = pd.DataFrame(dados_tabela, columns=["Data", "Tipo", "Cliente", "Título"])
        st.table(df_eventos)
    else:
        st.info("Nenhum compromisso pendente.")

def show_clientes(db: Session):
    """Tela de Gestão de Clientes."""
    st.header("📁 Gestão de Clientes")
    tab1, tab2 = st.tabs(["Listar/Buscar", "Novo Cliente"])
    
    # Aba: Listar Clientes
    with tab1:
        termo_busca = st.text_input("Buscar por Nome ou CPF/CNPJ", "")
        query = db.query(Cliente)
        if termo_busca:
            query = query.filter(or_(Cliente.nome.ilike(f"%{termo_busca}%"), Cliente.cpf_cnpj.ilike(f"%{termo_busca}%")))
        
        lista_clientes = query.all()
        lista_advogados = db.query(Advogado).all()
        
        if lista_clientes:
            for cliente in lista_clientes:
                with st.expander(f"👤 {cliente.nome} - {cliente.cpf_cnpj}"):
                    
                    # Dados do Cliente
                    col_dados1, col_dados2 = st.columns(2)
                    col_dados1.write(f"**Email:** {cliente.email}")
                    col_dados2.write(f"**Telefone:** {cliente.telefone}")
                    st.write(f"**Endereço:** {cliente.endereco}")
                    st.write(f"**Observações:** {cliente.observacoes}")
                    
                    st.markdown("---")
                    
                    # Seção de Documentos (Procuração)
                    st.markdown("##### 📄 Geração de Documentos")
                    
                    if not lista_advogados:
                        st.warning("⚠️ Cadastre um advogado na aba 'Advogados' para habilitar a geração de procuração.")
                    else:
                        col_doc_sel, col_doc_btn = st.columns([0.7, 0.3])
                        
                        with col_doc_sel:
                            # Cria dicionário {Label: ID} para o selectbox
                            opcoes_advogados = {f"{adv.nome} ({adv.oab})": adv.id for adv in lista_advogados}
                            advogado_selecionado_label = st.selectbox(
                                "Selecione o Advogado Responsável", 
                                list(opcoes_advogados.keys()), 
                                key=f"sel_adv_cli_{cliente.id}"
                            )
                        
                        with col_doc_btn:
                            if st.button("Gerar Procuração (Word)", key=f"btn_doc_{cliente.id}"):
                                id_advogado = opcoes_advogados[advogado_selecionado_label]
                                objeto_advogado = db.query(Advogado).get(id_advogado)
                                
                                arquivo_docx = services.gerar_procuracao(cliente, objeto_advogado)
                                
                                if arquivo_docx:
                                    st.download_button(
                                        label="⬇️ Baixar DOCX",
                                        data=arquivo_docx,
                                        file_name=f"Procuracao_{cliente.nome}.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                        key=f"dl_doc_{cliente.id}"
                                    )
                                else:
                                    st.error("⚠️ Template 'template_procuracao.docx' não encontrado na pasta 'templates'.")
                    
                    st.markdown("---")
                    
                    # Botão de Excluir
                    if st.button("🗑️ Excluir Cliente", key=f"del_cli_{cliente.id}"):
                        db.delete(cliente)
                        db.commit()
                        st.success("Cliente excluído com sucesso!")
                        time.sleep(1)
                        st.rerun()

        else:
            st.info("Nenhum cliente encontrado.")

    # Aba: Novo Cliente
    with tab2:
        with st.form("form_novo_cliente"):
            nome = st.text_input("Nome Completo")
            cpf = st.text_input("CPF/CNPJ")
            telefone = st.text_input("Telefone")
            email = st.text_input("E-mail")
            endereco = st.text_area("Endereço")
            observacoes = st.text_area("Observações")
            
            submitted = st.form_submit_button("Cadastrar Cliente")
            
            if submitted:
                if nome and cpf:
                    novo_cliente = Cliente(
                        nome=nome, 
                        cpf_cnpj=cpf, 
                        telefone=telefone, 
                        email=email, 
                        endereco=endereco, 
                        observacoes=observacoes
                    )
                    db.add(novo_cliente)
                    db.commit()
                    
                    services.criar_estrutura_cliente(nome, novo_cliente.id)
                    
                    st.success(f"✅ Cliente {nome} cadastrado com sucesso!")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("Nome e CPF são obrigatórios.")

def show_processos(db: Session):
    """Tela de Gestão de Processos."""
    st.header("⚖️ Controle de Processos")
    
    tab1, tab2 = st.tabs(["Meus Processos", "Novo Processo"])
    
    # Verifica se existem clientes cadastrados
    lista_clientes = db.query(Cliente).all()
    if not lista_clientes:
        st.warning("⚠️ Você precisa cadastrar clientes antes de criar processos.")
        return

    # Mapeamento para o SelectBox
    mapa_clientes = {f"{c.nome} ({c.cpf_cnpj})": c.id for c in lista_clientes}

    # Aba: Novo Processo
    with tab2:
        with st.form("form_novo_processo"):
            cliente_selecionado = st.selectbox("Selecione o Cliente", list(mapa_clientes.keys()))
            
            col_proc1, col_proc2 = st.columns(2)
            numero_processo = col_proc1.text_input("Número do Processo (CNJ)")
            tribunal = col_proc2.text_input("Vara / Tribunal")
            
            col_proc3, col_proc4 = st.columns(2)
            tipo_acao = col_proc3.selectbox("Tipo de Ação", ["Cível", "Trabalhista", "Criminal", "Família", "Tributário", "Previdenciário", "Outros"])
            status = col_proc4.selectbox("Status", ["Em andamento", "Suspenso", "Sentenciado", "Arquivado"])
            
            parte_contraria = st.text_input("Parte Contrária")
            data_inicio = st.date_input("Data de Início", value=date.today(), format="DD/MM/YYYY")
            
            observacoes = st.text_area("Observações Iniciais")
            estrategia = st.text_area("🧠 Estratégia do Caso (Privado)", help="Campo confidencial para anotações estratégicas.")
            
            submitted = st.form_submit_button("Salvar Processo")
            
            if submitted:
                if numero_processo:
                    id_cliente = mapa_clientes[cliente_selecionado]
                    novo_processo = Processo(
                        cliente_id=id_cliente, 
                        numero_processo=numero_processo, 
                        tribunal=tribunal,
                        tipo_acao=tipo_acao,
                        parte_contraria=parte_contraria,
                        status=status, 
                        data_inicio=data_inicio,
                        observacoes=observacoes,
                        estrategia=estrategia
                    )
                    db.add(novo_processo)
                    db.commit()
                    
                    objeto_cliente = db.query(Cliente).get(id_cliente)
                    services.criar_estrutura_processo(objeto_cliente.nome, id_cliente, numero_processo)
                    
                    st.success("✅ Processo criado com sucesso!")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("O número do processo é obrigatório.")

    # Aba: Lista de Processos
    with tab1:
        processos = db.query(Processo).join(Cliente).all()
        if processos:
            for processo in processos:
                with st.expander(f"{processo.numero_processo} - {processo.cliente.nome} ({processo.status})"):
                    
                    # Visualização rápida dos dados
                    col_info1, col_info2, col_info3 = st.columns(3)
                    col_info1.write(f"**Ação:** {processo.tipo_acao}")
                    col_info1.write(f"**Tribunal:** {processo.tribunal}")
                    col_info2.write(f"**Contra:** {processo.parte_contraria}")
                    col_info2.write(f"**Início:** {format_date_br(processo.data_inicio)}")
                    col_info3.info(f"Status: {processo.status}")
                    
                    # --- DADOS ADICIONAIS RESTAURADOS ---
                    if processo.observacoes:
                        st.markdown(f"**📝 Observações:** {processo.observacoes}")

                    # --- ESTRATÉGIA COM TOGGLE DE PRIVACIDADE RESTAURADA ---
                    if processo.estrategia:
                        mostrar_estrategia = st.toggle("👁️ Ver Estratégia (Confidencial)", key=f"toggle_est_{processo.id}")
                        if mostrar_estrategia:
                            st.warning(f"**🧠 Estratégia:** {processo.estrategia}")
                    
                    st.markdown("---")
                    
                    # Abas internas do Processo
                    tab_arquivos, tab_financeiro, tab_diario, tab_editar = st.tabs(
                        ["📂 Arquivos (IA)", "💰 Financeiro", "📝 Diário", "⚙️ Editar/Detalhes"]
                    )
                    
                    # --- ABA 1: ARQUIVOS & IA ---
                    with tab_arquivos:
                        st.subheader("Gestão de Documentos")
                        
                        arquivos_upload = st.file_uploader("Anexar documentos", key=f"upload_{processo.id}", accept_multiple_files=True)
                        if arquivos_upload:
                            for arquivo in arquivos_upload:
                                services.salvar_arquivo(arquivo, processo.cliente.nome, processo.cliente.id, processo.numero_processo)
                            st.success("Arquivos salvos!")
                            time.sleep(1)
                            st.rerun()
                        
                        st.markdown("---")
                        
                        lista_arquivos = services.listar_arquivos(processo.cliente.nome, processo.cliente.id, processo.numero_processo)
                        
                        if lista_arquivos:
                            for nome_arquivo in lista_arquivos:
                                col_nome, col_acoes = st.columns([0.6, 0.4])
                                
                                col_nome.text(f"📄 {nome_arquivo}")
                                
                                with col_acoes:
                                    col_btn_ia, col_btn_ver, col_btn_del = st.columns(3)
                                    
                                    if nome_arquivo.lower().endswith(".pdf"):
                                        if col_btn_ia.button("✨ IA", key=f"btn_ia_{processo.id}_{nome_arquivo}", help="Resumir com Gemma 3"):
                                            with st.spinner("Lendo PDF e gerando resumo..."):
                                                caminho_completo = services.get_caminho_arquivo(processo.cliente.nome, processo.cliente.id, processo.numero_processo, nome_arquivo)
                                                texto_pdf = services.extrair_texto_pdf(caminho_completo)
                                                
                                                api_key = st.session_state.get("google_key")
                                                resumo_ia = services.resumir_com_google(texto_pdf, api_key)
                                                
                                                st.session_state[f"resumo_{processo.id}_{nome_arquivo}"] = resumo_ia
                                    
                                    if col_btn_ver.button("👁️", key=f"btn_ver_{processo.id}_{nome_arquivo}"):
                                        caminho_completo = services.get_caminho_arquivo(processo.cliente.nome, processo.cliente.id, processo.numero_processo, nome_arquivo)
                                        render_file_preview(caminho_completo, nome_arquivo)
                                    
                                    if col_btn_del.button("❌", key=f"btn_del_{processo.id}_{nome_arquivo}"):
                                        services.excluir_arquivo(processo.cliente.nome, processo.cliente.id, processo.numero_processo, nome_arquivo)
                                        st.rerun()

                                if f"resumo_{processo.id}_{nome_arquivo}" in st.session_state:
                                    st.info(st.session_state[f"resumo_{processo.id}_{nome_arquivo}"])
                        else:
                            st.caption("Nenhum arquivo anexado a este processo.")

                    # --- ABA 2: FINANCEIRO ---
                    with tab_financeiro:
                        st.subheader("Controle Financeiro")
                        
                        with st.form(key=f"form_fin_{processo.id}"):
                            col_f1, col_f2, col_f3 = st.columns(3)
                            desc_fin = col_f1.text_input("Descrição (Ex: Honorários)")
                            valor_fin = col_f2.number_input("Valor (R$)", min_value=0.0, step=100.0)
                            tipo_fin = col_f3.selectbox("Tipo", ["Honorário", "Despesa/Custa"])
                            
                            if st.form_submit_button("Adicionar Lançamento"):
                                novo_fin = Financeiro(
                                    processo_id=processo.id, 
                                    descricao=desc_fin, 
                                    valor=valor_fin, 
                                    tipo=tipo_fin
                                )
                                db.add(novo_fin)
                                db.commit()
                                st.success("Lançamento adicionado!")
                                time.sleep(1)
                                st.rerun()
                        
                        lancamentos = db.query(Financeiro).filter(Financeiro.processo_id == processo.id).all()
                        if lancamentos:
                            for lanc in lancamentos:
                                col_l1, col_l2, col_l3 = st.columns([0.6, 0.2, 0.2])
                                col_l1.write(f"**{lanc.descricao}** ({lanc.tipo})")
                                col_l2.write(format_moeda(lanc.valor))
                                
                                status_icon = "✅ Pago" if lanc.status == "Pago" else "⏳ Pendente"
                                if col_l3.button(status_icon, key=f"btn_status_{lanc.id}"):
                                    lanc.status = "Pendente" if lanc.status == "Pago" else "Pago"
                                    db.commit()
                                    st.rerun()
                        else:
                            st.caption("Nenhum lançamento financeiro registrado.")

                    # --- ABA 3: DIÁRIO ---
                    with tab_diario:
                        st.subheader("Notas do Processo")
                        
                        nota_texto = st.text_input("Nova nota ou andamento", key=f"input_nota_{processo.id}")
                        if st.button("Adicionar Nota", key=f"btn_add_nota_{processo.id}"):
                            if nota_texto:
                                db.add(DiarioProcessual(processo_id=processo.id, texto=nota_texto))
                                db.commit()
                                st.rerun()
                        
                        st.markdown("---")
                        notas = db.query(DiarioProcessual).filter(DiarioProcessual.processo_id == processo.id).order_by(desc(DiarioProcessual.data_registro)).all()
                        
                        for nota in notas:
                            st.text(f"{nota.data_registro.strftime('%d/%m/%Y %H:%M')} - {nota.texto}")

                    # --- ABA 4: EDITAR ---
                    with tab_editar:
                        st.subheader("Editar Dados do Processo")
                        with st.form(key=f"form_editar_proc_{processo.id}"):
                            
                            ed_tribunal = st.text_input("Tribunal", value=processo.tribunal)
                            ed_parte = st.text_input("Parte Contrária", value=processo.parte_contraria)
                            
                            lista_status_edit = ["Em andamento", "Suspenso", "Sentenciado", "Arquivado"]
                            idx_status = lista_status_edit.index(processo.status) if processo.status in lista_status_edit else 0
                            novo_status = st.selectbox("Status", lista_status_edit, index=idx_status)
                            
                            st.markdown("---")
                            st.markdown("**Anotações Privadas**")
                            ed_obs = st.text_area("Observações", value=processo.observacoes)
                            ed_estrategia = st.text_area("Estratégia", value=processo.estrategia)
                            
                            if st.form_submit_button("Atualizar Processo"):
                                processo.tribunal = ed_tribunal
                                processo.parte_contraria = ed_parte
                                processo.status = novo_status
                                processo.observacoes = ed_obs
                                processo.estrategia = ed_estrategia
                                db.commit()
                                st.success("Status atualizado!")
                                time.sleep(1)
                                st.rerun()
        else:
            st.info("Nenhum processo cadastrado.")

def show_agenda(db: Session):
    """Tela da Agenda Jurídica."""
    st.header("📅 Agenda Jurídica")
    
    col_novo, col_lista = st.columns([1, 2])
    
    # Coluna Esquerda: Novo Agendamento
    with col_novo:
        st.subheader("Novo Compromisso")
        lista_processos = db.query(Processo).all()
        
        if lista_processos:
            opcoes_processos = {f"{p.numero_processo} - {p.cliente.nome}": p.id for p in lista_processos}
            
            with st.form("form_agenda"):
                proc_selecionado = st.selectbox("Vincular ao Processo", list(opcoes_processos.keys()))
                titulo = st.text_input("Título (Ex: Audiência)")
                data_evento = st.date_input("Data")
                hora_evento = st.time_input("Hora")
                
                if st.form_submit_button("Agendar"):
                    id_proc = opcoes_processos[proc_selecionado]
                    data_hora_final = datetime.combine(data_evento, hora_evento)
                    
                    novo_evento = Audiencia(
                        processo_id=id_proc, 
                        titulo=titulo, 
                        data_hora=data_hora_final
                    )
                    db.add(novo_evento)
                    db.commit()
                    st.success("Compromisso agendado!")
                    time.sleep(1)
                    st.rerun()
        else:
            st.warning("Cadastre processos para usar a agenda.")
    
    # Coluna Direita: Lista de Compromissos
    with col_lista:
        st.subheader("Próximos Eventos")
        eventos = db.query(Audiencia).filter(Audiencia.concluido == 0).order_by(Audiencia.data_hora).all()
        
        if eventos:
            for evento in eventos:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([0.2, 0.6, 0.2])
                    c1.write(f"📅 **{evento.data_hora.strftime('%d/%m')}**")
                    c1.write(f"⏰ {evento.data_hora.strftime('%H:%M')}")
                    
                    c2.write(f"**{evento.titulo}**")
                    proc = db.query(Processo).get(evento.processo_id)
                    if proc and proc.cliente:
                        c2.caption(f"Proc: {proc.numero_processo} | Cli: {proc.cliente.nome}")
                    
                    if c3.button("Concluir", key=f"btn_ok_evt_{evento.id}"):
                        evento.concluido = 1
                        db.commit()
                        st.rerun()
        else:
            st.info("Agenda vazia! 🎉")

def show_relatorios(db: Session):
    """Tela de Backups."""
    st.header("💾 Backup e Segurança")
    
    st.info("Gera um arquivo .zip contendo o banco de dados e todos os documentos anexados.")
    
    if st.button("Gerar Backup Completo"):
        with st.spinner("Compactando arquivos..."):
            caminho_zip = services.criar_backup()
            
            with open(caminho_zip, "rb") as arquivo_zip:
                st.download_button(
                    label="⬇️ Baixar Backup (.zip)",
                    data=arquivo_zip,
                    file_name="backup_jurisflow.zip",
                    mime="application/zip"
                )

# --- Função Principal ---

def main():
    # 1. Autenticação (Login)
    if not auth.login_page():
        return

    # 2. Configurações Globais e Sidebar
    st.sidebar.title(f"Olá, {st.session_state.username}")
    
    # --- LÓGICA DE API KEY (SECRETS) ---
    api_key_nos_secrets = None
    try:
        if "GOOGLE_API_KEY" in st.secrets:
            api_key_nos_secrets = st.secrets["GOOGLE_API_KEY"]
            st.session_state["google_key"] = api_key_nos_secrets
    except (FileNotFoundError, KeyError):
        pass
    
    # Se NÃO achou nos secrets e NÃO tem na sessão, mostra o campo
    chave_esta_configurada = False
    if "google_key" in st.session_state and st.session_state["google_key"]:
        chave_esta_configurada = True

    if not chave_esta_configurada:
        st.sidebar.markdown("### 🤖 Configuração IA")
        input_chave_manual = st.sidebar.text_input(
            "API Key (Google)", 
            type="password", 
            help="Chave necessária para usar o Gemma 3. Configure nos Secrets para sumir daqui."
        )
        
        if input_chave_manual:
            st.session_state["google_key"] = input_chave_manual
            st.rerun()
            
    # -----------------------------------

    # Menu de Navegação
    menu_selecionado = st.sidebar.radio(
        "Menu Principal", 
        ["Dashboard", "Clientes", "Advogados", "Processos", "Agenda", "Calculadora Prazos", "Relatórios"],
        index=0
    )
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair / Logout"):
        auth.logout()

    # 3. Roteamento de Telas
    db = SessionLocal()
    try:
        if menu_selecionado == "Dashboard":
            show_dashboard(db)
        elif menu_selecionado == "Clientes":
            show_clientes(db)
        elif menu_selecionado == "Advogados":
            show_advogados(db)
        elif menu_selecionado == "Processos":
            show_processos(db)
        elif menu_selecionado == "Agenda":
            show_agenda(db)
        elif menu_selecionado == "Calculadora Prazos":
            show_calculadora_prazos()
        elif menu_selecionado == "Relatórios":
            show_relatorios(db)
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
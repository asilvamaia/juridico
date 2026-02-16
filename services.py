import os
import shutil
import re
from pathlib import Path
from datetime import datetime, timedelta
import holidays
from docxtpl import DocxTemplate
import io
from pypdf import PdfReader
from google import genai  # Biblioteca oficial do Google (v1.0+)

# Configuração de Diretórios Básicos
BASE_DIR = Path("dados")
TEMPLATES_DIR = Path("templates")

# --- 1. Manipulação de Arquivos e Diretórios ---

def sanitize_filename(name):
    """Remove caracteres inválidos e espaços para criar nomes de arquivos seguros."""
    return re.sub(r'[<>:"/\\|?*]', '', str(name)).strip().replace(' ', '_')

def get_cliente_dir(cliente_nome, cliente_id):
    """Retorna o objeto Path para a pasta raiz de um cliente."""
    safe_name = sanitize_filename(cliente_nome)
    folder_name = f"{safe_name}_{cliente_id}"
    path = BASE_DIR / "clientes" / folder_name
    return path

def get_processo_dir(cliente_nome, cliente_id, numero_processo):
    """Retorna o objeto Path para a pasta de arquivos de um processo específico."""
    client_path = get_cliente_dir(cliente_nome, cliente_id)
    safe_proc = sanitize_filename(numero_processo)
    proc_path = client_path / "processos" / safe_proc / "arquivos_anexados"
    return proc_path

def criar_estrutura_cliente(cliente_nome, cliente_id):
    """Cria a estrutura de pastas física para um novo cliente."""
    path = get_cliente_dir(cliente_nome, cliente_id)
    path.mkdir(parents=True, exist_ok=True)
    
    # Garante que a pasta de templates também exista para evitar erros
    TEMPLATES_DIR.mkdir(exist_ok=True)
    
    # Cria um arquivo JSON com metadados básicos (opcional, para controle futuro)
    import json
    meta_path = path / "dados_cliente.json"
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump({
            "id": cliente_id, 
            "nome": cliente_nome, 
            "criado_em": str(datetime.now())
        }, f)

def criar_estrutura_processo(cliente_nome, cliente_id, numero_processo):
    """Cria a estrutura de pastas para um novo processo."""
    path = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    path.mkdir(parents=True, exist_ok=True)

def salvar_arquivo(uploaded_file, cliente_nome, cliente_id, numero_processo):
    """Salva um arquivo enviado pelo Streamlit na pasta correta do processo."""
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    
    # Cria a pasta se ela não existir
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = target_dir / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def listar_arquivos(cliente_nome, cliente_id, numero_processo):
    """Retorna uma lista com os nomes dos arquivos na pasta do processo."""
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    if not target_dir.exists():
        return []
    return [f.name for f in target_dir.iterdir() if f.is_file()]

def get_caminho_arquivo(cliente_nome, cliente_id, numero_processo, filename):
    """Retorna o caminho completo (Path) para um arquivo específico."""
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    return target_dir / filename

def excluir_arquivo(cliente_nome, cliente_id, numero_processo, filename):
    """Exclui permanentemente um arquivo do disco."""
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    file_path = target_dir / filename
    if file_path.exists():
        file_path.unlink()
        return True
    return False

def criar_backup():
    """Compacta a pasta 'dados' e o banco SQLite em um arquivo .zip."""
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = backup_dir / f"backup_completo_{timestamp}"
    
    # Faz uma cópia segura do banco de dados antes de zipar
    if os.path.exists("juris_gestao.db"):
        shutil.copy("juris_gestao.db", BASE_DIR / "database_backup.db")
        
    # Cria o arquivo ZIP
    shutil.make_archive(str(zip_name), 'zip', BASE_DIR)
    
    # Remove a cópia temporária do banco
    if (BASE_DIR / "database_backup.db").exists():
        (BASE_DIR / "database_backup.db").unlink()
        
    return f"{zip_name}.zip"

# --- 2. Funcionalidades Jurídicas (Prazos e Documentos) ---

def calcular_prazo_util(data_inicio, dias_uteis):
    """Calcula a data final de um prazo em dias úteis, considerando feriados BR."""
    feriados_br = holidays.BR()
    data_atual = data_inicio
    dias_restantes = dias_uteis
    
    while dias_restantes > 0:
        data_atual += timedelta(days=1)
        # Se for fim de semana (5=Sábado, 6=Domingo) ou feriado, não desconta do prazo
        if data_atual.weekday() < 5 and data_atual not in feriados_br:
            dias_restantes -= 1
            
    return data_atual

def gerar_procuracao(dados_cliente, dados_advogado):
    """
    Preenche um template Word (.docx) com os dados do Cliente e do Advogado.
    Requer o arquivo 'templates/template_procuracao.docx'.
    """
    template_path = TEMPLATES_DIR / "template_procuracao.docx"
    
    if not template_path.exists():
        return None

    doc = DocxTemplate(template_path)
    
    # Dicionário de Contexto (Merge Fields)
    # Aqui unimos os dados do cliente e do advogado
    context = {
        # Dados do Cliente
        'nome_cliente': dados_cliente.nome,
        'cpf_cliente': dados_cliente.cpf_cnpj,
        'endereco_cliente': dados_cliente.endereco,
        'email_cliente': dados_cliente.email,
        
        # Dados do Advogado
        'nome_advogado': dados_advogado.nome,
        'oab_advogado': dados_advogado.oab,
        'end_advogado': dados_advogado.endereco,
        'nac_advogado': dados_advogado.nacionalidade,
        'ec_advogado': dados_advogado.estado_civil,
        
        # Dados Gerais
        'data_hoje': datetime.now().strftime("%d/%m/%Y")
    }
    
    # Renderiza o documento
    doc.render(context)
    
    # Salva em memória (BytesIO) para permitir download direto
    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output

# --- 3. Inteligência Artificial (Google GenAI - Gemma 3) ---

def extrair_texto_pdf(filepath):
    """Lê o texto de um arquivo PDF, limitando a 40 páginas para performance."""
    try:
        reader = PdfReader(filepath)
        text = ""
        # Limite de segurança: lê apenas as primeiras 40 páginas
        for page in reader.pages[:40]:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        return f"Erro ao ler PDF: {str(e)}"

def resumir_com_google(texto, api_key):
    """
    Envia o texto para a API do Google AI Studio usando a nova biblioteca 'google-genai'.
    Modelo configurado: gemma-3-27b-it
    """
    if not api_key:
        return "Erro: API Key não configurada. Verifique os Secrets ou a configuração lateral."
    
    try:
        # Inicializa o Cliente com a nova SDK (v1.0+)
        client = genai.Client(api_key=api_key)
        
        # Define o modelo alvo (Gemma 3)
        model_name = 'gemma-3-27b-it' 
        
        prompt = f"""
        Atue como um Assessor Jurídico Sênior experiente.
        Analise o texto jurídico abaixo extraído de um arquivo PDF:
        
        {texto[:60000]}
        
        Produza um resumo estruturado e profissional contendo:
        1. 📄 **Tipo de Peça**: (Ex: Sentença, Petição Inicial, Agravo, Contestação)
        2. ⚖️ **Resumo dos Fatos**: Uma narrativa cronológica breve do que aconteceu.
        3. 🎯 **Dispositivo/Pedidos**: O que foi decidido pelo juiz ou solicitado pelas partes.
        4. ⚠️ **Prazos e Riscos**: Destaque datas fatais, multas ou obrigações urgentes.
        """
        
        # Chamada de geração de conteúdo
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text

    except Exception as e:
        return f"Erro na IA Google: {str(e)}. Verifique se a API Key está correta e se o modelo '{model_name}' está acessível."
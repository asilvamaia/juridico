import os
import shutil
import re
from pathlib import Path
from datetime import datetime, timedelta
import holidays
from docxtpl import DocxTemplate
import io
from pypdf import PdfReader
from google import genai  # Biblioteca oficial atualizada (v1.0+)

# Configuração de Diretórios
BASE_DIR = Path("dados")
TEMPLATES_DIR = Path("templates")

# --- 1. Manipulação de Arquivos e Diretórios ---

def sanitize_filename(name):
    """Remove caracteres inválidos para nomes de arquivos/pastas."""
    return re.sub(r'[<>:"/\\|?*]', '', str(name)).strip().replace(' ', '_')

def get_cliente_dir(cliente_nome, cliente_id):
    """Retorna o caminho da pasta do cliente."""
    safe_name = sanitize_filename(cliente_nome)
    folder_name = f"{safe_name}_{cliente_id}"
    path = BASE_DIR / "clientes" / folder_name
    return path

def get_processo_dir(cliente_nome, cliente_id, numero_processo):
    """Retorna o caminho da pasta de anexos de um processo."""
    client_path = get_cliente_dir(cliente_nome, cliente_id)
    safe_proc = sanitize_filename(numero_processo)
    proc_path = client_path / "processos" / safe_proc / "arquivos_anexados"
    return proc_path

def criar_estrutura_cliente(cliente_nome, cliente_id):
    """Cria a pasta do cliente e o arquivo json de metadados."""
    path = get_cliente_dir(cliente_nome, cliente_id)
    path.mkdir(parents=True, exist_ok=True)
    
    # Garante que a pasta de templates exista
    TEMPLATES_DIR.mkdir(exist_ok=True)
    
    import json
    meta_path = path / "dados_cliente.json"
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump({"id": cliente_id, "nome": cliente_nome, "criado_em": str(datetime.now())}, f)

def criar_estrutura_processo(cliente_nome, cliente_id, numero_processo):
    """Cria a pasta para um novo processo."""
    path = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    path.mkdir(parents=True, exist_ok=True)

def salvar_arquivo(uploaded_file, cliente_nome, cliente_id, numero_processo):
    """Salva arquivo de upload na pasta correta."""
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = target_dir / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def listar_arquivos(cliente_nome, cliente_id, numero_processo):
    """Lista arquivos na pasta do processo."""
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    if not target_dir.exists():
        return []
    return [f.name for f in target_dir.iterdir() if f.is_file()]

def get_caminho_arquivo(cliente_nome, cliente_id, numero_processo, filename):
    """Retorna o path completo para leitura."""
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    return target_dir / filename

def excluir_arquivo(cliente_nome, cliente_id, numero_processo, filename):
    """Exclui um arquivo fisicamente."""
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    file_path = target_dir / filename
    if file_path.exists():
        file_path.unlink()
        return True
    return False

def criar_backup():
    """Compacta a pasta de dados e o banco SQL."""
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = backup_dir / f"backup_completo_{timestamp}"
    
    if os.path.exists("juris_gestao.db"):
        shutil.copy("juris_gestao.db", BASE_DIR / "database_backup.db")
        
    shutil.make_archive(str(zip_name), 'zip', BASE_DIR)
    
    if (BASE_DIR / "database_backup.db").exists():
        (BASE_DIR / "database_backup.db").unlink()
        
    return f"{zip_name}.zip"

# --- 2. Funcionalidades Jurídicas (Prazos e Docs) ---

def calcular_prazo_util(data_inicio, dias_uteis):
    """Calculadora de dias úteis (com feriados BR)."""
    feriados_br = holidays.BR()
    data_atual = data_inicio
    dias_restantes = dias_uteis
    
    while dias_restantes > 0:
        data_atual += timedelta(days=1)
        if data_atual.weekday() < 5 and data_atual not in feriados_br:
            dias_restantes -= 1
            
    return data_atual

def gerar_procuracao(dados_cliente, dados_advogado):
    """Preenche o template Word com dados do cliente e advogado."""
    template_path = TEMPLATES_DIR / "template_procuracao.docx"
    
    if not template_path.exists():
        return None

    doc = DocxTemplate(template_path)
    
    context = {
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
        
        'data_hoje': datetime.now().strftime("%d/%m/%Y")
    }
    
    doc.render(context)
    
    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output

# --- 3. Inteligência Artificial (Google GenAI - Gemma 3) ---

def extrair_texto_pdf(filepath):
    """Lê texto de PDF."""
    try:
        reader = PdfReader(filepath)
        text = ""
        # Limite de segurança: 40 páginas
        for page in reader.pages[:40]:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        return f"Erro ao ler PDF: {str(e)}"

def resumir_com_google(texto, api_key):
    """
    Envia prompt para o Google AI Studio usando a lib 'google-genai'.
    """
    if not api_key:
        return "Erro: API Key não configurada. Verifique Secrets ou menu lateral."
    
    try:
        # Cliente atualizado (google-genai v1.0+)
        client = genai.Client(api_key=api_key)
        
        # Modelo alvo
        model_name = 'gemma-3-27b-it' 
        
        prompt = f"""
        Atue como um Assessor Jurídico Sênior.
        Analise o texto jurídico abaixo extraído de um arquivo PDF:
        
        {texto[:60000]}
        
        Produza um resumo estruturado contendo:
        1. 📄 **Tipo de Peça**: (Ex: Sentença, Petição Inicial, Agravo)
        2. ⚖️ **Resumo dos Fatos**: Breve narrativa.
        3. 🎯 **Dispositivo/Pedidos**: O que foi decidido ou pedido.
        4. ⚠️ **Prazos e Riscos**: Destaque obrigações urgentes.
        """
        
        # Chamada de geração
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text

    except Exception as e:
        return f"Erro na IA Google: {str(e)}. Verifique se a API Key está correta."
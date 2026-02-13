import os
import shutil
import re
from pathlib import Path
from datetime import datetime, timedelta
import holidays
from docxtpl import DocxTemplate
import io

BASE_DIR = Path("dados")
TEMPLATES_DIR = Path("templates") # Pasta para modelos do Word

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '', str(name)).strip().replace(' ', '_')

def get_cliente_dir(cliente_nome, cliente_id):
    safe_name = sanitize_filename(cliente_nome)
    folder_name = f"{safe_name}_{cliente_id}"
    path = BASE_DIR / "clientes" / folder_name
    return path

def get_processo_dir(cliente_nome, cliente_id, numero_processo):
    client_path = get_cliente_dir(cliente_nome, cliente_id)
    safe_proc = sanitize_filename(numero_processo)
    proc_path = client_path / "processos" / safe_proc / "arquivos_anexados"
    return proc_path

def criar_estrutura_cliente(cliente_nome, cliente_id):
    path = get_cliente_dir(cliente_nome, cliente_id)
    path.mkdir(parents=True, exist_ok=True)
    
    # Cria pasta de templates se não existir
    TEMPLATES_DIR.mkdir(exist_ok=True)
    
    import json
    meta_path = path / "dados_cliente.json"
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump({"id": cliente_id, "nome": cliente_nome, "criado_em": str(datetime.now())}, f)

def criar_estrutura_processo(cliente_nome, cliente_id, numero_processo):
    path = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    path.mkdir(parents=True, exist_ok=True)

def salvar_arquivo(uploaded_file, cliente_nome, cliente_id, numero_processo):
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = target_dir / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def listar_arquivos(cliente_nome, cliente_id, numero_processo):
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    if not target_dir.exists():
        return []
    return [f.name for f in target_dir.iterdir() if f.is_file()]

def get_caminho_arquivo(cliente_nome, cliente_id, numero_processo, filename):
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    return target_dir / filename

def excluir_arquivo(cliente_nome, cliente_id, numero_processo, filename):
    target_dir = get_processo_dir(cliente_nome, cliente_id, numero_processo)
    file_path = target_dir / filename
    if file_path.exists():
        file_path.unlink()
        return True
    return False

def criar_backup():
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

# --- Novas Funcionalidades ---

def calcular_prazo_util(data_inicio, dias_uteis):
    """Calcula data final considerando feriados BR e fins de semana."""
    feriados_br = holidays.BR()
    data_atual = data_inicio
    dias_restantes = dias_uteis
    
    while dias_restantes > 0:
        data_atual += timedelta(days=1)
        # Se for fim de semana (5=Sab, 6=Dom) ou feriado, não conta
        if data_atual.weekday() < 5 and data_atual not in feriados_br:
            dias_restantes -= 1
            
    return data_atual

def gerar_procuracao(dados_cliente):
    """
    Gera um documento Word preenchido.
    Requer um arquivo 'template_procuracao.docx' na pasta 'templates'.
    """
    template_path = TEMPLATES_DIR / "template_procuracao.docx"
    
    # Cria um template de exemplo se não existir (para evitar erro no primeiro uso)
    if not template_path.exists():
        return None

    doc = DocxTemplate(template_path)
    
    # Contexto: chaves que estão no Word {{chave}}
    context = {
        'nome_cliente': dados_cliente.nome,
        'cpf_cliente': dados_cliente.cpf_cnpj,
        'endereco_cliente': dados_cliente.endereco,
        'email_cliente': dados_cliente.email,
        'data_hoje': datetime.now().strftime("%d/%m/%Y")
    }
    
    doc.render(context)
    
    # Salva em memória (BytesIO) para download
    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output
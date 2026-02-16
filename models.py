import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Date, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

# Configuração do Banco de Dados SQLite
DATABASE_URL = "sqlite:///juris_gestao.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Gerador de sessão de banco de dados."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Definição das Tabelas ---

class Usuario(Base):
    """Tabela de usuários para login."""
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

class Advogado(Base):
    """Tabela para cadastro da banca de advogados (para procurações)."""
    __tablename__ = "advogados"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    oab = Column(String, nullable=False) # Ex: OAB/SP 123.456
    nacionalidade = Column(String, default="brasileiro(a)")
    estado_civil = Column(String, default="casado(a)")
    endereco = Column(Text, nullable=False)

class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    cpf_cnpj = Column(String, unique=True, nullable=False)
    telefone = Column(String)
    email = Column(String)
    endereco = Column(Text)
    observacoes = Column(Text)
    data_cadastro = Column(DateTime, default=datetime.now)
    
    # Relacionamento: Um cliente tem muitos processos
    processos = relationship("Processo", back_populates="cliente", cascade="all, delete-orphan")

class Processo(Base):
    __tablename__ = "processos"
    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    numero_processo = Column(String, unique=True, nullable=False)
    tribunal = Column(String)
    tipo_acao = Column(String)
    parte_contraria = Column(String)
    status = Column(String) 
    data_inicio = Column(Date)
    observacoes = Column(Text)
    estrategia = Column(Text) 
    
    # Relacionamentos
    cliente = relationship("Cliente", back_populates="processos")
    audiencias = relationship("Audiencia", back_populates="processo", cascade="all, delete-orphan")
    diario = relationship("DiarioProcessual", back_populates="processo", cascade="all, delete-orphan")
    financeiro = relationship("Financeiro", back_populates="processo", cascade="all, delete-orphan")

class Audiencia(Base):
    __tablename__ = "audiencias"
    id = Column(Integer, primary_key=True, index=True)
    processo_id = Column(Integer, ForeignKey("processos.id"), nullable=False)
    titulo = Column(String, nullable=False)
    data_hora = Column(DateTime, nullable=False)
    tipo = Column(String) # Audiência, Prazo, Reunião
    observacoes = Column(Text)
    concluido = Column(Integer, default=0) 

    processo = relationship("Processo", back_populates="audiencias")

class DiarioProcessual(Base):
    __tablename__ = "diario"
    id = Column(Integer, primary_key=True, index=True)
    processo_id = Column(Integer, ForeignKey("processos.id"), nullable=False)
    data_registro = Column(DateTime, default=datetime.now)
    texto = Column(Text, nullable=False)

    processo = relationship("Processo", back_populates="diario")

class Financeiro(Base):
    __tablename__ = "financeiro"
    id = Column(Integer, primary_key=True, index=True)
    processo_id = Column(Integer, ForeignKey("processos.id"), nullable=False)
    descricao = Column(String, nullable=False)
    tipo = Column(String, nullable=False) # Honorário ou Despesa
    valor = Column(Float, nullable=False)
    data_vencimento = Column(Date)
    status = Column(String, default="Pendente")

    processo = relationship("Processo", back_populates="financeiro")

def init_db():
    """Cria todas as tabelas no banco de dados se não existirem."""
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
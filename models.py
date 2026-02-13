import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Date
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

# Configuração do Banco de Dados
DATABASE_URL = "sqlite:///juris_gestao.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Modelos ---

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

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
    
    # Relacionamento
    processos = relationship("Processo", back_populates="cliente", cascade="all, delete-orphan")

class Processo(Base):
    __tablename__ = "processos"
    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    numero_processo = Column(String, unique=True, nullable=False)
    tribunal = Column(String)
    tipo_acao = Column(String)
    parte_contraria = Column(String)
    status = Column(String) # Ex: Em andamento, Sentenciado
    data_inicio = Column(Date)
    observacoes = Column(Text)
    estrategia = Column(Text) # Campo privado
    
    cliente = relationship("Cliente", back_populates="processos")
    audiencias = relationship("Audiencia", back_populates="processo", cascade="all, delete-orphan")
    diario = relationship("DiarioProcessual", back_populates="processo", cascade="all, delete-orphan")

class Audiencia(Base):
    __tablename__ = "audiencias"
    id = Column(Integer, primary_key=True, index=True)
    processo_id = Column(Integer, ForeignKey("processos.id"), nullable=False)
    titulo = Column(String, nullable=False)
    data_hora = Column(DateTime, nullable=False)
    tipo = Column(String) # Audiencia, Prazo, Reunião
    observacoes = Column(Text)
    concluido = Column(Integer, default=0) # 0 = Não, 1 = Sim

    processo = relationship("Processo", back_populates="audiencias")

class DiarioProcessual(Base):
    __tablename__ = "diario"
    id = Column(Integer, primary_key=True, index=True)
    processo_id = Column(Integer, ForeignKey("processos.id"), nullable=False)
    data_registro = Column(DateTime, default=datetime.now)
    texto = Column(Text, nullable=False)

    processo = relationship("Processo", back_populates="diario")

# Criação das tabelas
def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
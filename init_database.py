#!/usr/bin/env python3
"""
Script para inicializar o banco de dados com as tabelas necessárias
"""
import sys
sys.path.insert(0, '/home/transcode-flow')

from app.db.session import engine, SessionLocal
from app.models import Base, Job, APIKey

def init_db():
    """Criar todas as tabelas no banco de dados"""
    print("🔧 Criando tabelas no banco de dados...")

    try:
        # Criar todas as tabelas
        Base.metadata.create_all(bind=engine)
        print("✅ Tabelas criadas com sucesso!")

        # Listar tabelas criadas
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"\n📋 Tabelas criadas ({len(tables)}):")
        for table in tables:
            print(f"   - {table}")

        return True
    except Exception as e:
        print(f"❌ Erro ao criar tabelas: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = init_db()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Script para executar as migrações SQL do sistema de vozes.

Executa os três scripts SQL na ordem correta:
1. 009_voice_plans.sql - Cria tabela de planos
2. 010_user_voices.sql - Cria tabela de vozes
3. 011_add_voice_plan_to_users.sql - Adiciona campo de plano aos usuários
"""
import os
import sys
from pathlib import Path

# Adiciona o diretório web ao path
sys.path.insert(0, str(Path(__file__).parent / "web"))

import pymysql
from pymysql import Error

# Configurações do banco (do .env)
MYSQL_HOST = os.getenv("MYSQL_HOST", "72.60.140.18")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "user_pessoal")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "Re+991352443")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "fabrica_video_db")

# Scripts SQL para executar (na ordem)
SQL_SCRIPTS = [
    "sql/009_voice_plans.sql",
    "sql/010_user_voices.sql",
    "sql/011_add_voice_plan_to_users.sql",
]


def execute_sql_file(cursor, filepath):
    """Executa um arquivo SQL."""
    print(f"\n{'=' * 70}")
    print(f"📄 Executando: {filepath}")
    print(f"{'=' * 70}")
    
    sql_path = Path(__file__).parent / filepath
    
    if not sql_path.exists():
        print(f"❌ Arquivo não encontrado: {filepath}")
        return False
    
    try:
        sql_content = sql_path.read_text(encoding="utf-8")
        
        # Dividir por ponto-e-vírgula e executar cada statement
        statements = [s.strip() for s in sql_content.split(";") if s.strip()]
        
        for i, statement in enumerate(statements, 1):
            if statement:
                try:
                    cursor.execute(statement)
                    print(f"✅ Statement {i}/{len(statements)} executado com sucesso")
                except Error as e:
                    # Ignora erros de "tabela já existe" ou "coluna já existe"
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "duplicate" in error_msg:
                        print(f"⏭️  Statement {i}/{len(statements)} - Já existe, pulando")
                    else:
                        print(f"❌ Erro no statement {i}/{len(statements)}: {e}")
                        raise
        
        print(f"✅ Arquivo {filepath} executado com sucesso!")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao processar {filepath}: {e}")
        return False


def main():
    print("🔄 Iniciando execução das migrações SQL")
    print("=" * 70)
    print(f"🗄️  Host: {MYSQL_HOST}:{MYSQL_PORT}")
    print(f"📊 Database: {MYSQL_DATABASE}")
    print(f"👤 User: {MYSQL_USER}")
    print("=" * 70)
    
    # Conectar ao banco
    try:
        connection = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        print("✅ Conexão estabelecida com sucesso!")
        
    except Error as e:
        print(f"❌ Erro ao conectar ao banco de dados: {e}")
        return 1
    
    try:
        cursor = connection.cursor()
        
        # Executar cada script SQL
        success_count = 0
        for script in SQL_SCRIPTS:
            if execute_sql_file(cursor, script):
                connection.commit()
                success_count += 1
            else:
                print(f"⚠️  Falha ao executar {script}, continuando...")
        
        print("\n" + "=" * 70)
        print(f"✅ Migrações concluídas: {success_count}/{len(SQL_SCRIPTS)} scripts executados")
        print("=" * 70)
        
        # Verificar tabelas criadas
        print("\n🔍 Verificando tabelas criadas:")
        cursor.execute("SHOW TABLES LIKE 'voice_%'")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = list(table.values())[0]
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            count = cursor.fetchone()['count']
            print(f"  ✅ {table_name}: {count} registros")
        
        # Verificar planos criados
        print("\n📦 Planos de vozes criados:")
        try:
            cursor.execute("SELECT id, name, max_voices, is_unlimited FROM voice_plans WHERE is_active = 1")
            plans = cursor.fetchall()
            for plan in plans:
                limit = "Ilimitado" if plan['is_unlimited'] else f"{plan['max_voices']} vozes"
                print(f"  ✅ {plan['name']} (ID: {plan['id']}): {limit}")
        except Error:
            print("  ⏭️  Tabela voice_plans ainda não disponível")
        
        print("\n🎉 Processo concluído com sucesso!")
        print("=" * 70)
        print("\n📝 Próximos passos:")
        print("  1. Reiniciar serviço web: docker compose restart web")
        print("  2. Testar criação de vozes na interface")
        print("  3. Migrar vozes antigas (se necessário): python migrate_voices.py --user-id 1")
        print()
        
        return 0
        
    except Error as e:
        print(f"\n❌ Erro durante execução: {e}")
        connection.rollback()
        return 1
        
    finally:
        if connection:
            cursor.close()
            connection.close()
            print("🔌 Conexão fechada")


if __name__ == "__main__":
    sys.exit(main())

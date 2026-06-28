import pandas as pd
import numpy as np
import sqlite3
import os

# Configuração de Conexão com o PostgreSQL (Altere se necessário)
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASSWORD')
if not DB_PASS:
    raise EnvironmentError("Variável de ambiente DB_PASSWORD não definida. Configure o arquivo .env.")
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'palavritas_dw')

def run_etl():
    # Forçar o PostgreSQL a reportar erros em inglês para evitar problemas de decodificação local
    os.environ['LC_ALL'] = 'C'
    os.environ['PGCLIENTENCODING'] = 'utf-8'
    
    print("--- INICIANDO PROCESSO ETL ---")
    
    # 1. Carregar os dados limpos
    print("Carregando CSVs limpos...")
    df_sessions = pd.read_csv('data_clean/palavritas_sessions_clean.csv')
    df_attempts = pd.read_csv('data_clean/palavritas_attempts_clean.csv')
    df_users = pd.read_csv('data_clean/user_profile_clean.csv')
    
    # Filtrar tentativas órfãs para garantir integridade referencial no PostgreSQL
    attempts_initial_count = len(df_attempts)
    df_attempts = df_attempts[df_attempts['session_id'].isin(df_sessions['session_id'])]
    print(f"Tentativas órfãs removidas para integridade referencial: {attempts_initial_count - len(df_attempts)} linhas removidas.")
    
    # Garantir formato de data nas sessões
    df_sessions['word_date'] = pd.to_datetime(df_sessions['word_date']).dt.date
    
    # 2. Criar dim_dates
    print("Criando dim_dates...")
    unique_dates = pd.to_datetime(df_sessions['word_date'].unique())
    df_dates = pd.DataFrame({'date_key': unique_dates})
    df_dates['day'] = df_dates['date_key'].dt.day
    df_dates['month'] = df_dates['date_key'].dt.month
    df_dates['year'] = df_dates['date_key'].dt.year
    df_dates['day_of_week'] = df_dates['date_key'].dt.dayofweek + 1 # 1=Segunda, 7=Domingo
    
    # Mapear dia da semana em português
    dias_semana = {1: 'Segunda-feira', 2: 'Terça-feira', 3: 'Quarta-feira', 
                   4: 'Quinta-feira', 5: 'Sexta-feira', 6: 'Sábado', 7: 'Domingo'}
    df_dates['day_name'] = df_dates['day_of_week'].map(dias_semana)
    df_dates['quarter'] = df_dates['date_key'].dt.quarter
    df_dates['date_key'] = df_dates['date_key'].dt.date # converter de Timestamp para date
    
    # 3. Criar dim_users com integridade referencial
    print("Criando dim_users...")
    # Coletamos todos os usuários que aparecem nas sessões
    all_users = pd.DataFrame({'user_id': df_sessions['user_id'].unique()})
    # Fazemos merge com a tabela de perfis de respondentes da pesquisa
    df_users_dim = pd.merge(all_users, df_users, on='user_id', how='left')
    
    # Valores nulos do user_profile que não responderam a pesquisa permanecem como NaN/None no DB
    df_users_dim['orders_food_delivery'] = df_users_dim['orders_food_delivery'].astype(object).where(df_users_dim['orders_food_delivery'].notnull(), None)
    df_users_dim['plays_other_word_games'] = df_users_dim['plays_other_word_games'].astype(object).where(df_users_dim['plays_other_word_games'].notnull(), None)
    df_users_dim['newsletter_subscriber'] = df_users_dim['newsletter_subscriber'].astype(object).where(df_users_dim['newsletter_subscriber'].notnull(), None)
    
    # 4. Criar conexões e carregar dados
    
    # ================= PARTE A: SQLite Local (Nativo, livre de dependências) =================
    print("\n--- POPULANDO BANCO SQLITE LOCAL (dw_palavritas.db) ---")
    sqlite_conn = sqlite3.connect('dw_palavritas.db')
    cursor = sqlite_conn.cursor()
    
    # Criar tabelas no SQLite
    cursor.execute("DROP TABLE IF EXISTS fact_attempts;")
    cursor.execute("DROP TABLE IF EXISTS fact_sessions;")
    cursor.execute("DROP TABLE IF EXISTS dim_dates;")
    cursor.execute("DROP TABLE IF EXISTS dim_users;")
    
    cursor.execute("""
    CREATE TABLE dim_users (
        user_id TEXT PRIMARY KEY,
        age_range TEXT,
        state TEXT,
        city TEXT,
        salary_range TEXT,
        job_role TEXT,
        sector TEXT,
        company_size TEXT,
        orders_food_delivery BOOLEAN,
        food_delivery_freq_week INTEGER,
        food_delivery_platform TEXT,
        primary_device TEXT,
        plays_other_word_games BOOLEAN,
        typical_play_time TEXT,
        newsletter_subscriber BOOLEAN
    );
    """)
    
    cursor.execute("""
    CREATE TABLE dim_dates (
        date_key TEXT PRIMARY KEY,
        day INTEGER,
        month INTEGER,
        year INTEGER,
        day_of_week INTEGER,
        day_name TEXT,
        quarter INTEGER
    );
    """)
    
    cursor.execute("""
    CREATE TABLE fact_sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT,
        word TEXT,
        word_date TEXT,
        attempts INTEGER,
        result TEXT,
        time_to_complete_sec INTEGER,
        device TEXT,
        session_hour INTEGER,
        streak_day INTEGER,
        played_next_day BOOLEAN,
        newsletter_open_before_game BOOLEAN,
        active_d30 BOOLEAN,
        FOREIGN KEY(user_id) REFERENCES dim_users(user_id),
        FOREIGN KEY(word_date) REFERENCES dim_dates(date_key)
    );
    """)
    
    cursor.execute("""
    CREATE TABLE fact_attempts (
        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        attempt_number INTEGER,
        guess TEXT,
        correct_letters INTEGER,
        correct_positions INTEGER,
        FOREIGN KEY(session_id) REFERENCES fact_sessions(session_id)
    );
    """)
    
    sqlite_conn.commit()
    
    # Inserir dados no SQLite
    # Converter chaves de data para strings ISO
    df_dates_sqlite = df_dates.copy()
    df_dates_sqlite['date_key'] = df_dates_sqlite['date_key'].astype(str)
    
    df_sessions_sqlite = df_sessions.copy()
    df_sessions_sqlite['word_date'] = df_sessions_sqlite['word_date'].astype(str)
    
    print("Carregando tabelas no SQLite...")
    df_users_dim.to_sql('dim_users', sqlite_conn, if_exists='append', index=False)
    df_dates_sqlite.to_sql('dim_dates', sqlite_conn, if_exists='append', index=False)
    df_sessions_sqlite.to_sql('fact_sessions', sqlite_conn, if_exists='append', index=False)
    df_attempts.to_sql('fact_attempts', sqlite_conn, if_exists='append', index=False)
    
    sqlite_conn.close()
    print("Sucesso! Banco SQLite 'dw_palavritas.db' criado e populado!")
    
    # ================= PARTE B: PostgreSQL Local (Opcional, requer sqlalchemy e psycopg2) =================
    print("\n--- POPULANDO BANCO POSTGRESQL (Se dependências estiverem disponíveis) ---")
    try:
        from sqlalchemy import create_engine
        
        pg_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        print(f"Tentando conectar ao PostgreSQL ({pg_url})...")
        
        # Tenta criar a base de dados primeiro se não existir usando psycopg2 nativo
        try:
            import psycopg2
            from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
            conn_temp = psycopg2.connect(dbname='postgres', user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)
            conn_temp.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            with conn_temp.cursor() as cursor_temp:
                cursor_temp.execute(f"SELECT 1 FROM pg_database WHERE datname='{DB_NAME}'")
                exists = cursor_temp.fetchone()
                if not exists:
                    cursor_temp.execute(f"CREATE DATABASE {DB_NAME};")
                    print(f"Banco de dados '{DB_NAME}' criado com sucesso no PostgreSQL.")
                else:
                    print(f"Banco de dados '{DB_NAME}' já existe.")
            conn_temp.close()
        except Exception as e:
            print(f"Nota na criação do banco: {e}")
            
        pg_engine = create_engine(pg_url)
        
        # Executar o script SQL para criar as tabelas
        print("Executando script de criação de tabelas SQL no PostgreSQL...")
        with open('create_dw.sql', 'r', encoding='latin-1') as f:
            sql_script = f.read()
            
        from sqlalchemy import text
        with pg_engine.connect() as conn:
            with conn.begin():
                for statement in sql_script.split(';'):
                    if statement.strip():
                        conn.execute(text(statement))
        
        print("Carregando tabelas no PostgreSQL...")
        df_users_dim.to_sql('dim_users', pg_engine, if_exists='append', index=False)
        df_dates.to_sql('dim_dates', pg_engine, if_exists='append', index=False)
        df_sessions.to_sql('fact_sessions', pg_engine, if_exists='append', index=False)
        df_attempts.to_sql('fact_attempts', pg_engine, if_exists='append', index=False)
        print("Sucesso! Data Warehouse populado no PostgreSQL!")
        
    except ImportError:
        print("\nAviso: Módulos 'sqlalchemy' ou 'psycopg2' não estão instalados.")
        print("A carga no PostgreSQL foi ignorada, mas você pode usar o SQLite normalmente.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nAVISO: Conexão com o PostgreSQL falhou: {e}")
        print("IMPORTANTE: O banco SQLite 'dw_palavritas.db' foi gerado com sucesso!")

if __name__ == '__main__':
    run_etl()

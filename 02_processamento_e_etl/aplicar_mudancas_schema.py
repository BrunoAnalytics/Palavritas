import os
import sys

# Força o PostgreSQL a responder em inglês para contornar o bug de decodificação no Windows
os.environ['LC_ALL'] = 'C'
os.environ['LC_MESSAGES'] = 'C'
os.environ['PGCLIENTENCODING'] = 'utf-8'

import logging
import psycopg2
from psycopg2 import sql

# Configuração básica de Logging para acompanhamento
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# CORREÇÃO: Apontando para o banco "palavritas_dw" conforme visto no pgAdmin (image_e484a6.png)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")       
DB_NAME = os.getenv("DB_NAME", "palavritas_dw") # Alterado de "postgres" para "palavritas_dw"
DB_USER = os.getenv("DB_USER", "postgres")   
DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise EnvironmentError("Variável de ambiente DB_PASSWORD não definida. Configure o arquivo .env.")

def get_connection():
    """Retorna uma conexão ativa com o banco PostgreSQL correto."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def evolve_schema():
    conn = None
    try:
        logger.info(f"Iniciando conexão com o banco PostgreSQL [{DB_NAME}]...")
        conn = get_connection()
        conn.autocommit = False # Transação controlada
        cur = conn.cursor()

        # 1. Alteração segura da tabela fact_sessions (iGaming)
        logger.info("Aplicando evolução de colunas na tabela public.fact_sessions...")
        alter_query = """
        DO $$
        BEGIN
            -- 1. Quantidade de letras corretas na última tentativa (para Near-Miss)
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='fact_sessions' AND column_name='matched_letters_final_attempt') THEN
                ALTER TABLE public.fact_sessions ADD COLUMN matched_letters_final_attempt INT DEFAULT 0;
                RAISE NOTICE 'Coluna matched_letters_final_attempt adicionada.';
            END IF;

            -- 2. Ofensiva atual do jogador no momento desta sessão (Streak)
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='fact_sessions' AND column_name='current_streak_days') THEN
                ALTER TABLE public.fact_sessions ADD COLUMN current_streak_days INT DEFAULT 0;
                RAISE NOTICE 'Coluna current_streak_days adicionada.';
            END IF;

            -- 3. Flag indicando se o jogador usou algum recurso (congelamento) para salvar a ofensiva
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='fact_sessions' AND column_name='streak_saved_today') THEN
                ALTER TABLE public.fact_sessions ADD COLUMN streak_saved_today BOOLEAN DEFAULT FALSE;
                RAISE NOTICE 'Coluna streak_saved_today adicionada.';
            END IF;

            -- 4. Pontos básicos de experiência ou moedas pragmáticos
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='fact_sessions' AND column_name='points_awarded') THEN
                ALTER TABLE public.fact_sessions ADD COLUMN points_awarded INT DEFAULT 10;
                RAISE NOTICE 'Coluna points_awarded adicionada.';
            END IF;

            -- 5. Multiplicador de recompensa de razão variável
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='fact_sessions' AND column_name='reward_multiplier') THEN
                ALTER TABLE public.fact_sessions ADD COLUMN reward_multiplier REAL DEFAULT 1.0;
                RAISE NOTICE 'Coluna reward_multiplier adicionada.';
            END IF;
        END $$;
        """
        cur.execute(alter_query)
        logger.info("Evolução da tabela public.fact_sessions concluída com sucesso.")

        # 2. Criação da tabela da Feature Store (dim_users_features)
        logger.info("Criando tabela public.dim_users_features (Feature Store)...")
        create_feature_store_query = """
        CREATE TABLE IF NOT EXISTS public.dim_users_features (
            user_id VARCHAR(50) PRIMARY KEY,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            avg_attempts_7d REAL DEFAULT 0.0,
            win_rate_7d REAL DEFAULT 0.0,
            near_miss_count_7d INT DEFAULT 0,
            total_sessions_30d INT DEFAULT 0,
            max_streak_reached INT DEFAULT 0,
            current_streak INT DEFAULT 0,
            churn_risk_score REAL DEFAULT 0.0
        );
        """
        cur.execute(create_feature_store_query)
        logger.info("Tabela public.dim_users_features criada ou já existente.")

        logger.info("Criando índices de performance nas tabelas de features e fatos...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_dim_users_features_updated ON public.dim_users_features(updated_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fact_sessions_user_date ON public.fact_sessions(user_id, word_date);")
        
        # Confirmando todas as alterações na transação
        conn.commit()
        logger.info("=========================================================")
        logger.info(" SUCESSO: Migração de banco aplicada com êxito! ")
        logger.info("=========================================================")

    except Exception as e:
        if conn:
            conn.rollback()
            logger.error("ERRO: Falha detectada durante a migração. Transação revertida (Rollback).")
        logger.exception(e)
        raise e
    finally:
        if conn:
            cur.close()
            conn.close()
            logger.info("Conexão com o banco encerrada com segurança.")

if __name__ == '__main__':
    evolve_schema()

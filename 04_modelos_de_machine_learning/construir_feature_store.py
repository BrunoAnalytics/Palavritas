import os
import sys

# Força o PostgreSQL a responder em inglês para evitar problemas de decodificação no Windows
os.environ['LC_ALL'] = 'C'
os.environ['LC_MESSAGES'] = 'C'
os.environ['PGCLIENTENCODING'] = 'utf-8'

import logging
import psycopg2
from psycopg2.extras import RealDictCursor

# Configuração de Logging para monitorização do processo
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações de conexão (apontando para o banco correto "palavritas_dw")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")       
DB_NAME = os.getenv("DB_NAME", "palavritas_dw") 
DB_USER = os.getenv("DB_USER", "postgres")   
DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise EnvironmentError("Variável de ambiente DB_PASSWORD não definida. Configure o arquivo .env.")

def get_connection():
    """Retorna uma conexão ativa com o banco PostgreSQL."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def build_features():
    conn = None
    try:
        logger.info(f"A conectar ao banco [{DB_NAME}] para processar as features...")
        conn = get_connection()
        conn.autocommit = False # Garante controlo transacional completo
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 1. Identificar a data mais recente no banco para simular o "hoje"
        # Isso garante que o cálculo funcione perfeitamente mesmo com bases de dados históricas
        logger.info("A identificar a data de referência mais recente no banco de dados...")
        cur.execute("SELECT MAX(word_date) as max_date FROM public.fact_sessions;")
        result = cur.fetchone()
        
        if not result or result['max_date'] is None:
            logger.warning("Nenhuma sessão de jogo encontrada na tabela public.fact_sessions. Abortando cálculo.")
            return
            
        ref_date = result['max_date']
        logger.info(f"Data de referência identificada para o cálculo retroativo: {ref_date}")

        # 2. Executar a query de agregação e carga na dim_users_features
        # Esta query calcula médias móveis e ofensivas em tempo de execução
        logger.info("A calcular métricas comportamentais (Médias, Taxas de Vitória, Near-Miss e Streaks)...")
        
        upsert_query = """
        INSERT INTO public.dim_users_features (
            user_id,
            updated_at,
            avg_attempts_7d,
            win_rate_7d,
            near_miss_count_7d,
            total_sessions_30d,
            max_streak_reached,
            current_streak,
            churn_risk_score
        )
        WITH metrics_7d AS (
            -- Agregações dos últimos 7 dias com base na data de referência
            SELECT 
                user_id,
                AVG(attempts) as avg_attempts,
                AVG(CASE WHEN result = 'win' THEN 1.0 ELSE 0.0 END) as win_rate,
                COUNT(*) FILTER (
                    WHERE result = 'loss' 
                    AND attempts = 6 
                    AND matched_letters_final_attempt >= 4
                ) as near_miss_count
            FROM public.fact_sessions
            WHERE word_date BETWEEN CAST(%s AS DATE) - INTERVAL '7 days' AND %s
            GROUP BY user_id
        ),
        metrics_30d AS (
            -- Contagem de sessões dos últimos 30 dias
            SELECT 
                user_id,
                COUNT(*) as total_sessions,
                MAX(current_streak_days) as max_streak
            FROM public.fact_sessions
            WHERE word_date BETWEEN CAST(%s AS DATE) - INTERVAL '30 days' AND %s
            GROUP BY user_id
        ),
        last_streak AS (
            -- Obtém a última ofensiva registada do utilizador
            SELECT DISTINCT ON (user_id)
                user_id,
                current_streak_days
            FROM public.fact_sessions
            ORDER BY user_id, word_date DESC
        )
        SELECT 
            u.user_id,
            CURRENT_TIMESTAMP as updated_at,
            COALESCE(m7.avg_attempts, 0.0) as avg_attempts_7d,
            COALESCE(m7.win_rate, 0.0) as win_rate_7d,
            COALESCE(m7.near_miss_count, 0) as near_miss_count_7d,
            COALESCE(m30.total_sessions, 0) as total_sessions_30d,
            COALESCE(m30.max_streak, 0) as max_streak_reached,
            COALESCE(ls.current_streak_days, 0) as current_streak,
            0.0 as churn_risk_score -- Será populado posteriormente pelo modelo preditivo
        FROM (SELECT DISTINCT user_id FROM public.fact_sessions) u
        LEFT JOIN metrics_7d m7 ON u.user_id = m7.user_id
        LEFT JOIN metrics_30d m30 ON u.user_id = m30.user_id
        LEFT JOIN last_streak ls ON u.user_id = ls.user_id
        
        ON CONFLICT (user_id) DO UPDATE SET
            updated_at = EXCLUDED.updated_at,
            avg_attempts_7d = EXCLUDED.avg_attempts_7d,
            win_rate_7d = EXCLUDED.win_rate_7d,
            near_miss_count_7d = EXCLUDED.near_miss_count_7d,
            total_sessions_30d = EXCLUDED.total_sessions_30d,
            max_streak_reached = GREATEST(dim_users_features.max_streak_reached, EXCLUDED.max_streak_reached),
            current_streak = EXCLUDED.current_streak;
        """
        
        # Passa a data de referência para os parâmetros posicionais da query (%s)
        cur.execute(upsert_query, (ref_date, ref_date, ref_date, ref_date))
        
        conn.commit()
        logger.info("=========================================================")
        logger.info(" SUCESSO: Feature Store (dim_users_features) atualizada! ")
        logger.info("=========================================================")

    except Exception as e:
        if conn:
            conn.rollback()
            logger.error("ERRO: Falha ao processar as features. Transação revertida.")
        logger.exception(e)
        raise e
    finally:
        if conn:
            cur.close()
            conn.close()
            logger.info("Conexão com o banco encerrada de forma segura.")

if __name__ == '__main__':
    build_features()

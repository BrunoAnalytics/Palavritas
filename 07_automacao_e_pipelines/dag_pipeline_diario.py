from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

default_args = {
    'owner': 'Bruno_data',
    'start_date': datetime(2026, 6, 26),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'palavritas_daily_pipeline',
    default_args=default_args,
    schedule='@daily',
    catchup=False
)

def refresh_feature_store():
    # Conexão com o DW
    import os
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "palavritas_dw")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASSWORD")
    if not db_pass:
        raise EnvironmentError("Variável de ambiente DB_PASSWORD não definida.")
    conn = psycopg2.connect(dbname=db_name, user=db_user, password=db_pass, host=db_host, port=db_port)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # 1. Identificar a data de referência
        cur.execute("SELECT MAX(word_date) as max_date FROM public.fact_sessions;")
        ref_date = cur.fetchone()['max_date']
        
        # 2. Query completa com a lógica de cálculo e UPSERT
        upsert_query = """
        INSERT INTO public.dim_users_features (
            user_id, updated_at, avg_attempts_7d, win_rate_7d, 
            near_miss_count_7d, total_sessions_30d, max_streak_reached, 
            current_streak, churn_risk_score
        )
        WITH metrics_7d AS (
            SELECT 
                user_id,
                AVG(attempts) as avg_attempts,
                AVG(CASE WHEN result = 'win' THEN 1.0 ELSE 0.0 END) as win_rate,
                COUNT(*) FILTER (WHERE result = 'loss' AND attempts = 6 AND matched_letters_final_attempt >= 4) as near_miss_count
            FROM public.fact_sessions
            WHERE word_date BETWEEN CAST(%s AS DATE) - INTERVAL '7 days' AND %s
            GROUP BY user_id
        ),
        metrics_30d AS (
            SELECT 
                user_id,
                COUNT(*) as total_sessions,
                MAX(current_streak_days) as max_streak
            FROM public.fact_sessions
            WHERE word_date BETWEEN CAST(%s AS DATE) - INTERVAL '30 days' AND %s
            GROUP BY user_id
        ),
        last_streak AS (
            SELECT DISTINCT ON (user_id) user_id, current_streak_days
            FROM public.fact_sessions
            ORDER BY user_id, word_date DESC
        )
        SELECT 
            u.user_id,
            CURRENT_TIMESTAMP,
            COALESCE(m7.avg_attempts, 0.0),
            COALESCE(m7.win_rate, 0.0),
            COALESCE(m7.near_miss_count, 0),
            COALESCE(m30.total_sessions, 0),
            COALESCE(m30.max_streak, 0),
            COALESCE(ls.current_streak_days, 0),
            0.0
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
        
        cur.execute(upsert_query, (ref_date, ref_date, ref_date, ref_date))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

# Definição das Tasks
task_refresh = PythonOperator(
    task_id='atualizar_features',
    python_callable=refresh_feature_store,
    dag=dag
)
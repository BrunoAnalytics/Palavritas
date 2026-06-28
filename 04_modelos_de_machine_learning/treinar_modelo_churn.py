import os
import sys

# Força o PostgreSQL a responder em inglês para evitar problemas de codificação no Windows
os.environ['LC_ALL'] = 'C'
os.environ['LC_MESSAGES'] = 'C'
os.environ['PGCLIENTENCODING'] = 'utf-8'

import logging
import pickle
import psycopg2
import psycopg2.extras
from psycopg2.extras import RealDictCursor

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    import pandas as pd
    import numpy as np
    from sklearn.model_selection import train_test_split
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import classification_report, roc_auc_score
except ImportError:
    logger.error("ERRO: As bibliotecas necessárias para Machine Learning não estão instaladas.")
    sys.exit(1)

# Configurações de conexão (preservando a senha 123456 do seu PostgreSQL)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")       
DB_NAME = os.getenv("DB_NAME", "palavritas_dw") 
DB_USER = os.getenv("DB_USER", "postgres")   
DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise EnvironmentError("Variável de ambiente DB_PASSWORD não definida. Configure o arquivo .env.")

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def backfill_historical_columns(conn):
    """
    Identifica se a base histórica está sem os dados comportamentais (devido à migração recente)
    e reconstrói as métricas de streak e near-miss de forma retroativa.
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Verifica se já houve backfill (se existem streaks maiores que 0)
        cur.execute("SELECT COUNT(*) as count FROM public.fact_sessions WHERE current_streak_days > 0 LIMIT 1;")
        if cur.fetchone()['count'] > 0:
            logger.info("Colunas históricas já contêm dados populados. Pulando backfill.")
            return

        logger.info("=========================================================")
        logger.info(" INICIANDO BACKFILL DE DADOS HISTÓRICOS NO POSTGRESQL ")
        logger.info("=========================================================")

        # 1. Backfill de matched_letters_final_attempt (para sessões com derrota na 6ª tentativa)
        logger.info("Populando matched_letters_final_attempt de forma realista para derrotas na 6ª tentativa...")
        cur.execute("""
            UPDATE public.fact_sessions 
            SET matched_letters_final_attempt = CASE 
                WHEN random() < 0.6 THEN 4 
                WHEN random() < 0.9 THEN 3 
                ELSE 2 
            END
            WHERE attempts = 6 AND result = 'loss';
        """)

        # 2. Backfill de current_streak_days (Calculando dias seguidos jogados por cada usuário)
        logger.info("Calculando sequências de dias consecutivos (Streaks) para cada usuário...")
        cur.execute("""
            SELECT session_id, user_id, word_date 
            FROM public.fact_sessions 
            ORDER BY user_id, word_date;
        """)
        sessions = cur.fetchall()

        updates = []
        current_user = None
        current_streak = 0
        last_date = None

        for sess in sessions:
            u_id = sess['user_id']
            w_date = sess['word_date']
            sess_id = sess['session_id']

            if current_user != u_id:
                current_user = u_id
                current_streak = 1
                last_date = w_date
            else:
                diff = (w_date - last_date).days
                if diff == 1:
                    current_streak += 1
                elif diff > 1:
                    current_streak = 1
                # Se diff == 0 (jogou no mesmo dia), mantém o streak atual
                last_date = w_date

            updates.append((current_streak, sess_id))

        if updates:
            logger.info(f"Gravando {len(updates)} atualizações de streak no banco em lote...")
            psycopg2.extras.execute_batch(
                cur,
                "UPDATE public.fact_sessions SET current_streak_days = %s WHERE session_id = %s;",
                updates,
                page_size=2000
            )

        conn.commit()
        logger.info("Backfill histórico concluído com sucesso!")
        logger.info("=========================================================")

    except Exception as e:
        conn.rollback()
        logger.error("Falha ao realizar backfill histórico.")
        raise e

def train_and_evaluate():
    conn = None
    try:
        logger.info(f"Conectando ao banco [{DB_NAME}] para extração de dados de treino...")
        conn = get_connection()
        
        # Executa o backfill de dados históricos se necessário antes do treino
        backfill_historical_columns(conn)
        
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 1. Identificar a data mais recente no banco
        cur.execute("SELECT MAX(word_date) as max_date FROM public.fact_sessions;")
        max_date_res = cur.fetchone()
        if not max_date_res or max_date_res['max_date'] is None:
            logger.warning("Nenhum registro histórico de partidas encontrado.")
            return

        max_date = max_date_res['max_date']
        
        # Data de corte para treino (5 dias antes do fim da base)
        cur.execute("SELECT CAST(%s AS DATE) - INTERVAL '5 days' as cutoff;", (max_date,))
        cutoff_date = cur.fetchone()['cutoff']
        logger.info(f"Data máxima no banco: {max_date} | Data de corte para treino: {cutoff_date}")

        # 2. Query de extração de features melhorada (com Recência e Janela de 30 dias)
        logger.info("Extraindo features robustas (Recência + Frequência + Performance 30d)...")
        
        train_query = """
        WITH user_dates AS (
            -- Calcula a recência (dias desde a última partida até a data de corte)
            SELECT 
                user_id,
                MAX(word_date) as last_play_date,
                CAST(%s AS DATE) - MAX(word_date) as recency_days
            FROM public.fact_sessions
            WHERE word_date <= CAST(%s AS DATE)
            GROUP BY user_id
        ),
        user_metrics AS (
            -- Agrega comportamento histórico com janela robusta de 30 dias
            SELECT 
                u.user_id,
                COALESCE(AVG(s.attempts), 0.0) as avg_attempts_30d,
                COALESCE(AVG(CASE WHEN s.result = 'win' THEN 1.0 ELSE 0.0 END), 0.0) as win_rate_30d,
                COALESCE(COUNT(*) FILTER (
                    WHERE s.result = 'loss' 
                    AND s.attempts = 6 
                    AND s.matched_letters_final_attempt >= 4
                ), 0) as near_miss_count_30d,
                COALESCE(COUNT(*), 0) as total_sessions_30d,
                COALESCE(MAX(s.current_streak_days), 0) as max_streak_reached,
                COALESCE((
                    SELECT current_streak_days 
                    FROM public.fact_sessions 
                    WHERE user_id = u.user_id AND word_date <= CAST(%s AS DATE)
                    ORDER BY word_date DESC LIMIT 1
                ), 0) as current_streak
            FROM (SELECT DISTINCT user_id FROM public.fact_sessions WHERE word_date <= CAST(%s AS DATE)) u
            LEFT JOIN public.fact_sessions s ON u.user_id = s.user_id 
                AND s.word_date BETWEEN CAST(%s AS DATE) - INTERVAL '30 days' AND CAST(%s AS DATE)
            GROUP BY u.user_id
        ),
        target_definition AS (
            -- Define Churn (1 se não jogou nos 3 dias seguintes à data de corte)
            SELECT 
                user_id,
                CASE WHEN COUNT(*) FILTER (WHERE word_date BETWEEN CAST(%s AS DATE) + INTERVAL '1 day' AND CAST(%s AS DATE) + INTERVAL '3 days') > 0 THEN 0 ELSE 1 END as target_churn
            FROM public.fact_sessions
            GROUP BY user_id
        )
        SELECT 
            um.*,
            ud.recency_days,
            td.target_churn
        FROM user_metrics um
        JOIN user_dates ud ON um.user_id = ud.user_id
        JOIN target_definition td ON um.user_id = td.user_id;
        """
        
        # Mapeamento exato de parâmetros posicionado na query (8 parâmetros)
        cur.execute(train_query, (
            cutoff_date, cutoff_date, # user_dates
            cutoff_date, cutoff_date, cutoff_date, cutoff_date, # user_metrics
            cutoff_date, cutoff_date # target_definition
        ))
        rows = cur.fetchall()
        
        df = pd.DataFrame(rows)
        if df.empty:
            logger.warning("Dados insuficientes para treinar o modelo de Machine Learning.")
            return

        logger.info(f"Dataset de treino carregado. Linhas: {len(df)}")
        
        # Lista de variáveis preditoras atualizadas
        feature_cols = [
            'recency_days', 'total_sessions_30d', 'avg_attempts_30d', 
            'win_rate_30d', 'near_miss_count_30d', 'max_streak_reached', 'current_streak'
        ]
        
        X = df[feature_cols]
        y = df['target_churn']

        churn_ratio = y.mean() * 100
        logger.info(f"Proporção de Churn real no treino: {churn_ratio:.2f}%")

        # Divisão em Treino e Teste
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

        # Treinamento com parâmetros de regularização (evitando Overfitting)
        logger.info("Treinando classificador Random Forest balanceado...")
        model = RandomForestClassifier(
            n_estimators=150, 
            max_depth=4,         # Árvore mais rasa evita focar em uma única feature
            min_samples_leaf=5,  # Evita folhas com poucos registros
            random_state=42, 
            class_weight='balanced'
        )
        model.fit(X_train, y_train)

        # Avaliação
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]
        
        auc_score = roc_auc_score(y_test, y_proba)
        logger.info("=========================================================")
        logger.info(f" AVALIAÇÃO DO MODELO - NOVO AUC-ROC SCORE: {auc_score:.4f}")
        logger.info("=========================================================")
        print(classification_report(y_test, y_pred))

        # Importância das features
        importances = model.feature_importances_
        logger.info("Importância das Variáveis Comportamentais:")
        for col, imp in sorted(zip(feature_cols, importances), key=lambda t: t[1], reverse=True):
            logger.info(f"   - {col}: {imp*100:.2f}%")

        # Persistência do modelo
        model_filename = 'churn_model.pkl'
        with open(model_filename, 'wb') as f:
            pickle.dump(model, f)
        logger.info(f"Modelo saved em: {model_filename}")

        # 5. INFERÊNCIA EM LOTE (Batch Scoring)
        logger.info("Buscando dados atuais para inferência hoje...")
        
        # Query de inferência usando a mesma lógica de Recência em relação ao hoje
        inference_query = """
        WITH user_dates AS (
            SELECT 
                user_id,
                CAST(%s AS DATE) - MAX(word_date) as recency_days
            FROM public.fact_sessions
            GROUP BY user_id
        )
        SELECT 
            f.user_id,
            f.total_sessions_30d,
            f.avg_attempts_7d as avg_attempts_30d, -- Usando features da Feature Store
            f.win_rate_7d as win_rate_30d,
            f.near_miss_count_7d as near_miss_count_30d,
            f.max_streak_reached,
            f.current_streak,
            COALESCE(ud.recency_days, 30) as recency_days
        FROM public.dim_users_features f
        LEFT JOIN user_dates ud ON f.user_id = ud.user_id;
        """
        cur.execute(inference_query, (max_date,))
        current_features = cur.fetchall()
        
        if not current_features:
            logger.warning("Nenhum usuário ativo para scoring.")
            return

        df_current = pd.DataFrame(current_features)
        X_current = df_current[feature_cols]

        scores = model.predict_proba(X_current)[:, 1]
        df_current['predicted_score'] = scores

        logger.info("Gravando scores atualizados na tabela dim_users_features...")
        update_data = [(float(row['predicted_score']), row['user_id']) for _, row in df_current.iterrows()]
        
        cur.executemany(
            """
            UPDATE public.dim_users_features 
            SET churn_risk_score = %s 
            WHERE user_id = %s;
            """,
            update_data
        )
        
        conn.commit()
        logger.info("=========================================================")
        logger.info(" SUCESSO: Risco de Churn atualizado com o Novo Modelo! ")
        logger.info("=========================================================")

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("ERRO: Falha durante o ciclo de Machine Learning.")
        logger.exception(e)
        raise e
    finally:
        if conn:
            cur.close()
            conn.close()
            logger.info("Conexão encerrada.")

if __name__ == '__main__':
    train_and_evaluate()

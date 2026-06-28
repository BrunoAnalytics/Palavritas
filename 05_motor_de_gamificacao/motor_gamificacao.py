import os
import sys
import logging

# Garante compatibilidade de encoding no ambiente Windows
os.environ['LC_ALL'] = 'C'
os.environ['LC_MESSAGES'] = 'C'
os.environ['PGCLIENTENCODING'] = 'utf-8'

# Configuração de Logging em Português de Portugal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.extras import RealDictCursor
    import pandas as pd
except ImportError:
    logger.error("ERRO: A biblioteca 'psycopg2' ou 'pandas' não está instalada no ambiente virtual.")
    sys.exit(1)

# Definições de conexão à base de dados (Mantendo a palavra-passe padrão 123456)
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

def setup_gamification_schema(conn):
    """
    Cria a tabela de destino para os gatilhos comportamentais de marketing e growth,
    garantindo que o sistema pode registar e auditar todas as ações em tempo real.
    """
    cur = conn.cursor()
    try:
        logger.info("A verificar estrutura da base de dados para o Motor de Gamificação...")
        
        # Criação da tabela de gatilhos de gamificação histórica
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.fact_gamification_triggers (
                trigger_id SERIAL PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                trigger_type VARCHAR(50) NOT NULL, -- 'near_miss_reward', 'streak_rescue_push', 'anti_frustration_easier_word'
                trigger_date DATE NOT NULL,
                priority VARCHAR(10) NOT NULL,      -- 'HIGH', 'MEDIUM', 'LOW'
                recomm_action VARCHAR(255) NOT NULL, -- Mensagem ou ação recomendada
                processed BOOLEAN DEFAULT FALSE,     -- Indica se o front-end/CRM já consumiu
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT unique_user_trigger_date UNIQUE (user_id, trigger_type, trigger_date)
            );
        """)
        conn.commit()
        logger.info("Tabela [fact_gamification_triggers] validada com sucesso.")
    except Exception as e:
        conn.rollback()
        logger.error("Erro ao configurar o esquema de gamificação.")
        raise e
    finally:
        cur.close()

def run_near_miss_engine(conn, target_date):
    """
    Identifica utilizadores em situação de Near-Miss (Quase Vitória) na data alvo:
    - Perderam na 6ª tentativa E acertaram 4 ou mais letras.
    Ação: Atribui uma recompensa de resgate (Ex: Dica de Palavra Grátis).
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        logger.info(f"A executar Motor Near-Miss para a data {target_date}...")
        
        # Query de identificação baseada em psicologia de iGaming
        query = """
            SELECT 
                user_id,
                session_id,
                attempts,
                matched_letters_final_attempt
            FROM public.fact_sessions
            WHERE word_date = CAST(%s AS DATE)
              AND result = 'loss'
              AND attempts = 6
              AND matched_letters_final_attempt >= 4;
        """
        cur.execute(query, (target_date,))
        near_misses = cur.fetchall()
        
        if not near_misses:
            logger.info("Nenhum utilizador em situação de Near-Miss encontrado para hoje.")
            return 0
            
        logger.info(f"Encontrados {len(near_misses)} utilizadores em quase vitória (Near-Miss)!")
        
        inserted = 0
        for row in near_misses:
            # Insere gatilho de recompensa imediata para reter o utilizador e quebrar a frustração
            try:
                cur.execute("""
                    INSERT INTO public.fact_gamification_triggers 
                    (user_id, trigger_type, trigger_date, priority, recomm_action)
                    VALUES (%s, 'near_miss_reward', %s, 'HIGH', %s)
                    ON CONFLICT (user_id, trigger_type, trigger_date) DO NOTHING;
                """, (
                    row['user_id'], 
                    target_date, 
                    f"Atribuir 50 Moedas + Dica Grátis devido a derrota injusta de {row['matched_letters_final_attempt']}/5 letras."
                ))
                inserted += cur.rowcount
            except Exception:
                pass # Ignora duplicados silenciosamente no ON CONFLICT
                
        conn.commit()
        return inserted
    except Exception as e:
        conn.rollback()
        logger.error("Falha no processamento do motor de Near-Miss.")
        raise e
    finally:
        cur.close()

def run_streak_rescue_engine(conn, target_date):
    """
    Identifica utilizadores com sequências ativas (Streaks >= 3 dias) que correm
    o risco de perder a sua ofensiva se não jogarem na data especificada.
    Ação: Envia um push urgente personalizado.
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        logger.info(f"A executar Motor de Resgate de Streaks (Sequências) para a data {target_date}...")
        
        # Identifica utilizadores cujo último dia ativo foi ontem e possuem streak relevante ativo
        query = """
            WITH last_user_sessions AS (
                SELECT 
                    user_id,
                    MAX(word_date) as last_play,
                    MAX(current_streak_days) as last_streak
                FROM public.fact_sessions
                WHERE word_date <= CAST(%s AS DATE)
                GROUP BY user_id
            )
            SELECT 
                user_id,
                last_streak
            FROM last_user_sessions
            WHERE last_play = CAST(%s AS DATE) - INTERVAL '1 day'
              AND last_streak >= 3
              AND user_id NOT IN (
                  SELECT DISTINCT user_id 
                  FROM public.fact_sessions 
                  WHERE word_date = CAST(%s AS DATE)
              );
        """
        cur.execute(query, (target_date, target_date, target_date))
        at_risk = cur.fetchall()
        
        if not at_risk:
            logger.info("Nenhuma sequência ativa de utilizadores está em risco de expirar hoje.")
            return 0
            
        logger.info(f"Sinalizados {len(at_risk)} utilizadores em risco de perder a sua sequência!")
        
        inserted = 0
        for row in at_risk:
            try:
                cur.execute("""
                    INSERT INTO public.fact_gamification_triggers 
                    (user_id, trigger_type, trigger_date, priority, recomm_action)
                    VALUES (%s, 'streak_rescue_push', %s, 'CRITICAL', %s)
                    ON CONFLICT (user_id, trigger_type, trigger_date) DO NOTHING;
                """, (
                    row['user_id'], 
                    target_date, 
                    f"Enviar Notificação Push: 'Rápido! Jogue hoje para manter a sua sequência de {row['last_streak']} dias!' "
                ))
                inserted += cur.rowcount
            except Exception:
                pass
                
        conn.commit()
        return inserted
    except Exception as e:
        conn.rollback()
        logger.error("Falha no processamento do motor de resgate de sequências.")
        raise e
    finally:
        cur.close()

def run_anti_frustration_engine(conn, target_date):
    """
    Identifica utilizadores com sequências de derrota persistentes (Loss Streak):
    - Perderam as últimas 3 partidas consecutivas jogadas.
    Ação: Configura a dificuldade do jogo para 'FÁCIL' ou oferece uma palavra comum de nível iniciante.
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        logger.info("A executar Motor de Retenção Anti-Frustração por perdas seguidas...")
        
        # Analisa o histórico recente das últimas 3 sessões de cada utilizador ativo até o momento
        query = """
            WITH ranked_sessions AS (
                SELECT 
                    user_id,
                    result,
                    ROW_NUMBER() OVER(PARTITION BY user_id ORDER BY word_date DESC, session_id DESC) as rn
                FROM public.fact_sessions
                WHERE word_date <= CAST(%s AS DATE)
            ),
            recent_three AS (
                SELECT 
                    user_id,
                    SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as loss_count
                FROM ranked_sessions
                WHERE rn <= 3
                GROUP BY user_id
                HAVING COUNT(*) = 3
            )
            SELECT user_id 
            FROM recent_three 
            WHERE loss_count = 3;
        """
        cur.execute(query, (target_date,))
        frustrated_users = cur.fetchall()
        
        if not frustrated_users:
            logger.info("Nenhum utilizador com alto nível de frustração cumulativa identificado.")
            return 0
            
        logger.info(f"Sinalizados {len(frustrated_users)} utilizadores frustrados devido a 3 derrotas seguidas.")
        
        inserted = 0
        for row in frustrated_users:
            try:
                cur.execute("""
                    INSERT INTO public.fact_gamification_triggers 
                    (user_id, trigger_type, trigger_date, priority, recomm_action)
                    VALUES (%s, 'anti_frustration_easier_word', %s, 'MEDIUM', %s)
                    ON CONFLICT (user_id, trigger_type, trigger_date) DO NOTHING;
                """, (
                    row['user_id'], 
                    target_date, 
                    "Configurar algoritmo dinâmico de palavra: Forçar palavra de nível muito fácil no próximo jogo."
                ))
                inserted += cur.rowcount
            except Exception:
                pass
                
        conn.commit()
        return inserted
    except Exception as e:
        conn.rollback()
        logger.error("Falha no processamento do motor anti-frustração.")
        raise e
    finally:
        cur.close()

def generate_marketing_dashboard(conn):
    """
    Gera um relatório agregador e executivo dos gatilhos comportamentais ativos
    na base de dados para fácil visualização pela equipa de Growth.
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT 
                trigger_type, 
                priority,
                COUNT(*) as total_triggers,
                SUM(CASE WHEN processed THEN 1 ELSE 0 END) as total_processed,
                SUM(CASE WHEN NOT processed THEN 1 ELSE 0 END) as pendentes
            FROM public.fact_gamification_triggers
            GROUP BY trigger_type, priority
            ORDER BY total_triggers DESC;
        """)
        rows = cur.fetchall()
        
        print("\n" + "="*70)
        print("          DASHBOARD DE MARKETING COMPORTAMENTAL & GAMIFICAÇÃO")
        print("="*70)
        
        if not rows:
            print("   Nenhum gatilho de gamificação registado no sistema atualmente.")
        else:
            print(f"{'Tipo de Gatilho (Trigger)':<32} | {'Prioridade':<10} | {'Total':<6} | {'Pendentes':<9}")
            print("-" * 70)
            for r in rows:
                print(f"{r['trigger_type']:<32} | {r['priority']:<10} | {r['total_triggers']:<6} | {r['pendentes']:<9}")
                
        print("="*70 + "\n")
        
    except Exception as e:
        logger.error("Erro ao gerar dashboard comportamental.")
        raise e
    finally:
        cur.close()

def main():
    conn = None
    try:
        conn = get_connection()
        
        # Garante a criação da tabela do motor comportamental
        setup_gamification_schema(conn)
        
        # Identifica a data mais recente dos jogos para contextualizar a simulação de hoje
        cur = conn.cursor()
        cur.execute("SELECT MAX(word_date) FROM public.fact_sessions;")
        max_date = cur.fetchone()[0]
        cur.close()
        
        if not max_date:
            logger.warning("Não há partidas registadas na base de dados para analisar gatilhos.")
            return
            
        logger.info(f"Data de simulação selecionada para análise de Gamificação: {max_date}")
        
        # Execução sequencial de todos os sub-motores de gamificação
        logger.info("=========================================================")
        logger.info("  A PROCESSAR SINAIS COMPORTAMENTAIS (iGAMING REGULATOR)  ")
        logger.info("=========================================================")
        
        nm_count = run_near_miss_engine(conn, max_date)
        logger.info(f"-> Motor Near-Miss: {nm_count} novos gatilhos registados.")
        
        sr_count = run_streak_rescue_engine(conn, max_date)
        logger.info(f"-> Motor Streak Rescue: {sr_count} novos gatilhos registados.")
        
        af_count = run_anti_frustration_engine(conn, max_date)
        logger.info(f"-> Motor Anti-Frustração: {af_count} novos gatilhos registados.")
        
        # Imprime o sumário final estatístico no ecrã
        generate_marketing_dashboard(conn)
        
    except Exception as e:
        logger.error("Erro crítico na execução do Motor de Gamificação.")
        logger.exception(e)
    finally:
        if conn:
            conn.close()
            logger.info("Conexão à base de dados encerrada de forma segura.")

if __name__ == '__main__':
    main()

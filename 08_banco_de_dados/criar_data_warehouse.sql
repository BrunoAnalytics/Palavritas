-- SQL Script to Create Data Warehouse Schema in PostgreSQL

-- Drop tables if they exist to allow clean creation
DROP TABLE IF EXISTS fact_attempts;
DROP TABLE IF EXISTS fact_sessions;
DROP TABLE IF EXISTS dim_dates;
DROP TABLE IF EXISTS dim_users;

-- 1. Dimension Table: dim_users
CREATE TABLE dim_users (
    user_id VARCHAR(50) PRIMARY KEY,
    age_range VARCHAR(20),
    state VARCHAR(50),
    city VARCHAR(100),
    salary_range VARCHAR(50),
    job_role VARCHAR(100),
    sector VARCHAR(100),
    company_size VARCHAR(50),
    orders_food_delivery BOOLEAN,
    food_delivery_freq_week INT,
    food_delivery_platform VARCHAR(50),
    primary_device VARCHAR(20),
    plays_other_word_games BOOLEAN,
    typical_play_time VARCHAR(20),
    newsletter_subscriber BOOLEAN
);

-- 2. Dimension Table: dim_dates
CREATE TABLE dim_dates (
    date_key DATE PRIMARY KEY,
    day INT NOT NULL,
    month INT NOT NULL,
    year INT NOT NULL,
    day_of_week INT NOT NULL,
    day_name VARCHAR(20) NOT NULL,
    quarter INT NOT NULL
);

-- 3. Fact Table: fact_sessions
CREATE TABLE fact_sessions (
    session_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL REFERENCES dim_users(user_id),
    word VARCHAR(50) NOT NULL,
    word_date DATE NOT NULL REFERENCES dim_dates(date_key),
    attempts INT NOT NULL,
    result VARCHAR(20) NOT NULL,
    time_to_complete_sec INT NOT NULL,
    device VARCHAR(20) NOT NULL,
    session_hour INT NOT NULL,
    streak_day INT NOT NULL,
    played_next_day BOOLEAN NOT NULL,
    newsletter_open_before_game BOOLEAN NOT NULL,
    active_d30 BOOLEAN NOT NULL
);

-- 4. Fact Table: fact_attempts
CREATE TABLE fact_attempts (
    attempt_id SERIAL PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL REFERENCES fact_sessions(session_id) ON DELETE CASCADE,
    attempt_number INT NOT NULL,
    guess VARCHAR(50) NOT NULL,
    correct_letters INT NOT NULL,
    correct_positions INT NOT NULL
);

-- Indexes for performance
CREATE INDEX idx_sessions_user ON fact_sessions(user_id);
CREATE INDEX idx_sessions_date ON fact_sessions(word_date);
CREATE INDEX idx_attempts_session ON fact_attempts(session_id);

use rusqlite::Connection;
use serde::Serialize;
use thiserror::Error;

#[derive(Debug, Clone, Serialize)]
pub struct Migration {
    pub version: i64,
    pub name: &'static str,
    pub sql: &'static str,
}
#[derive(Debug, Error)]
pub enum StorageError {
    #[error("sqlite error: {0}")]
    Sqlite(#[from] rusqlite::Error),
}

pub const MIGRATIONS: &[Migration] = &[
    Migration { version: 1, name: "create_games", sql: "CREATE TABLE IF NOT EXISTS games (id TEXT PRIMARY KEY, source TEXT NOT NULL DEFAULT 'local', source_id TEXT, board_size INTEGER NOT NULL, komi REAL NOT NULL, black_name TEXT, white_name TEXT, result TEXT, sgf_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP); CREATE INDEX IF NOT EXISTS idx_games_source ON games(source, source_id);" },
    Migration { version: 2, name: "create_game_nodes", sql: "CREATE TABLE IF NOT EXISTS game_nodes (id TEXT PRIMARY KEY, game_id TEXT NOT NULL, parent_id TEXT, move_number INTEGER NOT NULL, color TEXT, x INTEGER, y INTEGER, comment TEXT, zobrist TEXT, sgf_path TEXT, FOREIGN KEY(game_id) REFERENCES games(id)); CREATE INDEX IF NOT EXISTS idx_game_nodes_game_move ON game_nodes(game_id, move_number);" },
    Migration { version: 3, name: "create_analysis", sql: "CREATE TABLE IF NOT EXISTS analysis_jobs (id TEXT PRIMARY KEY, game_id TEXT, engine_profile_id TEXT, model_hash TEXT, visits INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT, FOREIGN KEY(game_id) REFERENCES games(id)); CREATE TABLE IF NOT EXISTS analysis_positions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, node_id TEXT, turn INTEGER NOT NULL, visits INTEGER NOT NULL, winrate_black REAL NOT NULL, score_mean_black REAL NOT NULL, score_stdev REAL, policy_json TEXT, ownership_json TEXT, candidates_json TEXT NOT NULL, raw_json TEXT, FOREIGN KEY(job_id) REFERENCES analysis_jobs(id)); CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_positions_job_turn ON analysis_positions(job_id, turn);" },
    Migration { version: 4, name: "create_engine_assets", sql: "CREATE TABLE IF NOT EXISTS engine_profiles (id TEXT PRIMARY KEY, name TEXT NOT NULL, engine_path TEXT NOT NULL, model_path TEXT, config_path TEXT, backend TEXT NOT NULL, config_json TEXT NOT NULL DEFAULT '{}'); CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, kind TEXT NOT NULL, version TEXT, path TEXT NOT NULL, sha256 TEXT, installed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);" },
];

pub fn apply_migrations(conn: &mut Connection) -> Result<(), StorageError> {
    conn.execute_batch("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);")?;
    let tx = conn.transaction()?;
    for m in MIGRATIONS {
        let count: i64 = tx.query_row(
            "SELECT COUNT(1) FROM schema_migrations WHERE version = ?1",
            [m.version],
            |row| row.get(0),
        )?;
        if count == 0 {
            tx.execute_batch(m.sql)?;
            tx.execute(
                "INSERT INTO schema_migrations(version, name) VALUES(?1, ?2)",
                (m.version, m.name),
            )?;
        }
    }
    tx.commit()?;
    Ok(())
}

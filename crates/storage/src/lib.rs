use rusqlite::{params, Connection, OptionalExtension};
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

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct GameMetadata {
    pub id: String,
    pub source: String,
    pub source_id: Option<String>,
    pub board_size: i64,
    pub komi: f64,
    pub black_name: Option<String>,
    pub white_name: Option<String>,
    pub result: Option<String>,
    pub sgf_hash: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct GameNode {
    pub id: String,
    pub game_id: String,
    pub parent_id: Option<String>,
    pub move_number: i64,
    pub color: Option<String>,
    pub x: Option<i64>,
    pub y: Option<i64>,
    pub comment: Option<String>,
    pub zobrist: Option<String>,
    pub sgf_path: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AnalysisJob {
    pub id: String,
    pub game_id: Option<String>,
    pub engine_profile_id: Option<String>,
    pub model_hash: Option<String>,
    pub visits: i64,
    pub status: String,
    pub created_at: Option<String>,
    pub finished_at: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AnalysisPosition {
    pub id: String,
    pub job_id: String,
    pub node_id: Option<String>,
    pub turn: i64,
    pub visits: i64,
    pub winrate_black: f64,
    pub score_mean_black: f64,
    pub score_stdev: Option<f64>,
    pub policy_json: Option<String>,
    pub ownership_json: Option<String>,
    pub candidates_json: String,
    pub raw_json: Option<String>,
}

pub const MIGRATIONS: &[Migration] = &[
    Migration { version: 1, name: "create_games", sql: "CREATE TABLE IF NOT EXISTS games (id TEXT PRIMARY KEY, source TEXT NOT NULL DEFAULT 'local', source_id TEXT, board_size INTEGER NOT NULL, komi REAL NOT NULL, black_name TEXT, white_name TEXT, result TEXT, sgf_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP); CREATE INDEX IF NOT EXISTS idx_games_source ON games(source, source_id);" },
    Migration { version: 2, name: "create_game_nodes", sql: "CREATE TABLE IF NOT EXISTS game_nodes (id TEXT PRIMARY KEY, game_id TEXT NOT NULL, parent_id TEXT, move_number INTEGER NOT NULL, color TEXT, x INTEGER, y INTEGER, comment TEXT, zobrist TEXT, sgf_path TEXT, FOREIGN KEY(game_id) REFERENCES games(id)); CREATE INDEX IF NOT EXISTS idx_game_nodes_game_move ON game_nodes(game_id, move_number);" },
    Migration { version: 3, name: "create_analysis", sql: "CREATE TABLE IF NOT EXISTS analysis_jobs (id TEXT PRIMARY KEY, game_id TEXT, engine_profile_id TEXT, model_hash TEXT, visits INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT, FOREIGN KEY(game_id) REFERENCES games(id)); CREATE TABLE IF NOT EXISTS analysis_positions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, node_id TEXT, turn INTEGER NOT NULL, visits INTEGER NOT NULL, winrate_black REAL NOT NULL, score_mean_black REAL NOT NULL, score_stdev REAL, policy_json TEXT, ownership_json TEXT, candidates_json TEXT NOT NULL, raw_json TEXT, FOREIGN KEY(job_id) REFERENCES analysis_jobs(id)); CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_positions_job_turn ON analysis_positions(job_id, turn);" },
    Migration { version: 4, name: "create_engine_assets", sql: "CREATE TABLE IF NOT EXISTS engine_profiles (id TEXT PRIMARY KEY, name TEXT NOT NULL, engine_path TEXT NOT NULL, model_path TEXT, config_path TEXT, backend TEXT NOT NULL, config_json TEXT NOT NULL DEFAULT '{}'); CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, kind TEXT NOT NULL, version TEXT, path TEXT NOT NULL, sha256 TEXT, installed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);" },
];

pub fn apply_migrations(conn: &mut Connection) -> Result<(), StorageError> {
    conn.execute_batch("PRAGMA foreign_keys = ON;")?;
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

pub fn upsert_game_metadata(conn: &Connection, game: &GameMetadata) -> Result<(), StorageError> {
    conn.execute(
        "INSERT INTO games (
            id, source, source_id, board_size, komi, black_name, white_name, result, sgf_hash
        ) VALUES (
            ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9
        )
        ON CONFLICT(id) DO UPDATE SET
            source = excluded.source,
            source_id = excluded.source_id,
            board_size = excluded.board_size,
            komi = excluded.komi,
            black_name = excluded.black_name,
            white_name = excluded.white_name,
            result = excluded.result,
            sgf_hash = excluded.sgf_hash,
            updated_at = CURRENT_TIMESTAMP",
        params![
            game.id,
            game.source,
            game.source_id,
            game.board_size,
            game.komi,
            game.black_name,
            game.white_name,
            game.result,
            game.sgf_hash
        ],
    )?;
    Ok(())
}

pub fn insert_game_node(conn: &Connection, node: &GameNode) -> Result<(), StorageError> {
    conn.execute(
        "INSERT INTO game_nodes (
            id, game_id, parent_id, move_number, color, x, y, comment, zobrist, sgf_path
        ) VALUES (
            ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10
        )",
        params![
            node.id,
            node.game_id,
            node.parent_id,
            node.move_number,
            node.color,
            node.x,
            node.y,
            node.comment,
            node.zobrist,
            node.sgf_path
        ],
    )?;
    Ok(())
}

pub fn list_game_nodes(conn: &Connection, game_id: &str) -> Result<Vec<GameNode>, StorageError> {
    let mut stmt = conn.prepare(
        "SELECT id, game_id, parent_id, move_number, color, x, y, comment, zobrist, sgf_path
        FROM game_nodes
        WHERE game_id = ?1
        ORDER BY move_number ASC, id ASC",
    )?;
    let nodes = stmt
        .query_map([game_id], |row| {
            Ok(GameNode {
                id: row.get(0)?,
                game_id: row.get(1)?,
                parent_id: row.get(2)?,
                move_number: row.get(3)?,
                color: row.get(4)?,
                x: row.get(5)?,
                y: row.get(6)?,
                comment: row.get(7)?,
                zobrist: row.get(8)?,
                sgf_path: row.get(9)?,
            })
        })?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(nodes)
}

pub fn create_analysis_job(conn: &Connection, job: &AnalysisJob) -> Result<(), StorageError> {
    conn.execute(
        "INSERT INTO analysis_jobs (
            id, game_id, engine_profile_id, model_hash, visits, status, created_at, finished_at
        ) VALUES (
            ?1, ?2, ?3, ?4, ?5, ?6, COALESCE(?7, CURRENT_TIMESTAMP), ?8
        )",
        params![
            job.id,
            job.game_id,
            job.engine_profile_id,
            job.model_hash,
            job.visits,
            job.status,
            job.created_at,
            job.finished_at
        ],
    )?;
    Ok(())
}

pub fn update_analysis_job(conn: &Connection, job: &AnalysisJob) -> Result<(), StorageError> {
    conn.execute(
        "UPDATE analysis_jobs SET
            game_id = ?2,
            engine_profile_id = ?3,
            model_hash = ?4,
            visits = ?5,
            status = ?6,
            created_at = COALESCE(?7, created_at),
            finished_at = ?8
        WHERE id = ?1",
        params![
            job.id,
            job.game_id,
            job.engine_profile_id,
            job.model_hash,
            job.visits,
            job.status,
            job.created_at,
            job.finished_at
        ],
    )?;
    Ok(())
}

pub fn get_latest_analysis_job(
    conn: &Connection,
    game_id: &str,
    engine_profile_id: Option<&str>,
    status: Option<&str>,
) -> Result<Option<AnalysisJob>, StorageError> {
    conn.query_row(
        "SELECT id, game_id, engine_profile_id, model_hash, visits, status, created_at, finished_at
        FROM analysis_jobs
        WHERE game_id = ?1
            AND (?2 IS NULL OR engine_profile_id = ?2)
            AND (?3 IS NULL OR status = ?3)
        ORDER BY COALESCE(finished_at, created_at) DESC, created_at DESC, id DESC
        LIMIT 1",
        params![game_id, engine_profile_id, status],
        |row| {
            Ok(AnalysisJob {
                id: row.get(0)?,
                game_id: row.get(1)?,
                engine_profile_id: row.get(2)?,
                model_hash: row.get(3)?,
                visits: row.get(4)?,
                status: row.get(5)?,
                created_at: row.get(6)?,
                finished_at: row.get(7)?,
            })
        },
    )
    .optional()
    .map_err(StorageError::from)
}

pub fn delete_analysis_for_game(
    conn: &Connection,
    game_id: &str,
    engine_profile_id: Option<&str>,
) -> Result<usize, StorageError> {
    conn.execute_batch("SAVEPOINT delete_analysis_for_game")?;

    let delete_result = || -> Result<usize, rusqlite::Error> {
        let deleted_positions = conn.execute(
            "DELETE FROM analysis_positions
            WHERE job_id IN (
                SELECT id FROM analysis_jobs
                WHERE game_id = ?1 AND (?2 IS NULL OR engine_profile_id = ?2)
            )",
            params![game_id, engine_profile_id],
        )?;
        let deleted_jobs = conn.execute(
            "DELETE FROM analysis_jobs
            WHERE game_id = ?1 AND (?2 IS NULL OR engine_profile_id = ?2)",
            params![game_id, engine_profile_id],
        )?;
        Ok(deleted_positions + deleted_jobs)
    }();

    match delete_result {
        Ok(deleted) => {
            if let Err(err) = conn.execute_batch("RELEASE SAVEPOINT delete_analysis_for_game") {
                let _ = conn.execute_batch(
                    "ROLLBACK TO SAVEPOINT delete_analysis_for_game;
                    RELEASE SAVEPOINT delete_analysis_for_game;",
                );
                return Err(StorageError::from(err));
            }
            Ok(deleted)
        }
        Err(err) => {
            let _ = conn.execute_batch(
                "ROLLBACK TO SAVEPOINT delete_analysis_for_game;
                RELEASE SAVEPOINT delete_analysis_for_game;",
            );
            Err(StorageError::from(err))
        }
    }
}

pub fn upsert_analysis_position(conn: &Connection, position: &AnalysisPosition) -> Result<(), StorageError> {
    conn.execute(
        "INSERT INTO analysis_positions (
            id, job_id, node_id, turn, visits, winrate_black, score_mean_black, score_stdev,
            policy_json, ownership_json, candidates_json, raw_json
        ) VALUES (
            ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12
        )
        ON CONFLICT(job_id, turn) DO UPDATE SET
            id = excluded.id,
            node_id = excluded.node_id,
            visits = excluded.visits,
            winrate_black = excluded.winrate_black,
            score_mean_black = excluded.score_mean_black,
            score_stdev = excluded.score_stdev,
            policy_json = excluded.policy_json,
            ownership_json = excluded.ownership_json,
            candidates_json = excluded.candidates_json,
            raw_json = excluded.raw_json",
        params![
            position.id,
            position.job_id,
            position.node_id,
            position.turn,
            position.visits,
            position.winrate_black,
            position.score_mean_black,
            position.score_stdev,
            position.policy_json,
            position.ownership_json,
            position.candidates_json,
            position.raw_json
        ],
    )?;
    Ok(())
}

pub fn load_analysis_positions(
    conn: &Connection,
    job_id: &str,
) -> Result<Vec<AnalysisPosition>, StorageError> {
    let mut stmt = conn.prepare(
        "SELECT id, job_id, node_id, turn, visits, winrate_black, score_mean_black, score_stdev,
            policy_json, ownership_json, candidates_json, raw_json
        FROM analysis_positions
        WHERE job_id = ?1
        ORDER BY turn ASC, id ASC",
    )?;
    let positions = stmt
        .query_map([job_id], |row| {
            Ok(AnalysisPosition {
                id: row.get(0)?,
                job_id: row.get(1)?,
                node_id: row.get(2)?,
                turn: row.get(3)?,
                visits: row.get(4)?,
                winrate_black: row.get(5)?,
                score_mean_black: row.get(6)?,
                score_stdev: row.get(7)?,
                policy_json: row.get(8)?,
                ownership_json: row.get(9)?,
                candidates_json: row.get(10)?,
                raw_json: row.get(11)?,
            })
        })?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(positions)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn migrated_connection() -> Connection {
        let mut conn = Connection::open_in_memory().expect("open in-memory sqlite");
        apply_migrations(&mut conn).expect("apply migrations");
        conn
    }

    fn sample_game() -> GameMetadata {
        GameMetadata {
            id: "game-1".to_string(),
            source: "local".to_string(),
            source_id: Some("sgf-1".to_string()),
            board_size: 19,
            komi: 7.5,
            black_name: Some("Black".to_string()),
            white_name: Some("White".to_string()),
            result: Some("B+R".to_string()),
            sgf_hash: Some("hash-1".to_string()),
        }
    }

    fn sample_job() -> AnalysisJob {
        AnalysisJob {
            id: "job-1".to_string(),
            game_id: Some("game-1".to_string()),
            engine_profile_id: Some("engine-1".to_string()),
            model_hash: Some("model-1".to_string()),
            visits: 800,
            status: "queued".to_string(),
            created_at: None,
            finished_at: None,
        }
    }

    fn sample_position(id: &str, job_id: &str, turn: i64) -> AnalysisPosition {
        AnalysisPosition {
            id: id.to_string(),
            job_id: job_id.to_string(),
            node_id: None,
            turn,
            visits: 800,
            winrate_black: 0.53,
            score_mean_black: 1.2,
            score_stdev: Some(8.1),
            policy_json: Some(r#"{"dd":0.4}"#.to_string()),
            ownership_json: None,
            candidates_json: r#"[{"move":"dd"}]"#.to_string(),
            raw_json: Some(r#"{"raw":true}"#.to_string()),
        }
    }

    #[test]
    fn apply_migrations_is_idempotent_for_in_memory_database() {
        let mut conn = Connection::open_in_memory().expect("open in-memory sqlite");

        apply_migrations(&mut conn).expect("first migration run");
        apply_migrations(&mut conn).expect("second migration run");

        let applied_count: i64 = conn
            .query_row("SELECT COUNT(1) FROM schema_migrations", [], |row| row.get(0))
            .expect("count applied migrations");
        assert_eq!(applied_count, MIGRATIONS.len() as i64);
    }

    #[test]
    fn apply_migrations_enables_foreign_key_enforcement() {
        let conn = migrated_connection();

        let foreign_keys_enabled: i64 = conn
            .query_row("PRAGMA foreign_keys", [], |row| row.get(0))
            .expect("read foreign_keys pragma");
        assert_eq!(foreign_keys_enabled, 1);

        let orphan_node = GameNode {
            id: "orphan-node".to_string(),
            game_id: "missing-game".to_string(),
            parent_id: None,
            move_number: 0,
            color: None,
            x: None,
            y: None,
            comment: None,
            zobrist: None,
            sgf_path: None,
        };
        assert!(insert_game_node(&conn, &orphan_node).is_err());

        let orphan_position = AnalysisPosition {
            id: "orphan-position".to_string(),
            job_id: "missing-job".to_string(),
            node_id: None,
            turn: 1,
            visits: 1,
            winrate_black: 0.5,
            score_mean_black: 0.0,
            score_stdev: None,
            policy_json: None,
            ownership_json: None,
            candidates_json: "[]".to_string(),
            raw_json: None,
        };
        assert!(upsert_analysis_position(&conn, &orphan_position).is_err());

        let orphan_job = AnalysisJob {
            id: "orphan-job".to_string(),
            game_id: Some("missing-game".to_string()),
            engine_profile_id: None,
            model_hash: None,
            visits: 1,
            status: "queued".to_string(),
            created_at: None,
            finished_at: None,
        };
        assert!(create_analysis_job(&conn, &orphan_job).is_err());
    }

    #[test]
    fn upserts_game_metadata() {
        let conn = migrated_connection();
        let mut game = sample_game();

        upsert_game_metadata(&conn, &game).expect("insert game");
        game.black_name = Some("Updated Black".to_string());
        game.result = Some("W+2.5".to_string());
        upsert_game_metadata(&conn, &game).expect("update game");

        let stored: (String, String, Option<String>) = conn
            .query_row(
                "SELECT id, black_name, result FROM games WHERE id = ?1",
                ["game-1"],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .expect("load game");
        assert_eq!(
            stored,
            (
                "game-1".to_string(),
                "Updated Black".to_string(),
                Some("W+2.5".to_string())
            )
        );
    }

    #[test]
    fn inserts_and_lists_game_nodes() {
        let conn = migrated_connection();
        upsert_game_metadata(&conn, &sample_game()).expect("insert game");

        let root = GameNode {
            id: "node-1".to_string(),
            game_id: "game-1".to_string(),
            parent_id: None,
            move_number: 0,
            color: None,
            x: None,
            y: None,
            comment: Some("root".to_string()),
            zobrist: Some("z0".to_string()),
            sgf_path: Some(";".to_string()),
        };
        let move_one = GameNode {
            id: "node-2".to_string(),
            game_id: "game-1".to_string(),
            parent_id: Some("node-1".to_string()),
            move_number: 1,
            color: Some("B".to_string()),
            x: Some(3),
            y: Some(3),
            comment: None,
            zobrist: Some("z1".to_string()),
            sgf_path: Some(";B[dd]".to_string()),
        };
        insert_game_node(&conn, &move_one).expect("insert move one");
        insert_game_node(&conn, &root).expect("insert root");

        let nodes = list_game_nodes(&conn, "game-1").expect("list nodes");
        assert_eq!(nodes, vec![root, move_one]);
    }

    #[test]
    fn creates_and_updates_analysis_job() {
        let conn = migrated_connection();
        upsert_game_metadata(&conn, &sample_game()).expect("insert game");
        let mut job = sample_job();

        create_analysis_job(&conn, &job).expect("create job");
        job.status = "finished".to_string();
        job.visits = 1200;
        job.finished_at = Some("2026-05-01T12:00:00Z".to_string());
        update_analysis_job(&conn, &job).expect("update job");

        let stored: (String, i64, Option<String>) = conn
            .query_row(
                "SELECT status, visits, finished_at FROM analysis_jobs WHERE id = ?1",
                ["job-1"],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .expect("load job");
        assert_eq!(
            stored,
            (
                "finished".to_string(),
                1200,
                Some("2026-05-01T12:00:00Z".to_string())
            )
        );
    }

    #[test]
    fn gets_latest_analysis_job_with_optional_filters() {
        let conn = migrated_connection();
        upsert_game_metadata(&conn, &sample_game()).expect("insert game");

        let mut old_queued = sample_job();
        old_queued.id = "job-old-queued".to_string();
        old_queued.created_at = Some("2026-05-01T10:00:00Z".to_string());
        create_analysis_job(&conn, &old_queued).expect("create old queued job");

        let mut finished = sample_job();
        finished.id = "job-finished".to_string();
        finished.status = "finished".to_string();
        finished.created_at = Some("2026-05-01T09:00:00Z".to_string());
        finished.finished_at = Some("2026-05-01T12:00:00Z".to_string());
        create_analysis_job(&conn, &finished).expect("create finished job");

        let mut other_engine = sample_job();
        other_engine.id = "job-other-engine".to_string();
        other_engine.engine_profile_id = Some("engine-2".to_string());
        other_engine.status = "finished".to_string();
        other_engine.created_at = Some("2026-05-01T11:00:00Z".to_string());
        other_engine.finished_at = Some("2026-05-01T13:00:00Z".to_string());
        create_analysis_job(&conn, &other_engine).expect("create other engine job");

        let latest_any = get_latest_analysis_job(&conn, "game-1", None, None)
            .expect("load latest job")
            .expect("latest job");
        assert_eq!(latest_any.id, "job-other-engine");

        let latest_engine_one = get_latest_analysis_job(&conn, "game-1", Some("engine-1"), None)
            .expect("load latest engine job")
            .expect("latest engine job");
        assert_eq!(latest_engine_one.id, "job-finished");

        let latest_queued = get_latest_analysis_job(&conn, "game-1", Some("engine-1"), Some("queued"))
            .expect("load latest queued job")
            .expect("latest queued job");
        assert_eq!(latest_queued.id, "job-old-queued");

        let missing = get_latest_analysis_job(&conn, "game-1", Some("engine-1"), Some("running"))
            .expect("load missing status");
        assert_eq!(missing, None);
    }

    #[test]
    fn saves_loads_and_overwrites_analysis_positions() {
        let conn = migrated_connection();
        upsert_game_metadata(&conn, &sample_game()).expect("insert game");
        create_analysis_job(&conn, &sample_job()).expect("create job");

        let first = AnalysisPosition {
            id: "position-1".to_string(),
            job_id: "job-1".to_string(),
            node_id: Some("node-1".to_string()),
            turn: 1,
            visits: 800,
            winrate_black: 0.53,
            score_mean_black: 1.2,
            score_stdev: Some(8.1),
            policy_json: Some(r#"{"dd":0.4}"#.to_string()),
            ownership_json: None,
            candidates_json: r#"[{"move":"dd"}]"#.to_string(),
            raw_json: Some(r#"{"raw":true}"#.to_string()),
        };
        upsert_analysis_position(&conn, &first).expect("insert position");

        let mut overwritten = first.clone();
        overwritten.id = "position-1b".to_string();
        overwritten.visits = 1600;
        overwritten.winrate_black = 0.61;
        overwritten.candidates_json = r#"[{"move":"pq"}]"#.to_string();
        upsert_analysis_position(&conn, &overwritten).expect("overwrite position");

        let positions = load_analysis_positions(&conn, "job-1").expect("load positions");
        assert_eq!(positions, vec![overwritten]);
    }

    #[test]
    fn loads_analysis_positions_ordered_by_turn() {
        let conn = migrated_connection();
        upsert_game_metadata(&conn, &sample_game()).expect("insert game");
        create_analysis_job(&conn, &sample_job()).expect("create job");

        let turn_three = sample_position("position-3", "job-1", 3);
        let turn_one = sample_position("position-1", "job-1", 1);
        let turn_two = sample_position("position-2", "job-1", 2);
        upsert_analysis_position(&conn, &turn_three).expect("insert turn three");
        upsert_analysis_position(&conn, &turn_one).expect("insert turn one");
        upsert_analysis_position(&conn, &turn_two).expect("insert turn two");

        let positions = load_analysis_positions(&conn, "job-1").expect("load positions");
        let turns = positions.iter().map(|position| position.turn).collect::<Vec<_>>();
        assert_eq!(turns, vec![1, 2, 3]);
    }

    #[test]
    fn deletes_analysis_jobs_and_positions_for_game() {
        let conn = migrated_connection();
        upsert_game_metadata(&conn, &sample_game()).expect("insert game");
        let mut other_game = sample_game();
        other_game.id = "game-2".to_string();
        upsert_game_metadata(&conn, &other_game).expect("insert other game");

        let delete_job = sample_job();
        create_analysis_job(&conn, &delete_job).expect("create delete job");

        let mut keep_engine_job = sample_job();
        keep_engine_job.id = "job-keep-engine".to_string();
        keep_engine_job.engine_profile_id = Some("engine-2".to_string());
        create_analysis_job(&conn, &keep_engine_job).expect("create keep engine job");

        let mut keep_game_job = sample_job();
        keep_game_job.id = "job-keep-game".to_string();
        keep_game_job.game_id = Some("game-2".to_string());
        create_analysis_job(&conn, &keep_game_job).expect("create keep game job");

        upsert_analysis_position(&conn, &sample_position("position-delete", "job-1", 1))
            .expect("insert delete position");
        upsert_analysis_position(
            &conn,
            &sample_position("position-keep-engine", "job-keep-engine", 1),
        )
        .expect("insert keep engine position");
        upsert_analysis_position(&conn, &sample_position("position-keep-game", "job-keep-game", 1))
            .expect("insert keep game position");

        let deleted = delete_analysis_for_game(&conn, "game-1", Some("engine-1")).expect("delete analysis");
        assert_eq!(deleted, 2);

        let deleted_job_count: i64 = conn
            .query_row(
                "SELECT COUNT(1) FROM analysis_jobs WHERE id = 'job-1'",
                [],
                |row| row.get(0),
            )
            .expect("count deleted job");
        assert_eq!(deleted_job_count, 0);
        let deleted_position_count: i64 = conn
            .query_row(
                "SELECT COUNT(1) FROM analysis_positions WHERE id = 'position-delete'",
                [],
                |row| row.get(0),
            )
            .expect("count deleted position");
        assert_eq!(deleted_position_count, 0);

        let remaining_job_count: i64 = conn
            .query_row("SELECT COUNT(1) FROM analysis_jobs", [], |row| row.get(0))
            .expect("count remaining jobs");
        assert_eq!(remaining_job_count, 2);
        let remaining_position_count: i64 = conn
            .query_row("SELECT COUNT(1) FROM analysis_positions", [], |row| row.get(0))
            .expect("count remaining positions");
        assert_eq!(remaining_position_count, 2);
    }

    #[test]
    fn delete_analysis_for_game_rolls_back_when_job_delete_fails() {
        let conn = migrated_connection();
        upsert_game_metadata(&conn, &sample_game()).expect("insert game");
        create_analysis_job(&conn, &sample_job()).expect("create job");
        upsert_analysis_position(&conn, &sample_position("position-1", "job-1", 1)).expect("insert position");

        conn.execute_batch(
            "CREATE TRIGGER fail_analysis_job_delete
            BEFORE DELETE ON analysis_jobs
            BEGIN
                SELECT RAISE(ABORT, 'blocked job delete');
            END;",
        )
        .expect("create failing delete trigger");

        let err =
            delete_analysis_for_game(&conn, "game-1", Some("engine-1")).expect_err("delete should fail");
        assert!(err.to_string().contains("blocked job delete"));

        let job_count: i64 = conn
            .query_row(
                "SELECT COUNT(1) FROM analysis_jobs WHERE id = 'job-1'",
                [],
                |row| row.get(0),
            )
            .expect("count jobs after rollback");
        assert_eq!(job_count, 1);
        let position_count: i64 = conn
            .query_row(
                "SELECT COUNT(1) FROM analysis_positions WHERE id = 'position-1'",
                [],
                |row| row.get(0),
            )
            .expect("count positions after rollback");
        assert_eq!(position_count, 1);

        conn.execute_batch("DROP TRIGGER fail_analysis_job_delete")
            .expect("drop failing delete trigger");
        let deleted =
            delete_analysis_for_game(&conn, "game-1", Some("engine-1")).expect("delete after trigger drop");
        assert_eq!(deleted, 2);
    }
}

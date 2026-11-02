-- Allow multiple concurrent reads during a write
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS snapshots (
-- can also use integer primary key, but the limited to signed 8byte integer
-- limit on number of row
id TEXT PRIMARY KEY,
url TEXT NOT NULL,
start_time REAL NOT NULL,
end_time REAL NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS files (
-- same comments as above about integer primary keys
id TEXT PRIMARY KEY,
snapshot_id TEXT,
-- not strictly nessessary depending on how we choose to organize files on
-- disk, but might be helpful for future storage changes
on_disk_path TEXT NOT NULL,
protocol TEXT NOT NULL,
port INTEGER NOT NULL,
host TEXT NOT NULL,
-- path of file on (above) remote host
remote_path TEXT NOT NULL,
request_sent_time REAL NOT NULL,
request_method TEXT NOT NULL,
-- jsonb object mapping request headers to their values
-- (see `/files/{FILE_ID}` for format)
request_headers BLOB NOT NULL,
-- jsonb object mapping request parameters to their values
-- (see `/files/{FILE_ID}` for format)
request_parameters BLOB NOT NULL,
response_recieved_time REAL NOT NULL,
response_code INTEGER NOT NULL,
-- jsonb object mapping request parameters to their values
-- (see `/files/{FILE_ID}` for format)
response_headers BLOB NOT NULL,

FOREIGN KEY (snapshot_id) REFERENCES snapshots (id)
    ON UPDATE SET NULL
    ON DELETE SET NULL
) WITHOUT ROWID;

-- Speed up searches in the form of
-- `SELECT * FROM files WHERE snapshot_id = '...';`
CREATE INDEX IF NOT EXISTS idx_files_snapshot ON files(snapshot_id);

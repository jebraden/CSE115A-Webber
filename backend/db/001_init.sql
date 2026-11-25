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
-- logical file size in bytes on disk (ignoring hardlinks, FS compression, etc.)
file_size INTEGER NOT NULL,
protocol TEXT NOT NULL,
port INTEGER NOT NULL,
host TEXT NOT NULL,
-- path of file on (above) remote host
remote_path TEXT NOT NULL,
request_sent_time REAL NOT NULL,
request_method TEXT NOT NULL,
-- jsonb object mapping response headers to their values
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

CREATE TABLE IF NOT EXISTS bookmarks (
-- ID of this bookmark
id TEXT PRIMARY KEY,
-- pretty printed name of this bookmark
name TEXT NOT NULL,
-- Actually, only one of the following should be set
-- That is, a bookmark on an entire snapshot should have FILE_ID be NULL and a
-- bookmark on a specific file should have SNAPSHOT_ID be NULL.
snapshot_id TEXT,
file_id TEXT,

FOREIGN KEY (snapshot_id) REFERENCES snapshots (id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,

FOREIGN KEY (file_id) REFERENCES files (id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,

CHECK (
    (snapshot_id IS NOT NULL and file_id IS NULL)
    OR
    (snapshot_id IS NULL and file_id IS NOT NULL)
)) WITHOUT ROWID;

-- Speed up searches in the form of
-- `SELECT * FROM files WHERE snapshot_id = '...';`
CREATE INDEX IF NOT EXISTS idx_files_snapshot ON files(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_files_rec_time ON files(response_recieved_time);
CREATE INDEX IF NOT EXISTS idx_snapshots_start_time ON snapshots(start_time);
CREATE INDEX IF NOT EXISTS idx_bookmarks_name ON bookmarks(name);
CREATE INDEX IF NOT EXISTS idx_bookmarks_file_id ON bookmarks(file_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_snapshot_id ON bookmarks(snapshot_id);

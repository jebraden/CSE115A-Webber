import sqlite3
import json
import uuid
import logging
import shutil
import re
import urllib.parse import urlsplit, parse_qs

base_dir = os.path.join(os.getenv("HOME"), ".webber")
db_path = os.path.join(base_dir, "archive.db")
logger = logging.getLogger(__name__)

class RequestManager():
    def __init__():
        pass


    def create_snapshot(self, request) -> (dict, int):
        form = request.form

        url: str = None
        options_dict: dict = None
        method: str = None
        headers: dict = None
        try:
            url = form["url"]
        except KeyError:
            return self.bad_request("Payload missing 'url'")
        raw_options = form.get("request_options", None)
        # Assume that options parameters are... optional
        if raw_options:
            try:
                options_dict = json.loads(raw_options)
            except json.JSONDecodeError:
                return self.bad_request("'request-options' contained invalid json. Failed to parse")
        if options_dict:
            method = options.get("method", None)
            try:
                raw_headers = options.get("headers", None)
                if raw_headers:
                    headers = json.loads(options["headers"])
            except json.JSONDecodeError:
                return self.bad_request("'request_options.headers' contained invalid json. Failed to parse")

        # Parameters validated
        # TODO: CALL WEB SCRAPER - NEED TO ADD SUPPORT FOR THE THINGS
        uid = uuid.uuid4()
        response = {"id": str(uid)}
        logger.info(f"Created new snapshot with id: {uid}")
        return (response, 201)


    def delete_snapshot(self, snapshot_id: str) -> (dict, int):
        db = sqlite3.connect(db_path)
        with db:
            row = db.execute(
                """
                SELECT * 
                FROM snapshots
                WHERE id = ?
                """,
                (snapshot_id,)
             ).fetchone()
            if row is None:
                return self.not_found(f"{snapshot_id} is not a valid snapshot id")
            path = os.path.join(base_dir, snapshot_id)
            # Should clean up the directory
            shutil.rmtree(path)
            logger.info(f"Deleted files on disk for the snapshot {snapshot_id}")
            # Delete file rows
            db.execute(
                """
                DELETE
                FROM files
                WHERE snapshot_id = ?
                """,
                (snapshot_id,)
            )
            logger.info(f"Deleted file entries assosciated with snapshot_id {snapshot_id}")
            db.execute(
                """
                DELETE 
                FROM snapshots
                WHERE id = ?
                """,
                (snapshot_id,)
            )
            logger.info(f"Deleted snapshot ({snapshot_id}) entry from snapshots table ")
            db.commit()
    db.close()
    path = os.path.join(base_dir, snapshot_id)
    # Should clean up the directory
    shutil.rmtree(path)
    logger.info(f"Deleted files on disk for the snapshot {snapshot_id}") 
    return ({}, 202)

    def get_snapshot(self, snapshot_id: str) -> (dict, int)
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        row = None
        file_ids = None
        with db:
            row = db.execute(
                """
                SELECT *
                FROM snapshots
                WHERE id = ?
                """,
                (snapshot_id,)
            ).fetchone()
            if row is None:
                db.close()
                return self.not_found(f"{snapshot_id} is not a valid snapshot id")
            file_ids = db.execute(
                """
                SELECT id 
                FROM files
                WHERE snapshot_id = ?
                """,
                (snapshot_id,)
            ).fetchall()
        db.close()
        resp = {
            "id": row["id"],
            "url": row["url"],
            "start_time": self._time_spec(row["start_time"]),
            "end_time": self._time_spec(row["end_time"]),
            "files": file_ids,
        }
        return (resp, 200)

    def get_file(self, file_id: str) -> (dict, int):
        db = sqlite3.connect(db_path)
        row = None
        with db:
            row = db.execute(
                """
                SELECT on_disk_path 
                FROM files
                WHERE id = ?
                """,
                (file_id,)
            ).fetchone()
            if row is None:
                db.close()
                return self.not_found(f"Failed to find file with id {file_id} in the database")
        db.close()
        return self._file_from_row(row)   

    def get_file_by_url(self, snapshot_id: str, url_path: str, request) -> (dict, int):
        safe_path = unquote(url_path)
        comps = urlsplit(safe_path)
        protocol = parsed.scheme
        host = parsed.hostname
        port = parsed.port
        remote_path = parsed.path or "/"

        params = request.args
        if not params:
            params = {}
        
        query_values = (snapshot_id, protocol, port, host, remote_path, json.dumps(params))

        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        row = None
        with db:
            row = db.execute(
                """
                SELECT on_disk_path
                FROM files
                WHERE snapshot_id = ?  
                    AND protocol = ?
                    AND host = ?
                    AND port = ?
                    AND remote_path = ?
                    AND request_parameters = jsonb(?)
                """,
                query_values
            ).fetchone() # There should only be one archive for this exact situation

        db.close()
        if row is None:
            return self.not_found(f"Failed to match url {safe_path} to a file in the DB")
        return self._file_from_row(row) 

    def regexp(pattern, url):
        if url is None: return False
        return re.search(pattern, url) is not None

    def query_snapshots(self, request) -> (dict, int):
        form = request.form
        start = float("-inf")
        end = float("inf") 
        url_reg = r"." # match anything in the db
        pattern = None
        try:
            start_spec = form.get("start_time", {})
            if start_spec:
                start = self._time(start_spec)
            end_spec = form.get("end_time", {})
            if end_spec:
                end = self._time(end_spec)
            raw_pattern = form.get("url", "")
            if raw_pattern:
                url_reg = rf"{raw_pattern}"
        except KeyError:
            return self.bad_request("start time or end time spec improperly formated")
        except Exception as e:
            logger.warning(f"query_snapshots: Encountered unexpected error {e}")
            return self.internal_server_error("Encountered unexpected internal error")
        try:
            pattern = re.compile(pattern)
        except re.error:
            return self.bad_request(f"The provided url-regex represents an invalid pattern {url_reg}")

        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        results = None
        with db:
            db.create_function("REGEXP", 2, regexp)
         
            results = db.execute(
                """
                SELECT *
                FROM snapshots
                WHERE start_time < ?
                    AND end_time > ?
                    AND url REGEXP ?
                """,
                (start, end, url_reg)
            )
        db.close()
        if results is None:
            return ({"content": []}, 200)
        ids = [row["id"] for row in rows]
        return ({"content": ids}, 200)

    def query_files(self, request) -> (dict, int):
        form = request.form
        other_conds = []
        other_vals = []

        snap_id = form.get("snapshot_id", "")
        if snap_id:
            other_conds.append("snapshot_id = ?")
            other_vals.append(snap_id)

        try:
            start_spec = form.get("start_time", {})
            if start_spec:
                start = self._time(start_spec)
                other_conds.append("request_sent_time >= ?")
                other_vals.append(start)
            end_spec = form.get("end_time", {})
            if end_spec:
                end = self._time(end_spec)
                other_conds.append("response_recieved_time <= ?")
                other_vals.append(end)
        except KeyError:
            return self.bad_request("start time or end time spec improperly formatted")
        except Exception as e:
            logger.warning(f"query_files: Encoutered unexpected error reading time specs: {e}")
            return self.internal_server_error("Encountered unexpected internal error")
        pattern_fields = {"host": "host", "protocol": "protocol", "path": "remote_path"}
        try:
            for field in pattern_fields:
                self._build_pattern(form, pattern_fields[field], field, other_conds, other_vals)
            self._url_subquery(form, "url", other_conds, other_vals)
        except re.error:
            return self._bad_request("Failed to generate regex pattern for one of the provided regex options!")
        except Exception as e:
            logger.warning(f"query_files: Encountered unexpected error reading regex patterns: {e}")
            return self.internal_server_error("Encountered unexpected internal error")

        port = None
        try:
            raw_port = form.get("port", "")
            if raw_port:
                port = int(raw_port)
                other_conds.append("port = ?")
                other_vals.append(port)
            codes = form.get("status_codes", [])
            if not isinstance(codes, list):
                return self._bad_request(f"Expected a list for field 'status_codes', instead recieved {type(codes)}")
            list_params = ", ".join(["?"]) * len(codes)
            other_conds.append(f"response_code IN ({list_params})")
            other_vals.extend(codes)
        except TypeError, ValueError:
            return self._bad_request("Bad value provided for the port or status codes field")
        except Exception as e:
            logger.warning(f"query_files: Encountered unexpected error port values / status code: {e}")
            return self.internal_server_error("Encountered unexpected internal error")
        conditions_string = "AND ".join(other_conds)
        
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        with db:
            db.create_function("REGEXP", 2, regexp)
            results = db.execute(
                f"""
                SELECT snapshot_id, id
                FROM files
                WHERE {conditions_string}
                """,
                other_vals
            ).fetchAll()
        db.close()    
        data = [
            {
                "snapshot_id": row["snapshot_id"],
                "file_id": row["id"]
            }
            for row in results
        ]
        return {"content": data}, 200


        
    def _url_subquery(self, form, field: str, conditions: list, values: list):
        """ Callers must surround method in try catch block """
        raw_pattern = form.get(field, "")
        if not raw_pattern: return None
        pattern = re.compile(raw_pattern)
        subquery = "snapshot_id IN (SELECT id FROM snapshots WHERE url REGEXP ?)"
        conditions.append(subquery)
        values.append(raw_pattern)

    
    def _build_pattern(self, form, sql_name: str, field: str, conditons: list, values: list):
        """ Callers must surround this method in a try catch block """
            raw_pattern = form.get(field, "")
            if not raw_pattern: return None
            pattern = re.compile(raw_pattern))
            # Need to catch and handle above error
            conditions.append(f"{sql_name} REGEXP ?")
            values.append(raw_pattern)


    def _file_from_row(self, row: dict) -> (dict, int):
        file_id = row["id"]
        disk_path = row["on_disk_path"]
        if not os.path.isfile(disk_path):
            return self.internal_server_error(f"Could not find file {file_id} locally at {disk_path}")

        body = None
        with open(path, "rb") as file:
            body = file.read()
        
        headers = json.loads(row["response_headers"])
        content_type = "application/octet-stream"
        for name, values in headers.items():
            if name.lower() != "content-type": continue
            content_type = values[0]
            break
        resp = {
            "body": body,
            "status": row["response_code"],
            "content_type": content_type
        }
        return (resp, 200)



    def _time(self, ts: dict):
        return ts["sec"] + ts["nsec"] / 1_000_000_000

    def _time_spec(self, t: float) -> dict:
        total_ns = round(t * 1_000_000_000)
        return {
            "sec": total_ns // 1_000_000_000,
            "nsec": total_ns % 1_000_000_000,
        }
        

    def internal_server_error(self, msg: str) -> (dict, int):
        return ({ "message": f"Internal Server Error: {msg}"}, 500) 

    def bad_request(self, msg: str) -> (dict, int):
        return ({"message": f"Bad Request: {msg}"}, 400)
    def not_found(self, msg: str) -> (dict, int):
        return ({"message": msg}, 404)



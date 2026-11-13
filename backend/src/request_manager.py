import sqlite3
import os
import json
import uuid
import logging
import shutil
import re
import asyncio
from urllib.parse import urlencode, unquote, urlsplit, parse_qs
from src.scraping.scraper import PageScraper

base_dir = os.path.join(os.getenv("HOME"), ".webber")
db_path = os.path.join(base_dir, "archive.db")
logger = logging.getLogger(__name__)

# Please note db = self.db usage is due to this member var not existing before
# And I am too lazy to insert self.db everywhere
class RequestManager():
    def __init__(self, db_conn=None):
        if db_conn is None:
            db_conn = sqlite3.connect(db_path)
        self.db = db_conn
        pass

    def _json_check(self, payload):
        if not isinstance(payload, dict):
            return self.bad_request("Expected JSON payload")
        else:
            return None

    def create_snapshot(self, request) -> (dict, int):
        payload = request.get_json(silent=True)
        res = self._json_check(payload)
        if res: return res

        url: str = None
        options_dict: dict = None
        method: str = None
        headers: dict = None
        try:
            url = payload["url"]
        except KeyError:
            return self.bad_request("Payload missing 'url'")
        raw_options = payload.get("request_options", None)
        # Assume that options parameters are... optional
        if raw_options:
            try:
                options_dict = json.loads(raw_options)
            except json.JSONDecodeError:
                return self.bad_request("'request-options' contained invalid json. Failed to parse")
        if options_dict:
            method = options_dict.get("method", None)
            try:
                raw_headers = options_dict.get("headers", None)
                if raw_headers:
                    headers = json.loads(options_dict["headers"])
            except json.JSONDecodeError:
                return self.bad_request("'request_options.headers' contained invalid json. Failed to parse")

        if url is None:
            return self.bad_request("No url found")

        # Parameters validated
        # Currently on GET explicitly supported
        scraper = PageScraper(db_conn = self.db)
        snap_id = asyncio.run(scraper.archive_page(url))
        response = {"id": str(snap_id)}
        logger.info(f"Created new snapshot with id: {snap_id}")
        return (response, 201)


    def delete_snapshot(self, snapshot_id: str) -> (dict, int):
        db = self.db 
        try:
            with db:
                # Was thinking if we need this initial query
                # It allows us to be informative, but it really doesn't
                # change behavior
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
        except Exception as e:
            logger.warning(f"delete_snapshot: Encountered unexpected error {e}")
            return self.internal_server_error(f"encountered unexpected error deleting snapshot {snapshot_id}")

        self._delete_snapshot_files(snapshot_id)

        return ({}, 202)

    def delete_snapshots(self, request) -> (dict, int):
        payload = request.get_json(silent=True)
        res = self._json_check(payload)
        if res: return res

        snapshot_ids = payload.get("ids", None)

        if snapshot_ids is None:
            return self.bad_request("Expected a body with 'ids' which is an array containing snapshot ids")

        db = self.db
        list_placeholder = ", ".join("?" * len(snapshot_ids))
        try:
            with db:
                db.execute(
                    f"""
                    DELETE
                    FROM files
                    WHERE snapshot_id IN ({list_placeholder})
                    """,
                    snapshot_ids
                )
                logger.info(f"Batch deleted file entries assosciated with snapshot_ids {snapshot_ids}")

                db.execute(
                    f"""
                    DELETE
                    from snapshots
                    WHERE id IN ({list_placeholder})
                    """,
                    snapshot_ids
                )
                logger.info(f"Batch deleted all snapshot entries assosciated with snapshot_ids {snapshot_ids}")
                db.commit()
        except Exception as e:
            logger.warning(f"delete_snapshops: Encountered unexpected error deleting from the database: {e}")
            return self.internal_server_error(f"Encountered unexpected error deleting from the database")

        for snap_id in snapshot_ids:
            self._delete_snapshot_files(snap_id)
        return ({}, 202)


    def _delete_snapshot_files(self, snapshot_id: str):
        path = os.path.join(base_dir, snapshot_id)
        if not os.path.exists(path):
            logger.warning(f"delete_snapshots: File path to snapshot {snapshot_id}, {str(path)}, doesn't exist! Skipping")
            return
        try:
            shutil.rmtree(path)
            logger.info(f"delete_snapshots: Deleted files on disk for the snapshot {snapshot_id}")
        except Exception as e:
            logger.warning(f"delete_snapshots: Encountered unexpected error while deleting files on disk for snapshot {snapshot_id} at {str(path)}: {e}")
 
    def get_snapshot(self, snapshot_id: str) -> (dict, int):
        db = self.db 
        db.row_factory = sqlite3.Row
        row = None
        file_ids = None
        try:
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
                file_rows = db.execute(
                    """
                    SELECT id 
                    FROM files
                    WHERE snapshot_id = ?
                    """,
                    (snapshot_id,)
                ).fetchall()
        except Exception as e:
            logger.warning(f"get_snapshot: Encountered unexpected error {e}")
            return self.internal_server_error("Encountered unexpected error when getting snapshot data")
        file_ids = [row["id"] for row in file_rows]
        resp = {
            "id": row["id"],
            "url": row["url"],
            "start_time": self._time_spec(row["start_time"]),
            "end_time": self._time_spec(row["end_time"]),
            "files": file_ids,
        }
        return (resp, 200)

    def get_file_info(self, file_id: str) -> (dict, int):
        db = self.db
        db.row_factory = sqlite3.Row

        row = None
        try:
            with db:
                row = db.execute(
                    f"""
                    SELECT id, snapshot_id, protocol, port,
                        host, remote_path, request_sent_time, request_method,
                        json(request_headers) AS request_headers, 
                        json(request_parameters) AS request_parameters,
                        response_recieved_time, response_code,
                        json(response_headers) AS response_headers
                    FROM files
                    WHERE id = ?
                    """,
                    (file_id,)
                ).fetchone()
                if row is None:
                    return self.not_found(f"Failed to find file with id {file_id} in the database")
        except Exception as e:
            logger.warning(f"get_file_info: Encountered unexpected error fetching file data from {file_id}: {e}")
            return self.internal_server_error("Encountered unexpected error getting file data")

        headers = json.loads(row["request_headers"])
        response_headers = json.loads(row["response_headers"])
        params = json.loads(row["request_parameters"])
        url = self._build_url(row)
        return ({
            "id": row["id"],
            "snapshot": row["snapshot_id"],
            "url": url,
            "protocol": row["protocol"],
            "port": row["port"],
            "host": row["host"],
            "path": row["remote_path"].lstrip("/"),
            "request": {
                "sent_time": self._time_spec(row["request_sent_time"]),
                "method": row["request_method"],
                "headers": headers,
                "parameters": params,
            },
            "response": {
                "recieved_time": self._time_spec(row["response_recieved_time"]),
                "code": row["response_code"],
                "headers": response_headers,
            },
        }, 200)

    def get_file(self, file_id: str) -> (dict, int):
        db = self.db
        db.row_factory = sqlite3.Row
        row = None
        try:
            with db:
                row = db.execute(
                    f"""
                    SELECT {self._file_params()} 
                    FROM files
                    WHERE id = ?
                    """,
                    (file_id,)
                ).fetchone()
                if row is None:
                    return self.not_found(f"Failed to find file with id {file_id} in the database")
        except Exception as e:
            logger.warning(f"get_file: Encountered unexpected error getting file data {e}")
            return self.internal_server_error("Encountered unexpected error when getting file data")
        return self._file_from_row(row)  

    def get_file_by_url(self, snapshot_id: str, url_path: str, request) -> (dict, int):
        safe_path = unquote(url_path)
        comps = urlsplit(safe_path)
        protocol = comps.scheme
        host = comps.hostname
        port = comps.port
        if port is None:
            port = 443 if protocol == "https" else 80
        remote_path = comps.path or "/"

        params = request.args.to_dict(flat=False)
        print(params)
        
        query_values = (snapshot_id, protocol, host, port, remote_path, json.dumps(params))
        print(query_values)

        db = self.db
        db.row_factory = sqlite3.Row
        row = None
        try:
            with db:
                row = db.execute(
                    f"""
                    SELECT {self._file_params()}
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
        except Exception as e:
            logger.warning(f"Encountered unexpected error searching for a file by url: {e}")
            return self.internal_server_error("An unexpected error occured!")
        if row is None:
            return self.not_found(f"Failed to match url {safe_path} to a file in the DB")
        return self._file_from_row(row) 

    def _file_params(self) -> str:
        return """
            id, on_disk_path, json(response_headers) AS response_headers, response_code
        """

    def regexp(self, pattern, url):
        if url is None: return False
        return re.search(pattern, url) is not None

    def query_snapshots(self, request) -> (dict, int):
        payload = request.get_json(silent=True)
        res = self._json_check(payload)
        if res: return res

        start = float("-inf")
        end = float("inf") 
        url_reg = r"." # match anything in the db
        pattern = None
        try:
            start_spec = payload.get("start_time", {})
            if start_spec:
                start = self._time(start_spec)
            end_spec = payload.get("end_time", {})
            if end_spec:
                end = self._time(end_spec)
            raw_pattern = payload.get("url", "")
            if raw_pattern:
                url_reg = rf"{raw_pattern}"
        except KeyError:
            return self.bad_request("start time or end time spec improperly formated")
        except Exception as e:
            logger.warning(f"query_snapshots: Encountered unexpected error {e}")
            return self.internal_server_error("Encountered unexpected internal error")
        try:
            pattern = re.compile(url_reg)
        except re.error:
            return self.bad_request(f"The provided url-regex represents an invalid pattern {url_reg}")

        db = self.db
        db.row_factory = sqlite3.Row
        results = None
        try:
            with db:
                db.create_function("REGEXP", 2, self.regexp)

                results = db.execute(
                    """
                    SELECT *
                    FROM snapshots
                    WHERE start_time >= ?
                    AND end_time <= ?
                    AND url REGEXP ?
                    """,
                    (start, end, url_reg)
                ).fetchall()
        except Exception as e:
            logger.warning(f"query_snapshots: Encountered unexpected error in the db {e}")
            return self.internal_server_error("Encountered unexpected internal error")
        if results is None:
            return ({"content": []}, 200)
        ids = [row["id"] for row in results]
        return ({"content": ids}, 200)

    def query_files(self, request) -> (dict, int):
        payload = request.get_json(silent=True)
        res = self._json_check(payload)
        if res: return res

        other_conds = []
        other_vals = []

        snap_id = payload.get("snapshot_id", "")
        if snap_id:
            other_conds.append("snapshot_id = ?")
            other_vals.append(snap_id)

        try:
            start_spec = payload.get("start_time", {})
            if start_spec:
                start = self._time(start_spec)
                other_conds.append("request_sent_time >= ?")
                other_vals.append(start)
            end_spec = payload.get("end_time", {})
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
                self._build_pattern(payload, pattern_fields[field], field, other_conds, other_vals)
            self._url_subquery(payload, "url", other_conds, other_vals)
        except re.error:
            return self._bad_request("Failed to generate regex pattern for one of the provided regex options!")
        except Exception as e:
            logger.warning(f"query_files: Encountered unexpected error reading regex patterns: {e}")
            return self.internal_server_error("Encountered unexpected internal error")

        port = None
        try:
            raw_port = payload.get("port", "")
            if raw_port:
                port = int(raw_port)
                other_conds.append("port = ?")
                other_vals.append(port)
            codes = payload.get("status_codes", [])
            if not isinstance(codes, list):
                return self._bad_request(f"Expected a list for field 'status_codes', instead recieved {type(codes)}")
            list_params = ", ".join(["?"] * len(codes))
            if list_params:
                other_conds.append(f"response_code IN ({list_params})")
                other_vals.extend(codes)
        except TypeError, ValueError:
            return self._bad_request("Bad value provided for the port or status codes field")
        except Exception as e:
            logger.warning(f"query_files: Encountered unexpected error port values / status code: {e}")
            return self.internal_server_error("Encountered unexpected internal error")
        conditions_string = " AND ".join(other_conds)
        
        db = self.db
        db.row_factory = sqlite3.Row
        where_clause = f"WHERE {conditions_string}" if conditions_string else ""
        print(where_clause)
        print(other_vals)
        try:
            with db:
                db.create_function("REGEXP", 2, self.regexp)
                results = db.execute(
                    f"""
                    SELECT snapshot_id, id
                    FROM files
                    {where_clause}
                    """,
                    other_vals
                ).fetchall()
        except Exception as e:
            logger.warning(f"query_files: Encountered error in the db {e}")
            return self.internal_server_error("Encountered unexpected internal error")
        data = [
            {
                "snapshot_id": row["snapshot_id"],
                "file_id": row["id"]
            }
            for row in results
        ]
        return {"content": data}, 200


    def query_statistics(self, request):
        payload = request.get_json(silent=True)
        res = self._json_check(payload)
        if res: return res

        intervals: list[dict] = None

        intervals = payload.get("intervals", None)
        if not intervals:
            return self.bad_request("query_statistics requires payloads consisting of an array of interval objects")

        db = self.db
        db.row_factory(sqlite3.Row)
        results = []
        for interval in intervals:
            resp, status = self._process_interval(interval, db) 
            if status != 200:
                return (resp, status)
            results.append(resp)
        return {"statistics": results}, 200

    def _build_url(self, row) -> str:
        params = json.loads(row["request_parameters"])

        url = (
            f"/data/{row['snapshot_id']}/"
            f"{row['protocol']}://{row['host']}"
        )
        protocol = row["protocol"]
        port = row["port"]
        if not (
            (protocol == "https" and port == 443) or
            (protocol == "http" and port == 80)
        ):
            url += f":{port}"
        url+=row["remote_path"]
        if params:
            url += "?" + urlencode(params, doseq=True)
        return url

    def _process_interval(self,interval: dict, db) -> (dict, int):
        numeric = self._numeric_interval(interval)
        if numeric[0] and numeric[1] and numeric[0] > numeric[1]:
            return self.bad_request("Encountered bad interval object, start time > end time")
        conditions = []
        vals = []
        if numeric[0] is not None:
            conditions.append("start_time >= ?")
            vals.append(numeric[0])
        if numeric[1] is not None:
            conditions.append("start_time < ?")
            vals.append(numeric[1])
        condition_str = " AND ".join(conditions)
        where_clause = f"WHERE {condition_str}" if conditions else ""
        results = None
        with db:
            results = db.execute(
                f"""
                SELECT s.id AS snapshot_id, s.url, f.id AS file_id,
                    f.on_disk_path, f.host, f.file_size
                FROM snapshots AS s
                LEFT JOIN files AS f ON f.snapshot_id = s.id
                {where_clause}
                """,
                vals
            ).fetchall()
        if results is None:
            return self.internal_server_error("Hit unexpected error")
        snap_set = set()
        file_set = set()
        url_set = set()
        host_set = set()
        size: int = 0
        for result in results:
            snap_set.add(result["snapshot_id"])
            url_set.add(result["url"])
            if result["file_id"] is None: continue
            file_set.add(result["file_id"])
            host_set.add(result["host"])

            path = result["on_disk_path"]
            if not os.path.isfile(path):
                logger.warning(f"query_statistics: Unexpected snag: Found file in db {path}, but could not find file on local filesystem")
                return self.internal_server_error("Hit unexpected error: found path in db not reflected in local storage!")
            # matches if it is NULL or 0. Good probably
            if not result["file_size"]: 
                size += os.path.getsize(path)
            else: size += result["file_size"]
        return self._build_statistics(interval, len(snap_set), len(file_set), size, len(url_set), len(host_set)), 200
        

    def get_limits(self) -> (dict, int):
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        results = None
        try:
            results = db.execute(
                """
                SELECT MIN(start_time) AS first_snapshot, MAX(start_time) AS last_snapshot
                FROM snapshots
                """
            ).fetchone()
        except Exception as e:
            logger.warning(f"get_limits: Encountered unexpected DB error {e}")
            return self.internal_server_error("Encountered unexpected error querying snapshot limit statistics")

        first_snapshot = None
        last_snapshot = None
        if results:
            first_snapshot = (self._time_spec(results["first_snapshot"])
            if results["first_snapshot"] is not None
            else None)

            last_snapshot = (self._time_spec(results["last_snapshot"])
                if results["last_snapshot"] is not None
                else None)
        return ({
            "first_snapshot": first_snapshot,
            "last_snapshot": last_snapshot
        }, 200)
            



        
    def _url_subquery(self, payload, field: str, conditions: list, values: list):
        """ Callers must surround method in try catch block """
        raw_pattern = payload.get(field, "")
        if not raw_pattern: return None
        pattern = re.compile(raw_pattern)
        subquery = "snapshot_id IN (SELECT id FROM snapshots WHERE url REGEXP ?)"
        conditions.append(subquery)
        values.append(raw_pattern)

    
    def _build_pattern(self, payload, sql_name: str, field: str, conditions: list, values: list):
        """ Callers must surround this method in a try catch block """
        raw_pattern = payload.get(field, "")
        if not raw_pattern: return None
        pattern = re.compile(raw_pattern)
        # Need to catch and handle above error
        conditions.append(f"{sql_name} REGEXP ?")
        values.append(raw_pattern)


    def _file_from_row(self, row: dict) -> (dict, int):
        file_id = row["id"]
        disk_path = row["on_disk_path"]
        if not os.path.isfile(disk_path):
            return self.internal_server_error(f"Could not find file {file_id} locally at {disk_path}")

        body = None
        with open(disk_path, "rb") as file:
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



    def _time(self, ts: dict) -> float:
        if not ts: return None
        return ts["sec"] + ts["nsec"] / 1_000_000_000

    def _time_spec(self, t: float) -> dict:
        total_ns = round(t * 1_000_000_000)
        return {
            "sec": total_ns // 1_000_000_000,
            "nsec": total_ns % 1_000_000_000,
        }
    def _numeric_interval(self, interval_dict: dict) -> (float, float):
        raw_start = interval_dict.get("start", None)
        raw_end = interval_dict.get("end", None)
        if raw_start == 'null': raw_start = None
        if raw_end == 'null': raw_end = None
        start = self._time(raw_start)
        end = self._time(raw_end)
        return (start, end)


    def _build_interval(self, start: float, end: float) -> dict:
        return {"start": self._time_spec(start), "end": self._time_spec(end)}

    def _build_statistics(self, interval: dict, snapshots: int, files: int, size: int, urls: int, hosts: int) -> dict:
        return {
            "interval": interval,
            "snapshots": snapshots,
            "files": files,
            "size": size,
            "urls": urls,
            "hosts": hosts,
        }


        

    def internal_server_error(self, msg: str) -> (dict, int):
        return ({ "message": f"Internal Server Error: {msg}"}, 500) 

    def bad_request(self, msg: str) -> (dict, int):
        return ({"message": f"Bad Request: {msg}"}, 400)
    def not_found(self, msg: str) -> (dict, int):
        return ({"message": msg}, 404)


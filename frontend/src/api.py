#import sys
import re
import requests 

HOST = "http://localhost:8000" # Maybe import this from somewhere else later

def delete_snapshot(snapshot_id):
    return requests.request("DELETE", HOST + "/snapshots/" + snapshot_id, timeout=5)

def get_snapshot(snapshot_id):
    return requests.request("GET", HOST + "/snapshots/" + snapshot_id, timeout=5)

def get_file(file_id):
    return requests.request("GET", HOST + "/files/" + file_id, timeout=5)

def get_file_data(file_id):
    return requests.request("GET", HOST + "/files/" + file_id + "/data", timeout=5)

def query_snapshots(key, field):
    return requests.request("QUERY", HOST + "/search/snapshots", json={field: re.escape(key)}, timeout=5)

def query_files(key, field):
    return requests.request("QUERY", HOST + "/search/files", json={field: re.escape(key)}, timeout=5)


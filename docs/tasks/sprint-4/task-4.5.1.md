---
id: task-4.5.1
story: 4.5
sprint: 5
assignee: Alexander Rosenberg
estimate_hours: 4
---

# Modify the backend to support bookmarks

## Description
Add backend endpoints to allow creation, deletion, and query of bookmarks.

## Specs
- Allow bookmark creation under arbitrary names.
- Bookmarks should be identified by unique IDs that follow current conventions.
- Returned error codes should follow current conventions.

## Requirements
- Add a new table to the database.
- Add new endpoints to `API.org`.

## Acceptance criteria
- `/bookmarks/create` creates a bookmark and returns a new ID.
- `/search/bookmarks` allows searching for existing bookmarks.
- DELETE to `bookmarks/...` allows deleting bookmarks.

---
id: task-4.5.2
story: 4.5
sprint: 5
assignee: Alexander Rosenberg
estimate_hours: 4
---

# Modify the frontend to support bookmarks

## Description
Add frontend support for interfacing with the previously added bookmark
endpoints.

## Specs
- Allow creating bookmarks
- Allow searching and using bookmarks
- Allow deleting bookmarks
- Allow recreating bookmarks

## Requirements
- Use the backend's bookmark endpoints
- New endpoint functions are added to `api.py`

## Acceptance criteria
- Bookmarks can be created, searched, and deleted
- Bookmarks can be edited (recreated behind the scenes)
- Tests written for any utility functions that end up being needed

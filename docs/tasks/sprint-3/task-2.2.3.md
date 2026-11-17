---
id: task-2.2.3
story: 2.2
sprint: 3
assignee: Alexander Rosenberg
estimate_hours: 4
---

# Refine api.py and integrate it into (standardize API calls within) the UI/frontend

## Description
Task 2.2.3 was supposed to be completed during sprint 2, however, the assignee
went MIA (we have not had any contact for about 2 weeks now) and this task
involved looking at the the code he produced and fixing it up so it could be
used.

## Specs
- All API endpoints covered in `docs/API.org` have a corresponding function in
  `frontend/src/api.py` with the exception of the `/data/*` endpoints.
- API functions raise errors when the server response is malformed, including
  missing keys and wrong value types.
- API functions are asynchronous.

## Requirements
- Don't touch backend code, only frontend code.
- Introducing or changing libraries is OK, the original `requests` library does
  not handle async functions well.
- Existing  frontend tests must continue to pass.
- Code is usable to implement task 3.1.1, especially the search endpoint.

## Acceptance criteria
- Unit test suite for API endpoint functions.
- Added public utility functions have unit tests. Some non-public functions may
  also have tests.
- Non-trivial public functions and classes have documentation strings.
- Pull request has been reviewed by at least one other team member and
  permission given to merge.

---
id: task-3.1.1
story: 3.1
sprint: 3
assignee: Alexander Rosenberg
estimate_hours: 12
---

# Create a panel that allows the user to bring up a calendar view of snapshots taken for a specific toplevel URL.

## Description
Create an archive.org-esque calendar view for seeing a heatmap of snapshots
matching a particular query by date. Allow users to open these snapshots.

## Specs
- Call API functions asynchronously.
- Allow canceling an in-progress search.
- UI is unthemed so it can be integrated with the theme of the rest of the app.

## Requirements
- Don't touch existing UI files, create new ones.
- UI has a test harness that can be invoked by running the main UI file directly
- Don't directly place API request code in the UI code, use the `api.py` file.
- Use Qt Widget Designer to create UI files and compile them with `pyside6-uic`.
- UI has test data.

## Acceptance criteria
- `util/` files and `queries.py` have tests.
- UI launches with test data and can be navigated according to spec.
- Pictures of working UI posted in GitHub pull request.
- Pull request reviewed and approved before merge.

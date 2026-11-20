---
id: US-3.3-T-2
story: US-3.3
sprint: 4
assignee: Samin Salman
estimate_hours: 4
---

# Add multi-snapshot selection and deletion controls to the search view


## Description

Extend Webber's existing search view so that users can select multiple
archived snapshots and mark them for deletion.

This task covers snapshot selection, a deletion confirmation mechanism,
and feedback indicating whether deletion succeeded or failed. The
underlying archive deletion logic is out of scope and should be handled
through the existing or separately implemented backend interface.


## Specs

- In `frontend/src/main_window.py`, the search view allows users to
  select multiple archived snapshots using checkboxes or equivalent controls.
- Each snapshot can be selected or deselected independently without
  affecting other selections.
- The interface provides a Delete action for selected snapshots.
- The Delete action is disabled or unavailable when no snapshots
  are selected.
- Selecting Delete opens a confirmation dialog displaying the number
  of snapshots marked for deletion.
- Canceling the confirmation dialog leaves the archived snapshots
  unchanged.
- Confirming deletion passes the selected snapshot identifiers to the
  archive deletion interface.
- The interface displays confirmation feedback after successful deletion
  and an appropriate error message if deletion fails.
- After successful deletion, the search results refresh to reflect the
  remaining snapshots.


## Requirements

- Integrate selection and deletion controls into the existing search view.
- Support multiple selections without interfering with existing search
  and archive navigation functionality.
- Use unique snapshot identifiers to track selected archives.
- Require explicit confirmation before initiating deletion.
- Use the project's archive deletion interface rather than implementing
  deletion logic directly in the frontend.
- Provide accurate success and failure feedback.
- Preserve existing frontend functionality and ensure relevant tests
  continue to pass.


## Acceptance criteria

1. Each snapshot in the search results has a selection control.
2. Multiple snapshots can be selected and deselected independently.
3. The Delete action is unavailable when no snapshots are selected.
4. Selecting Delete displays a confirmation dialog identifying the
   number of selected snapshots.
5. Canceling the confirmation dialog does not delete any snapshots.
6. Confirming deletion passes the correct snapshot identifiers to
   the archive deletion interface.
7. Successful deletion displays confirmation feedback and refreshes
   the search results.
8. Failed deletion displays an error message without reporting success.
9. Existing search and archive navigation functionality continues
   to operate correctly.
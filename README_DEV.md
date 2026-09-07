# Testing Branch Overview

This branch tracks active development work that has not yet been merged into production. Use this branch to follow ongoing changes and review the current development status.

## Current Goals / Scope

### V0.3 User Intigration
- Submitter field
  - add submitter field to DB for workorders table. this field should not be editable by anyone at any time, but should be visible as plain text.
  - submitters name should use the Display Name field
  - rework of "Requested For / By:" for the WO submission will be needed
- Light / Dark mode
- Default view from log-in

### V0.4 Notifications
- User-defined notifications, including but not limited to:
  - add methods of being notifed
  - pair methods with content type
- What to notify on
  - When a work order is created or submitted
  - When a work order is edited
  - When a work order is completed
  - When a work order is reopened or reactivated
- How to notify
  - Internal status page
  - Email
  - Other notification methods, such as:
    - Text message
    - Push notification service, such as Pushover

## Active Focus

## Completed Work

## Known Issues

## Next Steps

## Notes
- proposed solution - Further feature expansion can make submitter and fulfiller roles too broad of roles
  - add new table that provides user groups/teams. each group/team can then have individualized submitter/fulfiller rights.

# Testing Branch Overview

This branch tracks active development work that has not yet been merged into production. Use this branch to follow ongoing changes and review the current development status.

## Current Focus

### User Management
- Adding users
  - User creation via Google account
  - Raw user creation
- Adding user roles, including but not limited to:
  - Submitter
  - Fulfiller

### Notifications
User-defined notifications, including but not limited to:

#### What to notify on
- When a work order is created or submitted
- When a work order is edited
- When a work order is completed
- When a work order is reopened or reactivated

#### How to notify
- Internal status page
- Email
- Other notification methods, such as:
  - Text message
  - Push notification service, such as Pushover

## Current Goals
- Google account integration for user creation

## Completed Work
- updated copyright notice to Version 0.2
- updated container name and port number in yml for side-by-side running with main branch
- added README_DEV.md for better version control
- added table creation for user control

## Known Issues
- 

## Next Steps
- 

## Notes
- Attempted to combine the contents of 'static' and 'templates' into a single folder called 'assets'. Found out that these two folders are default organizational folders of Flask.
- the volumes for templates and static kept the files from being updated at time of update.

# Testing Branch Overview

This branch tracks active development work that has not yet been merged into production. Use this branch to follow ongoing changes and review the current development status.

## Current Focus

### User Management
- Adding users
  - Raw user creation
- Adding user roles, including but not limited to:
  - Submitter
  - Fulfiller
  - Administrator

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
- User creation
  - Initial user creation (auto assigned admin role)
  - additional users (must be accepted by an admin, roles selected at time of acceptance)
- Profile page
  - review all personal info
  - change key personal info
- Notification page
  - add methods of being notifed
  - pair methods with content type

## Completed Work
- updated copyright notice to Version 0.2
- updated container name and port number in yml for side-by-side running with main branch
- added README_DEV.md for better version control
- added table creation for user control
- pre-populating user_roles table
- implemented user login and authentication gui
- implemented new user creation gui

## Known Issues
- Further feature expansion can make submitter and fulfiller roles too broad of roles
- profile edit for other users can happen by changing URL profile user number

## Next Steps
- Create user management method for admins

## Notes
- Attempted to combine the contents of 'static' and 'templates' into a single folder called 'assets'. Found out that these two folders are default organizational folders of Flask.
- The volumes for templates and static kept the files from being updated at time of update.
- Google account integration requires each installation to have it's own OAuth setup, which is more than i want to support at this point. may approach at a later date.
- User management will be the end of v0.2; user integration into system along with notifications will be v0.3

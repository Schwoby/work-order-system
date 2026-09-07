# Work Order System

A Flask-based work order tracking application designed to run in Docker. It uses SQLite for local data storage, supports creating and editing work orders, tracks completion status, and provides separate views for open and completed work orders.

## Repository

Source code: https://github.com/Schwoby/work-order-system/

## Overview

This project is intended to be run as a containerized application. Users can create their own local instance from the source code in this repository, while the application data is stored locally in a Docker volume-mounted directory.

The application includes:

- work order creation
- work order editing
- completion tracking
- open and completed work order views
- automatic local database initialization
- a container health check endpoint

## Versions / Release Channels

This project is intended to support two container image channels:

- **release** — the default and recommended version
- **testing** — used only for development and validation before changes are promoted to release

For normal use, the release channel should be used.

> Note: the testing channel is intended for project development and should not be used by typical users.

## Requirements

- Docker
- Docker Compose v2

## **Project Structure**

The application is organized around a role-based workflow and access model:
*   **Authentication and session management** — users sign in through the login flow, and the application tracks the active session for access control and routing.
*   **Role-based authorization** — access to pages and actions is governed by permission levels, including blocked statuses and active roles for submitters, fulfillers, and administrators.
*   **Profile completion workflow** — users must complete their profile before they can access work order functions.
*   **Work order lifecycle** — submitters create work orders, fulfillers review and update them, and completed work orders are separated from open work orders.
*   **Administrative oversight** — administrators can view users, review assigned roles, and manage user permissions.
*   **Persistent application data** — user accounts, roles, profile preferences, and work orders are stored in the application database for retrieval and updates across sessions.

## Data Location (SQLite)

The SQLite database will be stored locally at:
- `./data/database.db`

## Features

- Create new work orders
- Edit existing work orders
- Mark work orders as completed
- View open work orders
- View completed work orders
- Automatically store work order data in SQLite
- Health check endpoint for container monitoring
- Timezone-aware timestamps

## How It Works

The application runs as a Flask web app inside a Docker container.

- Flask listens on port `8080` inside the container
- Docker Compose maps that to host port `3003`
- The SQLite database is stored at `./data/database.db` within your local **root directory**
- The `templates/` and `static/` folders are mounted into the container so the app can use its HTML and static assets

## Getting Started

### 1. Create a local root directory
Create a local directory for the application to operate from (we recommend naming it `WorkOrderSystem`).

### 2. Create `docker-compose.yml` in your root directory
Create `docker-compose.yml` in this directory using your preferred text editor.

Then **copy/paste the contents** of the provided `docker-compose.yml` from the repository into your local `docker-compose.yml`.

When you copy/paste, update the following values as needed:

- **Time zone (`TZ`)**: set this to your local time zone so container timestamps reflect your local time.
- **Port mapping**: verify the host port will not conflict with anything else on your machine.  
  - Default mapping: container `8080` → host `3003`

### 3. Pull and start the container
From within the root directory, run:

```bash
docker compose pull && docker compose up -d
```

### 4. Open the application
After the container starts, access the app at:

- `http://localhost:3003`

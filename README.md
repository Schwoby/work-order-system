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

## Project Structure

The application depends on the following files and folders:

- `app.py` — main Flask application
- `Dockerfile` — container build instructions
- `docker-compose.yml` — service definition for running the app
- `requirements.txt` — Python dependency list
- `templates/` — HTML templates required by the app
- `static/` — static assets required by the app
- `data/` — local data directory for the SQLite database

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

## Data Location (SQLite)

The SQLite database will be stored locally at:

- `./data/database.db`

This path is relative to the **root directory you created** (`WorkOrderSystem/`). If the `data/` folder does not exist yet, it will be created as part of the container’s startup/initialization.

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

> Additional required files live in the `templates/` and `static/` folders. These folders may be reorganized in the future.

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
- The SQLite database is stored in `./data/database.db`
- The `templates/` and `static/` folders are mounted into the container so the app can use its HTML and static assets

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Schwoby/work-order-system.git
cd work-order-system

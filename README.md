# The Choices We Make

A Streamlit application with a PostgreSQL backend, reverse proxied by Nginx with automated Let's Encrypt SSL management.

## Getting Started

Follow these steps to get the application running on your local machine or server.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd thechoiceswemake
   ```

2. **Configure environment variables**:
   Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and provide your configuration:
   - `DB_PASSWORD`: A secure password for the database.
   - `ADMIN_PASSWORD_HASH`: (Optional) Hash for admin access.
   - `DOMAIN`: Your domain name (e.g., `example.com`). Leave empty for `localhost` testing.
   - `EMAIL`: Your email for Let's Encrypt notifications.

3. **Running Locally (HTTP)**:
   If you didn't set a `DOMAIN` in `.env`, the app will run on port 8080.
   ```bash
   docker-compose up -d
   ```
   Access the app at `http://localhost:8080`.

4. **Running in Production (HTTPS)**:
   Ensure your `DOMAIN` is set and pointing to your server's IP.
   Run the SSL initialization script:
   ```bash
   chmod +x init-letsencrypt.sh
   ./init-letsencrypt.sh
   ```
   This will handle the initial certificate request and reload Nginx.

### Project Structure

- `app.py`: Main Streamlit application.
- `utils/`: Utility modules for database, LLM, and UI components.
- `docker-compose.yaml`: Multi-container orchestration (App, DB, Nginx, Certbot).
- `nginx/`: Nginx configuration templates.
- `certbot/`: SSL certificate storage.
- `init-letsencrypt.sh`: Automation script for SSL setup.
- `init.sql`: Initial database schema.

## Database Management

- **Backups**: Use `./backup_db.sh` to create a manual dump of the database.
- **Data Persistence**: Database data is stored in the `choices-postgres-data` volume.

## License

This project is licensed under the Apache-2.0 License - see the [LICENSE](LICENSE) file for details.

## Architectural direction

Move postgres to a separate server.
Look at nginx load balancing
Alembic for database migrations

## Code direction

Tests
Users -> new.ycombinator.com style (no need for email)
Users can have channels for their scenarios
Put warnings on inappropriate journeys in archives

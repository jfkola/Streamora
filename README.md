# Streamora

A Flask-based video-on-demand application with user authentication,
resume playback, personalized category recommendations, watchlists,
administrative media management and Cloudinary video delivery.

## Features

- Secure account registration with password hashing
- Persistent playback progress and Continue Watching
- Recommendations based on viewing-category history
- AJAX-based watchlist management
- Role-protected administrative media management
- Chunked video uploads through Cloudinary
- PostgreSQL persistence and Render deployment
- Subscription-based video transformations

## Tech Stack

- **Backend:** Python, Flask, Flask-SQLAlchemy
- **Database:** PostgreSQL in production and SQLite for local development
- **Authentication:** Flask-Login and Werkzeug password hashing
- **Media delivery:** Cloudinary
- **Frontend:** Jinja2, Bootstrap 5 and JavaScript
- **Deployment:** Render and Gunicorn

## Recommendation Strategy

Streamora counts the categories represented in a user's viewing history,
selects the most frequently watched category and recommends unwatched titles
from that category. If no matching titles remain, it falls back to unwatched
catalog titles. This is a deterministic category-based recommender, not a
machine-learning model.

## Media Uploads

Administrative users upload videos through the protected media-management
interface. Videos are temporarily stored on disk and transferred through
Cloudinary's chunked upload API. Thumbnail images and optional subtitle files
are stored in Cloudinary as separate assets.

## Local Setup

1. Create and activate a Python virtual environment.
2. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and configure the required variables.
4. Apply database migrations:

   ```bash
   flask --app app db upgrade
   ```

5. Start the application:

   ```bash
   flask --app app run
   ```

## Deployment Guide (Render & GitHub)

This repository contains a `render.yaml` blueprint.

1. Push the repository to your GitHub account.
2. Link your GitHub account to [Render.com](https://render.com).
3. In the Render Dashboard, select **Blueprints** -> **New Blueprint Instance**.
4. Select the Streamora repository. Render will provision a PostgreSQL
   database, install dependencies from `requirements.txt`, run the app with
   Gunicorn and wire up `DATABASE_URL`.
5. Set `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` and
   `CLOUDINARY_API_SECRET` in the web service's Environment Variables tab.

## Contributors

- Rhea — initial Flask application and frontend experience
- Sanjay Balasubramaniam — security hardening, database migrations,
  automated testing, CI and backend maintainability improvements

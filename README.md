# Kenya's Trivia: Backend

Django + Django REST Framework + PostgreSQL backend for a Kenyan cultural party game
(DeKUT final-year project). Apps: `users`, `matches`, `cards`, `generations`.
The card model is called through `generations/model_client.py` (currently a stand-in).

## Setup
1. `python -m venv venv` and activate it, then `python -m pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill it in. Create a random secret with:
   `python -c "import secrets; print(secrets.token_urlsafe(60))"`
3. Create the PostgreSQL database named in `.env`, then `python manage.py migrate`
4. `python manage.py createcachetable` (only if the cache table is missing)
5. Run: `python manage.py runserver`, and in a second terminal `python manage.py run_generation_worker`
6. Tests: `python manage.py test` (59 tests)

API base path: `/api/v1/users/` and `/api/v1/matches/`.

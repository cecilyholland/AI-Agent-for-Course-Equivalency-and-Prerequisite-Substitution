# Backend Setup Instructions

## Install Requirements

### Install Python (3.10+)

Check your version:

```bash
python --version
```
## Install PostgreSQL (NOT via pip)
Mac
brew install postgresql@14
brew services start postgresql@14
Windows
Download and install PostgreSQL from:

https://www.postgresql.org/download/windows/

After installation, verify:

psql --version
## Create Virtual Environment
From the project root:

python -m venv venv
Activate the virtual environment:

Mac/Linux
source venv/bin/activate
Windows
venv\Scripts\activate
## Install Python Dependencies
pip install fastapi uvicorn sqlalchemy psycopg2-binary python-multipart python-dotenv

## Create the Database
Use this command to create the Database
```
createdb ai_db
```
If that does not work:

```
psql postgres
``` 
and 
```
CREATE DATABASE ai_db;
\q
```

## Load the Schema
From inside the Database folder run this command:

```
psql -U <your_postgres_username> -d ai_db -f db_schema.sql
```

## Set Environment Variable
Mac/Linux
```
export DATABASE_URL="postgresql+psycopg2://<username>@localhost:5432/ai_db"
```
Windows (PowerShell)
```
setx DATABASE_URL "postgresql+psycopg2://<username>@localhost:5432/ai_db"
```
After setting this, restart your terminal.

## Run the Backend
From the app/ directory:

```
uvicorn main:app --reload
```
Open your browser:

http://127.0.0.1:8000/docs
Swagger UI should load.


# Important Notes
Do NOT run pip install postgress (that is incorrect).

PostgreSQL must be installed separately.

If a database reset is needed:

```
dropdb ai_db
```
```
createdb ai_db
```
```
psql -U <username> -d ai_db -f db_schema.sql
```
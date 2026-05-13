import os

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# Superadmins — from env, always have full access, cannot be removed via bot
SUPERADMIN_IDS: set[int] = {
    int(x.strip())
    for x in os.getenv("SUPERADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:////data/db.sqlite3")

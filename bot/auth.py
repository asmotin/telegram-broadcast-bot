from bot.config import SUPERADMIN_IDS
from shared.database import SessionLocal
from shared.models import AdminUser


def is_admin(telegram_id: int) -> bool:
    """Returns True if user is a superadmin (env) or an active DB admin."""
    if telegram_id in SUPERADMIN_IDS:
        return True
    with SessionLocal() as db:
        return (
            db.query(AdminUser)
            .filter_by(telegram_id=telegram_id, is_active=1)
            .first()
        ) is not None


def is_superadmin(telegram_id: int) -> bool:
    return telegram_id in SUPERADMIN_IDS

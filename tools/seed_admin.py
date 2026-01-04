"""
Script de seed:  crear usuario admin si no existe
Uso: python tools/seed_admin.py
NO se ejecuta automáticamente en import-time
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import User
from config import settings
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def seed_admin():
    """Crear usuario admin si no existe"""
    db = SessionLocal()

    try:
        # Verificar si ya existe
        admin = db.query(User).filter(User.email == settings. ADMIN_EMAIL).first()

        if admin:
            print(f"✅ Usuario admin ya existe: {settings.ADMIN_EMAIL}")
            return

        # Crear admin
        hashed_password = pwd_context. hash(settings.ADMIN_PASSWORD)
        admin_user = User(
            email=settings.ADMIN_EMAIL,
            username="admin",
            hashed_password=hashed_password,
            full_name="Administrator",
            role="institutional",
            is_active=True
        )

        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print(f"✅ Usuario admin creado:")
        print(f"   Email: {settings.ADMIN_EMAIL}")
        print(f"   Password: {settings.ADMIN_PASSWORD}")
        print(f"   Role: institutional")

    except Exception as e:
        print(f"❌ Error creando admin: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("🌱 Seeding admin user...")
    seed_admin()
    print("✅ Seed completado")
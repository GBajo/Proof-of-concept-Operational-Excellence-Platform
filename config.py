import os
import secrets


class Config:
    DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "opex.db")
    DEBUG: bool = False
    # En producción, SECRET_KEY debe estar definida como variable de entorno.
    # En desarrollo, se genera un secreto aleatorio por sesión si no está configurada.
    SECRET_KEY: str = os.environ.get("SECRET_KEY", secrets.token_hex(32))


class DevelopmentConfig(Config):
    DEBUG: bool = True


class ProductionConfig(Config):
    DEBUG: bool = False


_env = os.environ.get("FLASK_ENV", "development")
config = ProductionConfig() if _env == "production" else DevelopmentConfig()

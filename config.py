import os


class Config:
    DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "opex.db")
    DEBUG: bool = False
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "opex-dev-secret")


class DevelopmentConfig(Config):
    DEBUG: bool = True


class ProductionConfig(Config):
    DEBUG: bool = False


_env = os.environ.get("FLASK_ENV", "development")
config = ProductionConfig() if _env == "production" else DevelopmentConfig()

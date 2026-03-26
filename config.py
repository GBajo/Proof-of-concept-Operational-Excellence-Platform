import os


class Config:
    DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "packline.db")
    DEBUG: bool = False
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "packline-dev-secret")


class DevelopmentConfig(Config):
    DEBUG: bool = True


config = DevelopmentConfig()

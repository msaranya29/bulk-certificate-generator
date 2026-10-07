import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./certificates.db")
CERTIFICATE_DIR = os.getenv("CERTIFICATE_DIR", "./certificates_output")
MAX_RECIPIENTS_PER_JOB = int(os.getenv("MAX_RECIPIENTS_PER_JOB", "5000"))

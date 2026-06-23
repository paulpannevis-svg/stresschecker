"""
VB Database Module - Centraal beheer van VB database operaties
"""
import sqlite3
import os
from contextlib import contextmanager

class VBDatabase:
    """Centraal beheer van VB database operaties"""
    
    DB_PATH = os.environ.get('VB_DB_PATH', '/opt/stresschecker-staging/sc_pro.db')
    
    @classmethod
    @contextmanager
    def connection(cls):
        """Context manager voor safe database connections"""
        db = sqlite3.connect(cls.DB_PATH)
        try:
            yield db
        finally:
            db.close()
    
    @classmethod
    def verify_login(cls, email: str, password: str) -> tuple:
        """
        Verify VB login credentials
        
        Returns: (success: bool, vb_data: tuple or None)
        vb_data = (id, license_key, vb_email, tier, credits_available)
        """
        email = email.lower().strip() if email else ''
        password = password.strip() if password else ''
        
        with cls.connection() as db:
            vb = db.execute(
                "SELECT id, license_key, vb_email, tier, credits_available "
                "FROM vb_credits "
                "WHERE vb_email = ? COLLATE NOCASE AND password = ?",
                (email, password)
            ).fetchone()
            
            return (vb is not None, vb)
    
    @classmethod
    def get_credits(cls, license_key: str) -> int:
        """Get available credits for a license key"""
        with cls.connection() as db:
            row = db.execute(
                "SELECT credits_available FROM vb_credits WHERE license_key = ?",
                (license_key,)
            ).fetchone()
            return row[0] if row else 0
    
    @classmethod
    def deduct_credit(cls, license_key: str) -> bool:
        """Deduct 1 credit after measurement"""
        with cls.connection() as db:
            db.execute(
                "UPDATE vb_credits SET credits_used = credits_used + 1 WHERE license_key = ?",
                (license_key,)
            )
            db.commit()
            return True

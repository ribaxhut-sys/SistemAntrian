"""
Repository layer.

Lapisan ini hanya mengurus pengambilan dan penyimpanan data. Tidak ada
aturan bisnis di sini; aturan bisnis berada di service layer.
"""

from app.repositories.user_repository import UserRepository

__all__ = ["UserRepository"]

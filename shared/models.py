from datetime import datetime

from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    username = Column(String(255), nullable=True)
    is_active = Column(Integer, default=1)  # 0 = bot was removed
    added_at = Column(DateTime, default=datetime.utcnow)

    labels = relationship("Label", secondary="group_labels", back_populates="groups")
    broadcasts = relationship("BroadcastLog", back_populates="group")


class Label(Base):
    __tablename__ = "labels"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    groups = relationship("Group", secondary="group_labels", back_populates="labels")
    broadcasts = relationship("Broadcast", back_populates="label")


class GroupLabel(Base):
    __tablename__ = "group_labels"
    __table_args__ = (UniqueConstraint("group_id", "label_id"),)

    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    label_id = Column(Integer, ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True)


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id = Column(Integer, primary_key=True)
    label_id = Column(Integer, ForeignKey("labels.id", ondelete="SET NULL"), nullable=True)
    message = Column(Text, nullable=False)
    parse_mode = Column(String(20), default="HTML")
    sent_at = Column(DateTime, default=datetime.utcnow)
    sent_by = Column(String(100))
    success_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)

    label = relationship("Label", back_populates="broadcasts")
    logs = relationship("BroadcastLog", back_populates="broadcast")


class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"

    id = Column(Integer, primary_key=True)
    broadcast_id = Column(Integer, ForeignKey("broadcasts.id", ondelete="CASCADE"))
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
    success = Column(Integer, default=1)
    error = Column(String(255), nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)

    broadcast = relationship("Broadcast", back_populates="logs")
    group = relationship("Group", back_populates="broadcasts")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    # "superadmin" entries come from env and are never stored here;
    # all rows here are role="admin"
    added_by_id = Column(BigInteger, nullable=True)
    added_by_name = Column(String(255), nullable=True)
    is_active = Column(Integer, default=1)
    added_at = Column(DateTime, default=datetime.utcnow)

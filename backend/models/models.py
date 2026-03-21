"""
ORM Models — v5 Plan B
Tables: categories, sections, documents, products, import_logs, parse_logs
New: categories table, pgvector embedding, search_text, full_text
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship, DeclarativeBase


def _now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    __allow_unmapped__ = True


class Category(Base):
    __tablename__ = "categories"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(256), unique=True, nullable=False, index=True)
    slug        = Column(String(256), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    icon        = Column(String(16), nullable=True)
    created_at  = Column(DateTime(timezone=True), default=_now)
    sections    = relationship("Section", back_populates="category")


class Section(Base):
    __tablename__ = "sections"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(256), nullable=False, index=True)
    slug        = Column(String(256), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    description = Column(Text, nullable=True)
    full_text   = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), default=_now)
    category    = relationship("Category", back_populates="sections")
    documents   = relationship("Document", back_populates="section")
    __table_args__ = (
        UniqueConstraint("slug", "category_id", name="uq_section_slug_cat"),
    )


class Document(Base):
    __tablename__ = "documents"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(512), nullable=False, index=True)
    file_url    = Column(String(1024), nullable=False, unique=True)
    status      = Column(String(32), default="pending", nullable=False)
    section_id  = Column(Integer, ForeignKey("sections.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    page_count  = Column(Integer, nullable=True)
    error_msg   = Column(Text, nullable=True)
    parsed_at   = Column(DateTime(timezone=True), nullable=True)
    created_at  = Column(DateTime(timezone=True), default=_now)
    section     = relationship("Section", back_populates="documents")
    products    = relationship("Product", back_populates="document", cascade="all, delete-orphan")
    __table_args__ = (Index("ix_documents_status", "status"),)


class Product(Base):
    __tablename__ = "products"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    document_id     = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    section_id      = Column(Integer, ForeignKey("sections.id"), nullable=True)
    category_id     = Column(Integer, ForeignKey("categories.id"), nullable=True)
    title           = Column(String(512), nullable=False, index=True)
    subtitle        = Column(String(512), nullable=True)
    sku             = Column(String(128), nullable=True, index=True)
    description     = Column(Text, nullable=True)
    certifications  = Column(Text, nullable=True)
    attributes      = Column(JSON, default=dict)
    variants        = Column(JSON, default=list)
    search_text     = Column(Text, nullable=True)
    image_bbox      = Column(JSON, nullable=True)
    page_number     = Column(Integer, nullable=True)
    created_at      = Column(DateTime(timezone=True), default=_now)
    document        = relationship("Document", back_populates="products")
    __table_args__ = (
        Index("ix_products_doc", "document_id"),
        Index("ix_products_section", "section_id"),
        Index("ix_products_category", "category_id"),
    )



class ProductIndex(Base):
    """
    Flat index of every searchable identifier:
    - product own SKU
    - every variant SKU/index from variants JSON
    One row per identifier. Allows instant lookup by any article number.
    """
    __tablename__ = "product_indexes"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    product_id  = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    index_value = Column(String(200), nullable=False)   # uppercase, normalized
    index_type  = Column(String(20), nullable=False)    # "sku" | "variant" | "alt"
    variant_row = Column(JSON, nullable=True)           # full variant data for this index
    __table_args__ = (
        Index("ix_product_indexes_value", "index_value"),
        Index("ix_product_indexes_product", "product_id"),
    )

class ImportLog(Base):
    __tablename__ = "import_logs"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    document_id   = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    document_name = Column(String(512), nullable=True)
    status        = Column(String(32), nullable=False)
    message       = Column(String(400), nullable=True)
    created_at    = Column(DateTime(timezone=True), default=_now)


class ParseLog(Base):
    __tablename__ = "parse_logs"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    level       = Column(String(16), nullable=False)
    message     = Column(String(400), nullable=False)
    created_at  = Column(DateTime(timezone=True), default=_now)

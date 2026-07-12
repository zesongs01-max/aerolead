import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from app.config import DATABASE_URL

Base = declarative_base()

class Tenant(Base):
    __tablename__ = "tenants"
    
    tenant_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    billing_plan = Column(String, default="starter")  # starter, growth, pro
    credit_balance = Column(Float, default=100.0)
    api_key = Column(String, unique=True, index=True, nullable=True)
    seat_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    saved_lists = relationship("SavedList", back_populates="tenant", cascade="all, delete-orphan")
    saved_audiences = relationship("SavedAudience", back_populates="tenant", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="tenant", cascade="all, delete-orphan")
    crm_syncs = relationship("CRMSync", back_populates="tenant", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.tenant_id"), nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="member")  # admin, member
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    tenant = relationship("Tenant", back_populates="users")

class Company(Base):
    __tablename__ = "companies"
    
    company_id = Column(String, primary_key=True)
    legal_name = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    domain = Column(String, index=True, nullable=False)
    website_url = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    hq_country = Column(String, index=True, nullable=True)
    hq_state = Column(String, nullable=True)
    hq_city = Column(String, nullable=True)
    employee_range = Column(String, nullable=True)
    revenue_range = Column(String, nullable=True)
    industry = Column(String, index=True, nullable=True)
    sub_industry = Column(String, nullable=True)
    founded_year = Column(Integer, nullable=True)
    public_private = Column(String, default="private")
    funding_stage = Column(String, nullable=True)
    technologies = Column(JSON, default=list)  # Stored as JSON array
    confidence_score = Column(Float, default=0.0)
    last_verified_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    people = relationship("Person", back_populates="company")
    domain_edges = relationship("DomainEdge", back_populates="company", cascade="all, delete-orphan")
    employment_edges = relationship("EmploymentEdge", back_populates="company", cascade="all, delete-orphan")
    tech_edges = relationship("TechEdge", back_populates="company", cascade="all, delete-orphan")

class Person(Base):
    __tablename__ = "people"
    
    person_id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.company_id"), nullable=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    title = Column(String, index=True, nullable=True)
    seniority = Column(String, index=True, nullable=True)  # exec, director, vp, manager, individual_contributor
    department = Column(String, index=True, nullable=True)  # sales, marketing, engineering, hr, finance, etc.
    email = Column(String, index=True, nullable=True)
    email_status = Column(String, default="unknown")  # verified, likely_valid, bouncing, unknown
    phone = Column(String, nullable=True)
    phone_status = Column(String, default="unknown")
    location = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    confidence_score = Column(Float, default=0.0)
    last_verified_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_suppressed = Column(Boolean, default=False)
    
    company = relationship("Company", back_populates="people")
    employment_history = relationship("EmploymentEdge", back_populates="person", cascade="all, delete-orphan")

# Graph Optimization Layer (relationships as structured edge tables)
class DomainEdge(Base):
    __tablename__ = "domain_edges"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String, ForeignKey("companies.company_id"), nullable=False)
    domain = Column(String, index=True, nullable=False)
    is_canonical = Column(Boolean, default=True)
    
    company = relationship("Company", back_populates="domain_edges")

class EmploymentEdge(Base):
    __tablename__ = "employment_edges"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(String, ForeignKey("people.person_id"), nullable=False)
    company_id = Column(String, ForeignKey("companies.company_id"), nullable=False)
    title = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    is_current = Column(Boolean, default=True)
    
    person = relationship("Person", back_populates="employment_history")
    company = relationship("Company", back_populates="employment_edges")

class TechEdge(Base):
    __tablename__ = "tech_edges"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String, ForeignKey("companies.company_id"), nullable=False)
    tech_slug = Column(String, index=True, nullable=False)
    category = Column(String, nullable=True)
    confidence = Column(Float, default=0.8)
    last_detected_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    company = relationship("Company", back_populates="tech_edges")

# Saved Lists
class SavedList(Base):
    __tablename__ = "saved_lists"
    
    list_id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.tenant_id"), nullable=False)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # people, companies
    entity_ids = Column(JSON, default=list)  # Stored as JSON array of strings
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    tenant = relationship("Tenant", back_populates="saved_lists")

# Saved Audiences / Searches
class SavedAudience(Base):
    __tablename__ = "saved_audiences"
    
    audience_id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.tenant_id"), nullable=False)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    name = Column(String, nullable=False)
    filter_json = Column(JSON, nullable=False)  # Stored as JSON search filters
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    tenant = relationship("Tenant", back_populates="saved_audiences")

# Field-Level Provenance & Survivorship
class FieldMetadata(Base):
    __tablename__ = "field_metadata"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String, index=True, nullable=False)  # person, company
    entity_id = Column(String, index=True, nullable=False)
    field_name = Column(String, index=True, nullable=False)
    source = Column(String, nullable=False)  # pdl, clearbit, builtwith, hunter, manual_verification
    confidence_score = Column(Float, nullable=False)
    last_updated_at = Column(DateTime, default=datetime.datetime.utcnow)

# CRM Sync configs
class CRMSync(Base):
    __tablename__ = "crm_syncs"
    
    sync_id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.tenant_id"), nullable=False)
    crm_type = Column(String, nullable=False)  # salesforce, hubspot
    is_active = Column(Boolean, default=False)
    credentials = Column(JSON, nullable=True)  # Encrypted/mock token details
    field_mapping = Column(JSON, nullable=False)  # Custom maps
    conflict_policy = Column(String, default="preserve")  # preserve (keep local edits), overwrite
    last_sync_at = Column(DateTime, nullable=True)
    sync_logs = Column(JSON, default=list)  # History list
    
    tenant = relationship("Tenant", back_populates="crm_syncs")

# Audit Logs
class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    log_id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.tenant_id"), nullable=False)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    action = Column(String, nullable=False)  # search, enrich, api_call, crm_sync, export
    target_type = Column(String, nullable=True)  # person, company, list, api_key
    target_id = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    tenant = relationship("Tenant", back_populates="audit_logs")

# Database Initialization
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

from __future__ import annotations
import os, uuid, hashlib, shutil, hmac, secrets, base64
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import create_engine, String, Text, DateTime, Integer, Boolean, ForeignKey, Index, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import io

BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / '.env')
database_url = os.getenv('DATABASE_URL', f"sqlite:///{(BACKEND_ROOT / 'evidence.db').as_posix()}")
if database_url.startswith('sqlite:///') and not database_url.startswith('sqlite:////'):
    database_path = Path(database_url[len('sqlite:///'):])
    if database_path != Path(':memory:') and not database_path.is_absolute():
        database_url = f"sqlite:///{(BACKEND_ROOT / database_path).resolve().as_posix()}"
DATABASE_URL = database_url
storage_path = Path(os.getenv('STORAGE_ROOT', 'storage'))
STORAGE_ROOT = (storage_path if storage_path.is_absolute() else BACKEND_ROOT / storage_path).resolve()
MAX_UPLOAD_MB = int(os.getenv('MAX_UPLOAD_MB', '50'))
APP_SECRET = os.getenv('APP_SECRET', 'development-only-change-me')
DEMO_MODE = os.getenv('DEMO_MODE', 'true').lower() == 'true'
for folder in ('originals', 'forensic_copies', 'reports'):
    (STORAGE_ROOT / folder).mkdir(parents=True, exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=lambda:str(uuid.uuid4()))
    username: Mapped[str]=mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str]=mapped_column(String(256))
    role: Mapped[str]=mapped_column(String(20), default='INVESTIGATOR')
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
class InvestigationCase(Base):
    __tablename__='cases'
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=lambda:str(uuid.uuid4()))
    case_number: Mapped[str]=mapped_column(String(32), unique=True, index=True)
    title: Mapped[str]=mapped_column(String(180), index=True)
    description: Mapped[str]=mapped_column(Text, default='')
    investigator: Mapped[str]=mapped_column(String(100), default='Demo Investigator')
    priority: Mapped[str]=mapped_column(String(20), default='MEDIUM')
    status: Mapped[str]=mapped_column(String(20), default='OPEN', index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    evidence: Mapped[list['Evidence']]=relationship(back_populates='case', cascade='all, delete-orphan')
class Evidence(Base):
    __tablename__='evidence'
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=lambda:str(uuid.uuid4()))
    case_id: Mapped[str]=mapped_column(ForeignKey('cases.id', ondelete='CASCADE'), index=True)
    name: Mapped[str]=mapped_column(String(180))
    evidence_type: Mapped[str]=mapped_column(String(80), default='DOCUMENT')
    description: Mapped[str]=mapped_column(Text, default='')
    source: Mapped[str]=mapped_column(String(180), default='')
    acquisition_method: Mapped[str]=mapped_column(String(100), default='Controlled file upload')
    device_info: Mapped[str]=mapped_column(String(250), default='')
    collected_by: Mapped[str]=mapped_column(String(100), default='Demo Investigator')
    collection_time: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[str]=mapped_column(Text, default='')
    original_filename: Mapped[str]=mapped_column(String(255))
    file_size: Mapped[int]=mapped_column(Integer)
    mime_type: Mapped[str]=mapped_column(String(150), default='application/octet-stream')
    original_sha256: Mapped[str]=mapped_column(String(64), index=True)
    storage_key: Mapped[str]=mapped_column(String(100), unique=True)
    status: Mapped[str]=mapped_column(String(30), default='ACQUIRED', index=True)
    last_hash: Mapped[Optional[str]]=mapped_column(String(64), nullable=True)
    last_verified_at: Mapped[Optional[datetime]]=mapped_column(DateTime, nullable=True)
    integrity_status: Mapped[str]=mapped_column(String(30), default='PENDING', index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    case: Mapped[InvestigationCase]=relationship(back_populates='evidence')
    custody_events: Mapped[list['CustodyEvent']]=relationship(back_populates='evidence', cascade='all, delete-orphan')
    copies: Mapped[list['ForensicCopy']]=relationship(back_populates='evidence', cascade='all, delete-orphan')
    verifications: Mapped[list['EvidenceVerification']]=relationship(back_populates='evidence', cascade='all, delete-orphan')
    acquisitions: Mapped[list['AcquisitionLog']]=relationship(back_populates='evidence', cascade='all, delete-orphan')
class CustodyEvent(Base):
    __tablename__='custody_events'
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=lambda:str(uuid.uuid4()))
    evidence_id: Mapped[str]=mapped_column(ForeignKey('evidence.id', ondelete='CASCADE'), index=True)
    event_type: Mapped[str]=mapped_column(String(40), index=True)
    actor: Mapped[str]=mapped_column(String(100))
    from_user: Mapped[str]=mapped_column(String(100), default='')
    to_user: Mapped[str]=mapped_column(String(100), default='')
    reason: Mapped[str]=mapped_column(Text, default='')
    notes: Mapped[str]=mapped_column(Text, default='')
    location: Mapped[str]=mapped_column(String(180), default='')
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow, index=True)
    evidence: Mapped[Evidence]=relationship(back_populates='custody_events')
class ForensicCopy(Base):
    __tablename__='forensic_copies'
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=lambda:str(uuid.uuid4()))
    evidence_id: Mapped[str]=mapped_column(ForeignKey('evidence.id', ondelete='CASCADE'), index=True)
    filename: Mapped[str]=mapped_column(String(255))
    file_size: Mapped[int]=mapped_column(Integer)
    sha256: Mapped[str]=mapped_column(String(64))
    created_by: Mapped[str]=mapped_column(String(100))
    storage_key: Mapped[str]=mapped_column(String(100), unique=True)
    purpose: Mapped[str]=mapped_column(Text, default='Forensic working copy')
    status: Mapped[str]=mapped_column(String(30), default='AVAILABLE')
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    evidence: Mapped[Evidence]=relationship(back_populates='copies')
class AcquisitionLog(Base):
    __tablename__='acquisition_logs'
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=lambda:str(uuid.uuid4()))
    evidence_id: Mapped[str]=mapped_column(ForeignKey('evidence.id', ondelete='CASCADE'), index=True)
    investigator: Mapped[str]=mapped_column(String(100))
    source: Mapped[str]=mapped_column(String(180), default='')
    method: Mapped[str]=mapped_column(String(100))
    filename: Mapped[str]=mapped_column(String(255))
    file_size: Mapped[int]=mapped_column(Integer)
    sha256: Mapped[str]=mapped_column(String(64))
    notes: Mapped[str]=mapped_column(Text, default='')
    result: Mapped[str]=mapped_column(String(30), default='SUCCESS')
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    evidence: Mapped[Evidence]=relationship(back_populates='acquisitions')
class EvidenceVerification(Base):
    __tablename__='evidence_verifications'
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=lambda:str(uuid.uuid4()))
    evidence_id: Mapped[str]=mapped_column(ForeignKey('evidence.id', ondelete='CASCADE'), index=True)
    expected_hash: Mapped[str]=mapped_column(String(64))
    actual_hash: Mapped[str]=mapped_column(String(64))
    verified: Mapped[bool]=mapped_column(Boolean)
    verified_by: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    evidence: Mapped[Evidence]=relationship(back_populates='verifications')
Index('ix_evidence_case_status', Evidence.case_id, Evidence.status)
Base.metadata.create_all(bind=engine)

app=FastAPI(title='Digital Evidence Acquisition & Integrity Verification API', version='1.0.0', description='Academic prototype: controlled file acquisition, SHA-256 integrity checks and custody tracking. Not certified forensic imaging.')
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in os.getenv('CORS_ORIGINS','http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001').split(',') if origin.strip()], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
security=HTTPBearer(auto_error=False)
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
def now(): return datetime.now(timezone.utc).replace(tzinfo=None)
def hash_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): digest.update(chunk)
    return digest.hexdigest()
def password_hash(password:str)->str:
    salt=secrets.token_bytes(16); dk=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,180000)
    return base64.b64encode(salt+dk).decode()
def password_ok(password:str, stored:str)->bool:
    try:
        raw=base64.b64decode(stored); salt, expected=raw[:16],raw[16:]
        return hmac.compare_digest(expected,hashlib.pbkdf2_hmac('sha256',password.encode(),salt,180000))
    except Exception:return False
def token_for(user:User)->str:
    payload=f'{user.id}|{user.username}|{user.role}|{int((datetime.utcnow()+timedelta(hours=12)).timestamp())}'
    encoded=base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')
    sig=hmac.new(APP_SECRET.encode(),encoded.encode(),hashlib.sha256).hexdigest()
    return encoded+'.'+sig
def current_user(creds:HTTPAuthorizationCredentials=Depends(security), db:Session=Depends(get_db)):
    if not creds: raise HTTPException(401,'Login required')
    try:
        encoded,sig=creds.credentials.split('.',1); expected=hmac.new(APP_SECRET.encode(),encoded.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected): raise ValueError()
        payload=base64.urlsafe_b64decode(encoded+'===').decode().split('|'); uid,username,role,exp=payload
        if int(exp)<int(datetime.utcnow().timestamp()): raise ValueError()
        user=db.get(User,uid)
        if not user: raise ValueError()
        return user
    except Exception: raise HTTPException(401,'Invalid or expired token')
def require_write(user:User=Depends(current_user)):
    if user.role=='VIEWER': raise HTTPException(403,'Viewer role is read-only')
    return user
def event(db,evidence_id,event_type,actor,reason='',notes='',from_user='',to_user='',location=''):
    db.add(CustodyEvent(evidence_id=evidence_id,event_type=event_type,actor=actor,reason=reason,notes=notes,from_user=from_user,to_user=to_user,location=location))
def case_out(c): return {'id':c.id,'case_number':c.case_number,'title':c.title,'description':c.description,'investigator':c.investigator,'priority':c.priority,'status':c.status,'created_at':c.created_at,'updated_at':c.updated_at,'evidence_count':len(c.evidence)}
def evidence_out(e): return {'id':e.id,'case_id':e.case_id,'case_number':e.case.case_number if e.case else None,'case_title':e.case.title if e.case else None,'name':e.name,'evidence_type':e.evidence_type,'description':e.description,'source':e.source,'acquisition_method':e.acquisition_method,'device_info':e.device_info,'collected_by':e.collected_by,'collection_time':e.collection_time,'notes':e.notes,'original_filename':e.original_filename,'file_size':e.file_size,'mime_type':e.mime_type,'original_sha256':e.original_sha256,'status':e.status,'integrity_status':e.integrity_status,'last_hash':e.last_hash,'last_verified_at':e.last_verified_at,'created_at':e.created_at,'copies_count':len(e.copies)}
def add_demo(db):
    if db.query(User).count()==0:
        db.add_all([User(username='admin',password_hash=password_hash('Forensics@123'),role='ADMIN'),User(username='investigator',password_hash=password_hash('Investigator@123'),role='INVESTIGATOR'),User(username='viewer',password_hash=password_hash('Viewer@123'),role='VIEWER')]); db.commit()
    if db.query(InvestigationCase).count()>0:return
    admin=db.query(User).filter_by(username='admin').first()
    cases=[]
    for n,title,priority,status,desc in [('DF-2026-014','Corporate Data Exfiltration','HIGH','ACTIVE','Review of a suspected unauthorized transfer of internal documents.'),('DF-2026-015','Phishing Email Investigation','MEDIUM','OPEN','Collection and integrity tracking for a suspicious email sample.'),('DF-2026-016','Endpoint Incident Review','LOW','ON_HOLD','Preservation of user-provided incident artefacts pending review.')]:
        c=InvestigationCase(case_number=n,title=title,priority=priority,status=status,description=desc,investigator='R. Gurram'); db.add(c); cases.append(c)
    db.commit()
    for idx,(c,name,content,typ,stat) in enumerate([(cases[0],'network-notes.txt',b'Sample network review notes. Academic demo artefact only.','DOCUMENT','VERIFIED'),(cases[1],'suspicious-email.txt',b'From: unknown@example.invalid\nSubject: Please review attachment\nDemo-only email content.','EMAIL','ACQUIRED'),(cases[2],'endpoint-timeline.txt',b'2026-10-08T10:12:00Z - Demo endpoint event\nNo real user data.','LOG','SEALED')]):
        key=str(uuid.uuid4()); path=STORAGE_ROOT/'originals'/key; path.write_bytes(content); digest=hash_file(path)
        e=Evidence(case_id=c.id,name=name,evidence_type=typ,description='Harmless synthetic evidence for demonstration.',source='Demo collection',acquisition_method='Controlled file upload',device_info='Demo workstation',collected_by='R. Gurram',notes='Synthetic demo data; not from a real investigation.',original_filename=name,file_size=len(content),mime_type='text/plain',original_sha256=digest,storage_key=key,status=stat,integrity_status='PENDING')
        db.add(e); db.commit(); db.refresh(e)
        db.add(AcquisitionLog(evidence_id=e.id,investigator=e.collected_by,source=e.source,method=e.acquisition_method,filename=name,file_size=len(content),sha256=digest,notes=e.notes))
        event(db,e.id,'ACQUIRED',e.collected_by,'Initial demo acquisition',e.notes,location='Demo evidence store')
        event(db,e.id,'REGISTERED',e.collected_by,'Evidence registered')
        if idx==0:
            db.add(EvidenceVerification(evidence_id=e.id,expected_hash=digest,actual_hash=digest,verified=True,verified_by='R. Gurram'))
            e.integrity_status='VERIFIED'; e.last_hash=digest; e.last_verified_at=now()
            copykey=str(uuid.uuid4()); shutil.copyfile(path,STORAGE_ROOT/'forensic_copies'/copykey)
            db.add(ForensicCopy(evidence_id=e.id,filename=name,file_size=len(content),sha256=hash_file(STORAGE_ROOT/'forensic_copies'/copykey),created_by='R. Gurram',storage_key=copykey,purpose='Demo working copy'))
            event(db,e.id,'COPIED','R. Gurram','Seeded demo forensic copy')
        db.commit()

@app.on_event('startup')
def startup():
    with SessionLocal() as db:
        if DEMO_MODE: add_demo(db)

class LoginBody(BaseModel): username:str; password:str
class CaseBody(BaseModel): title:str=Field(min_length=2,max_length=180); description:str=''; investigator:str=''; priority:str='MEDIUM'; status:str='OPEN'
class CaseUpdate(BaseModel): title:Optional[str]=None; description:Optional[str]=None; investigator:Optional[str]=None; priority:Optional[str]=None; status:Optional[str]=None
class CustodyBody(BaseModel): event_type:str='TRANSFERRED'; from_user:str=''; to_user:str=''; reason:str=''; notes:str=''; location:str=''
class StatusBody(BaseModel): status:str
class CopyBody(BaseModel): purpose:str='Forensic working copy'

@app.get('/health')
def health(): return {'status':'ok','service':'digital-evidence-api','prototype':True}
@app.post('/auth/login')
def login(body:LoginBody,db:Session=Depends(get_db)):
    user=db.query(User).filter_by(username=body.username).first()
    if not user or not password_ok(body.password,user.password_hash): raise HTTPException(401,'Incorrect username or password')
    return {'access_token':token_for(user),'token_type':'bearer','user':{'id':user.id,'username':user.username,'role':user.role}}
@app.get('/auth/me')
def me(user:User=Depends(current_user)): return {'id':user.id,'username':user.username,'role':user.role}
@app.get('/dashboard/stats')
def dashboard(db:Session=Depends(get_db),user:User=Depends(current_user)):
    cases=db.query(InvestigationCase).all(); evidence=db.query(Evidence).all(); events=db.query(CustodyEvent).order_by(CustodyEvent.created_at.desc()).limit(8).all()
    return {'total_cases':len(cases),'active_cases':sum(c.status in ('ACTIVE','OPEN') for c in cases),'total_evidence':len(evidence),'pending_verification':sum(e.integrity_status=='PENDING' for e in evidence),'verified_evidence':sum(e.integrity_status=='VERIFIED' for e in evidence),'integrity_failures':sum(e.integrity_status=='INTEGRITY_FAILED' for e in evidence),'cases_by_status':{s:sum(c.status==s for c in cases) for s in ('OPEN','ACTIVE','ON_HOLD','CLOSED')},'evidence_by_status':{s:sum(e.status==s for e in evidence) for s in ('ACQUIRED','SEALED','UNDER_ANALYSIS','VERIFIED','INTEGRITY_FAILED','RELEASED','ARCHIVED')},'recent_evidence':[evidence_out(e) for e in sorted(evidence,key=lambda x:x.created_at,reverse=True)[:6]],'recent_events':[{'id':x.id,'evidence_id':x.evidence_id,'evidence_name':x.evidence.name if x.evidence else '', 'event_type':x.event_type,'actor':x.actor,'created_at':x.created_at,'notes':x.notes} for x in events]}
@app.post('/cases',status_code=201)
def create_case(body:CaseBody,db:Session=Depends(get_db),user:User=Depends(require_write)):
    if body.status not in ('OPEN','ACTIVE','ON_HOLD','CLOSED') or body.priority not in ('LOW','MEDIUM','HIGH','CRITICAL'): raise HTTPException(422,'Invalid case status or priority')
    c=InvestigationCase(case_number=f'DF-{datetime.utcnow().year}-{secrets.randbelow(90000)+10000}',title=body.title,description=body.description,investigator=body.investigator or user.username,priority=body.priority,status=body.status); db.add(c); db.commit(); db.refresh(c); return case_out(c)
@app.get('/cases')
def list_cases(search:str='',status:str='',priority:str='',db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(InvestigationCase)
    if search:q=q.filter((InvestigationCase.title.ilike(f'%{search}%'))|(InvestigationCase.case_number.ilike(f'%{search}%')))
    if status:q=q.filter_by(status=status)
    if priority:q=q.filter_by(priority=priority)
    return [case_out(c) for c in q.order_by(InvestigationCase.created_at.desc()).all()]
@app.get('/cases/{case_id}')
def get_case(case_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    c=db.get(InvestigationCase,case_id) or db.query(InvestigationCase).filter_by(case_number=case_id).first()
    if not c: raise HTTPException(404,'Case not found')
    return {**case_out(c),'evidence':[evidence_out(e) for e in c.evidence]}
@app.put('/cases/{case_id}')
def update_case(case_id:str,body:CaseUpdate,db:Session=Depends(get_db),user:User=Depends(require_write)):
    c=db.get(InvestigationCase,case_id)
    if not c: raise HTTPException(404,'Case not found')
    data=body.model_dump(exclude_unset=True)
    for k,v in data.items():
        if k=='status' and v not in ('OPEN','ACTIVE','ON_HOLD','CLOSED'): raise HTTPException(422,'Invalid status')
        if k=='priority' and v not in ('LOW','MEDIUM','HIGH','CRITICAL'): raise HTTPException(422,'Invalid priority')
        setattr(c,k,v)
    c.updated_at=now(); db.commit(); db.refresh(c); return case_out(c)
@app.delete('/cases/{case_id}')
def delete_case(case_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if user.role!='ADMIN': raise HTTPException(403,'Admin role required to delete cases')
    c=db.get(InvestigationCase,case_id)
    if not c: raise HTTPException(404,'Case not found')
    if c.evidence: raise HTTPException(409,'Cases with evidence cannot be deleted; close or archive the case instead')
    db.delete(c); db.commit(); return {'deleted':True}
@app.post('/evidence',status_code=201)
async def register_evidence(case_id:str=Form(...),name:str=Form(...),evidence_type:str=Form('DOCUMENT'),description:str=Form(''),source:str=Form(''),acquisition_method:str=Form('Controlled file upload'),device_info:str=Form(''),collected_by:str=Form(''),collection_time:str=Form(''),notes:str=Form(''),file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(require_write)):
    c=db.get(InvestigationCase,case_id)
    if not c: raise HTTPException(404,'Selected case does not exist')
    original_name=Path(file.filename or 'evidence.bin').name
    key=str(uuid.uuid4()); path=STORAGE_ROOT/'originals'/key; digest=hashlib.sha256(); size=0
    try:
        with path.open('wb') as out:
            while True:
                chunk=await file.read(1024*1024)
                if not chunk: break
                size+=len(chunk)
                if size>MAX_UPLOAD_MB*1024*1024: raise HTTPException(413,f'File exceeds {MAX_UPLOAD_MB} MB limit')
                digest.update(chunk); out.write(chunk)
        if size==0: raise HTTPException(400,'Empty files cannot be registered')
        dt=now()
        if collection_time:
            try: dt=datetime.fromisoformat(collection_time.replace('Z','+00:00')).replace(tzinfo=None)
            except ValueError: raise HTTPException(422,'Invalid collection date/time')
        e=Evidence(case_id=case_id,name=name, evidence_type=evidence_type,description=description,source=source,acquisition_method=acquisition_method,device_info=device_info,collected_by=collected_by or user.username,collection_time=dt,notes=notes,original_filename=original_name,file_size=size,mime_type=file.content_type or 'application/octet-stream',original_sha256=digest.hexdigest(),storage_key=key,status='ACQUIRED',integrity_status='PENDING')
        db.add(e); db.commit(); db.refresh(e)
        db.add(AcquisitionLog(evidence_id=e.id,investigator=e.collected_by,source=source,method=acquisition_method,filename=original_name,file_size=size,sha256=e.original_sha256,notes=notes))
        event(db,e.id,'ACQUIRED',user.username,'Evidence uploaded and SHA-256 calculated server-side',notes,location='Controlled storage')
        event(db,e.id,'REGISTERED',user.username,'Evidence record created')
        db.commit(); return evidence_out(e)
    except Exception:
        if path.exists(): path.unlink(missing_ok=True)
        raise
    finally: await file.close()
@app.get('/evidence')
def list_evidence(search:str='',case_id:str='',status:str='',evidence_type:str='',verification_status:str='',db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(Evidence)
    if search:q=q.filter((Evidence.name.ilike(f'%{search}%'))|(Evidence.original_filename.ilike(f'%{search}%'))|(Evidence.id.ilike(f'%{search}%')))
    if case_id:q=q.filter_by(case_id=case_id)
    if status:q=q.filter_by(status=status)
    if evidence_type:q=q.filter_by(evidence_type=evidence_type)
    if verification_status:q=q.filter_by(integrity_status=verification_status)
    return [evidence_out(e) for e in q.order_by(Evidence.created_at.desc()).all()]
@app.get('/evidence/{evidence_id}')
def get_evidence(evidence_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=db.get(Evidence,evidence_id)
    if not e:raise HTTPException(404,'Evidence not found')
    return {**evidence_out(e),'custody':[{'id':x.id,'event_type':x.event_type,'actor':x.actor,'from_user':x.from_user,'to_user':x.to_user,'reason':x.reason,'notes':x.notes,'location':x.location,'created_at':x.created_at} for x in sorted(e.custody_events,key=lambda x:x.created_at)],'copies':[{'id':x.id,'filename':x.filename,'file_size':x.file_size,'sha256':x.sha256,'created_by':x.created_by,'purpose':x.purpose,'status':x.status,'created_at':x.created_at} for x in sorted(e.copies,key=lambda x:x.created_at,reverse=True)],'verifications':[{'id':x.id,'expected_hash':x.expected_hash,'actual_hash':x.actual_hash,'verified':x.verified,'verified_by':x.verified_by,'created_at':x.created_at} for x in sorted(e.verifications,key=lambda x:x.created_at,reverse=True)],'acquisitions':[{'id':x.id,'investigator':x.investigator,'source':x.source,'method':x.method,'filename':x.filename,'file_size':x.file_size,'sha256':x.sha256,'notes':x.notes,'result':x.result,'created_at':x.created_at} for x in e.acquisitions]}
@app.post('/evidence/{evidence_id}/verify')
def verify(evidence_id:str,db:Session=Depends(get_db),user:User=Depends(require_write)):
    e=db.get(Evidence,evidence_id)
    if not e:raise HTTPException(404,'Evidence not found')
    path=STORAGE_ROOT/'originals'/e.storage_key
    if not path.is_file(): raise HTTPException(500,'Stored evidence is missing; integrity could not be verified')
    actual=hash_file(path); verified=hmac.compare_digest(actual,e.original_sha256); timestamp=now()
    db.add(EvidenceVerification(evidence_id=e.id,expected_hash=e.original_sha256,actual_hash=actual,verified=verified,verified_by=user.username))
    e.last_hash=actual; e.last_verified_at=timestamp; e.integrity_status='VERIFIED' if verified else 'INTEGRITY_FAILED'
    if not verified:e.status='INTEGRITY_FAILED'
    elif e.status=='INTEGRITY_FAILED':e.status='VERIFIED'
    event(db,e.id,'VERIFIED' if verified else 'STATUS_CHANGED',user.username,'Integrity verification completed', 'Hash matched original' if verified else 'HASH MISMATCH: possible alteration or storage corruption')
    db.commit()
    return {'evidence_id':e.id,'expected_hash':e.original_sha256,'actual_hash':actual,'verified':verified,'tamper_detected':not verified,'verification_status':e.integrity_status,'verified_at':timestamp,'message':'Evidence integrity confirmed.' if verified else 'Integrity failure detected. Preserve the item and investigate.'}
@app.post('/dev/evidence/{evidence_id}/simulate-tamper')
def simulate_tamper(evidence_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not DEMO_MODE: raise HTTPException(404,'Not found')
    if user.role!='ADMIN': raise HTTPException(403,'Admin role required')
    e=db.get(Evidence,evidence_id)
    if not e: raise HTTPException(404,'Evidence not found')
    path=STORAGE_ROOT/'originals'/e.storage_key
    if not path.is_file(): raise HTTPException(404,'Stored evidence file not found')
    with path.open('r+b') as f:
        first=f.read(1)
        if not first: raise HTTPException(400,'Cannot tamper with an empty file')
        f.seek(0); f.write(bytes([first[0] ^ 1])); f.flush(); os.fsync(f.fileno())
    event(db,e.id,'STATUS_CHANGED',user.username,'DEMO ONLY: first byte altered to demonstrate integrity failure','Development-only tamper simulation; not a production feature')
    db.commit()
    return {'simulated':True,'evidence_id':e.id,'message':'One byte changed in the stored original for a controlled integrity-failure demonstration. Run Verify Integrity to observe the mismatch.'}

@app.post('/evidence/{evidence_id}/copies',status_code=201)
def create_copy(evidence_id:str,body:CopyBody,db:Session=Depends(get_db),user:User=Depends(require_write)):
    e=db.get(Evidence,evidence_id)
    if not e:raise HTTPException(404,'Evidence not found')
    src=STORAGE_ROOT/'originals'/e.storage_key
    if not src.is_file():raise HTTPException(500,'Original evidence file is missing')
    key=str(uuid.uuid4()); dst=STORAGE_ROOT/'forensic_copies'/key
    try:shutil.copyfile(src,dst); digest=hash_file(dst)
    except OSError as exc:dst.unlink(missing_ok=True);raise HTTPException(500,f'Unable to create copy: {exc}')
    if not hmac.compare_digest(digest,hash_file(src)):
        dst.unlink(missing_ok=True);raise HTTPException(500,'Copy verification failed; copy was discarded')
    cp=ForensicCopy(evidence_id=e.id,filename=e.original_filename,file_size=dst.stat().st_size,sha256=digest,created_by=user.username,storage_key=key,purpose=body.purpose);db.add(cp)
    event(db,e.id,'COPIED',user.username,'Forensic copy created and hash checked',body.purpose)
    db.commit();db.refresh(cp);return {'id':cp.id,'evidence_id':cp.evidence_id,'filename':cp.filename,'file_size':cp.file_size,'sha256':cp.sha256,'created_by':cp.created_by,'purpose':cp.purpose,'status':cp.status,'created_at':cp.created_at}
@app.get('/evidence/{evidence_id}/copies')
def list_copies(evidence_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not db.get(Evidence,evidence_id):raise HTTPException(404,'Evidence not found')
    return [{'id':x.id,'evidence_id':x.evidence_id,'filename':x.filename,'file_size':x.file_size,'sha256':x.sha256,'created_by':x.created_by,'purpose':x.purpose,'status':x.status,'created_at':x.created_at} for x in db.query(ForensicCopy).filter_by(evidence_id=evidence_id).all()]
@app.get('/copies/{copy_id}')
def get_copy(copy_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    x=db.get(ForensicCopy,copy_id)
    if not x:raise HTTPException(404,'Copy not found')
    return {'id':x.id,'evidence_id':x.evidence_id,'filename':x.filename,'file_size':x.file_size,'sha256':x.sha256,'created_by':x.created_by,'purpose':x.purpose,'status':x.status,'created_at':x.created_at}
@app.get('/evidence/{evidence_id}/custody')
def custody(evidence_id:str,event_type:str='',actor:str='',db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not db.get(Evidence,evidence_id):raise HTTPException(404,'Evidence not found')
    q=db.query(CustodyEvent).filter_by(evidence_id=evidence_id)
    if event_type:q=q.filter_by(event_type=event_type)
    if actor:q=q.filter(CustodyEvent.actor.ilike(f'%{actor}%'))
    return [{'id':x.id,'event_type':x.event_type,'actor':x.actor,'from_user':x.from_user,'to_user':x.to_user,'reason':x.reason,'notes':x.notes,'location':x.location,'created_at':x.created_at} for x in q.order_by(CustodyEvent.created_at.desc()).all()]
@app.post('/evidence/{evidence_id}/custody',status_code=201)
def add_custody(evidence_id:str,body:CustodyBody,db:Session=Depends(get_db),user:User=Depends(require_write)):
    e=db.get(Evidence,evidence_id)
    if not e:raise HTTPException(404,'Evidence not found')
    allowed={'TRANSFERRED','ACCESSED','SEALED','RELEASED','EXPORTED','STATUS_CHANGED','REGISTERED','ACQUIRED','VERIFIED','COPIED'}
    if body.event_type not in allowed:raise HTTPException(422,'Unsupported custody event type')
    event(db,e.id,body.event_type,user.username,body.reason,body.notes,body.from_user,body.to_user,body.location);db.commit()
    return {'created':True,'evidence_id':e.id,'event_type':body.event_type}
@app.patch('/evidence/{evidence_id}/status')
def set_status(evidence_id:str,body:StatusBody,db:Session=Depends(get_db),user:User=Depends(require_write)):
    allowed={'REGISTERED','ACQUIRED','SEALED','UNDER_ANALYSIS','VERIFIED','INTEGRITY_FAILED','RELEASED','ARCHIVED'}
    if body.status not in allowed:raise HTTPException(422,'Invalid evidence status')
    e=db.get(Evidence,evidence_id)
    if not e:raise HTTPException(404,'Evidence not found')
    old=e.status;e.status=body.status;event(db,e.id,'STATUS_CHANGED',user.username,f'Status changed from {old} to {body.status}');db.commit();return evidence_out(e)
@app.get('/evidence/{evidence_id}/acquisition')
def acquisition(evidence_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not db.get(Evidence,evidence_id):raise HTTPException(404,'Evidence not found')
    return [{'id':x.id,'investigator':x.investigator,'source':x.source,'method':x.method,'filename':x.filename,'file_size':x.file_size,'sha256':x.sha256,'notes':x.notes,'result':x.result,'created_at':x.created_at} for x in db.query(AcquisitionLog).filter_by(evidence_id=evidence_id).order_by(AcquisitionLog.created_at.desc()).all()]
@app.get('/evidence/{evidence_id}/download')
def download_evidence(evidence_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=db.get(Evidence,evidence_id)
    if not e:raise HTTPException(404,'Evidence not found')
    path=STORAGE_ROOT/'originals'/e.storage_key
    if not path.is_file():raise HTTPException(404,'Stored evidence file not found')
    event(db,e.id,'ACCESSED',user.username,'Evidence download requested');db.commit()
    return FileResponse(path,filename=e.original_filename,media_type='application/octet-stream')
@app.get('/cases/{case_id}/report')
def case_report(case_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    c=db.get(InvestigationCase,case_id)
    if not c:raise HTTPException(404,'Case not found')
    return make_pdf(f'Case Report — {c.case_number}',[('Case number',c.case_number),('Title',c.title),('Investigator',c.investigator),('Status',c.status),('Priority',c.priority),('Description',c.description),('Generated at',now().isoformat()),('Evidence count',str(len(c.evidence)))]+[(f'Evidence: {e.name}',f'ID: {e.id} | Status: {e.status} | Integrity: {e.integrity_status} | Size: {e.file_size} bytes | SHA-256: {e.original_sha256}') for e in c.evidence]+[(f'Custody event — {ev.event_type}',f'{ev.created_at.isoformat()} | {ev.actor} | {ev.reason} {ev.notes}') for e in c.evidence for ev in sorted(e.custody_events,key=lambda x:x.created_at)])
@app.get('/evidence/{evidence_id}/report')
def evidence_report(evidence_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=db.get(Evidence,evidence_id)
    if not e:raise HTTPException(404,'Evidence not found')
    rows=[('Evidence ID',e.id),('Case',e.case.case_number+' — '+e.case.title),('Name',e.name),('Type',e.evidence_type),('Source',e.source),('Collector',e.collected_by),('Acquisition time',e.collection_time.isoformat()),('Original filename',e.original_filename),('File size',f'{e.file_size} bytes'),('MIME type',e.mime_type),('Status',e.status),('Integrity status',e.integrity_status),('Original SHA-256',e.original_sha256),('Last observed SHA-256',e.last_hash or 'Not verified'),('Last verification',e.last_verified_at.isoformat() if e.last_verified_at else 'Not verified'),('Acquisition method',e.acquisition_method),('Notes',e.notes),('Generated at',now().isoformat())]
    rows += [(f'Custody — {x.event_type}',f'{x.created_at.isoformat()} | {x.actor} | {x.reason} {x.notes}') for x in sorted(e.custody_events,key=lambda x:x.created_at)]
    rows += [(f'Forensic copy — {x.filename}',f'{x.created_at.isoformat()} | {x.created_by} | SHA-256: {x.sha256} | {x.purpose}') for x in e.copies]
    rows += [(f'Verification — {x.verified}',f'{x.created_at.isoformat()} | expected {x.expected_hash} | actual {x.actual_hash} | by {x.verified_by}') for x in e.verifications]
    return make_pdf(f'Evidence Report — {e.name}',rows)
def make_pdf(title,rows):
    buff=io.BytesIO(); doc=SimpleDocTemplate(buff,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=48,bottomMargin=42); styles=getSampleStyleSheet(); story=[Paragraph('DIGITAL FORENSICS / EVIDENCE MANAGEMENT',styles['Kicker'] if 'Kicker' in styles else styles['Normal']),Spacer(1,8),Paragraph(title,styles['Title']),Spacer(1,8),Paragraph('Academic prototype report. This document records application data and is not a certification of forensic acquisition.',styles['Italic']),Spacer(1,18)]
    for label,value in rows:
        story.append(Paragraph(str(label).replace('&','&amp;').replace('<','&lt;'),styles['Heading4'])); story.append(Paragraph(str(value or '—').replace('&','&amp;').replace('<','&lt;').replace('\n','<br/>'),styles['BodyText'])); story.append(Spacer(1,6))
    def footer(canvas,doc):
        canvas.saveState(); canvas.setFont('Helvetica',8); canvas.setFillColor(colors.grey); canvas.drawString(42,22,'DIGITAL EVIDENCE SYSTEM • ACADEMIC PROTOTYPE'); canvas.drawRightString(A4[0]-42,22,f'Page {doc.page}'); canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer);buff.seek(0)
    safe_name=''.join(ch if ch.isascii() and (ch.isalnum() or ch in '._-') else '_' for ch in title[:40]).strip('_') or 'report'
    return StreamingResponse(buff,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{safe_name}.pdf"'})

from app.core.config import settings
from app.core.database import SessionLocal
from app.repositories.project_repository import ProjectRepository
from app.models.project import Project
import urllib.parse

print('DATABASE_URL =', settings.DATABASE_URL)
session = SessionLocal()
try:
    proj = session.query(Project).filter(Project.id==19).first()
    if not proj:
        print('Project id 19 not found')
    else:
        print('project.id=', proj.id)
        print('project.local_path raw=', repr(getattr(proj, 'local_path', None)))
        print('project.local_path (as stored) =', proj.local_path)

    decoded = urllib.parse.unquote('d:%5CProgramming+Files%5CJava%5CChatGIS-server')
    print('decoded query param =', decoded)

    repo = ProjectRepository(Project, session)
    r1 = repo.get_by_local_path(decoded)
    print('repo.get_by_local_path(decoded) ->', getattr(r1, 'id', None))
    raw_q = r"d:\\Programming Files\\Java\\ChatGIS-server"
    r2 = repo.get_by_local_path(raw_q)
    print('repo.get_by_local_path(raw_q) ->', getattr(r2, 'id', None))

    allp = session.query(Project).filter(Project.local_path!=None).limit(20).all()
    print('\nSample stored local_paths:')
    for p in allp:
        print(p.id, '->', repr(p.local_path))
finally:
    session.close()

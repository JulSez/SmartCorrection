"""Local browser application; standard-library HTTP, no hosted service or AI API."""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
from urllib.parse import urlsplit, parse_qs
import webbrowser
from .db import DEFAULT_DB
from .gui_prompts_v2 import make_prompt
from .workflow_v2 import WorkflowApplication as Application

WEB = Path(__file__).with_name('web')
MAX_BODY = 160 * 1024 * 1024


def make_server(app, port=0):
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _trusted(self, mutation=False):
            allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in allowed:
                return False
            origin=self.headers.get('Origin')
            if origin and origin not in {'http://'+host for host in allowed}:
                return False
            return not mutation or secrets.compare_digest(self.headers.get('X-SmartCorrection-Token',''),token)

        def _send(self, status, content, mime='application/json; charset=utf-8'):
            raw=content if isinstance(content,bytes) else json.dumps(content,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            ancestors = "'self'" if status == 200 and mime == 'application/pdf' else "'none'"
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; object-src 'self'; base-uri 'none'; frame-ancestors "+ancestors)
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if not self._trusted():
                return self._send(403,{'erreur':'Origine non autorisée'})
            try:
                parsed=urlsplit(self.path);path=parsed.path;query=parse_qs(parsed.query)
                if path=='/':
                    self._send(200,(WEB/'index.html').read_text(encoding='utf-8').replace('__TOKEN__',token).encode('utf-8'),'text/html; charset=utf-8')
                elif path in {'/app.js','/grid-preview.js','/workflow-v2.js','/layout-v3.js','/hotfix-pr20.js','/fast-workflow.js','/style.css'}:
                    mime='text/javascript' if path.endswith('.js') else 'text/css'
                    self._send(200,(WEB/path[1:]).read_bytes(),mime+'; charset=utf-8')
                elif path=='/api/home':
                    self._send(200,app.home())
                elif path=='/api/dossier':
                    self._send(200,app.state(query.get('id',[''])[0]))
                elif path=='/api/prompt':
                    with app.lock:
                        text=make_prompt(app,query.get('id',[''])[0],query.get('etape',[''])[0],query.get('version',[None])[0],query.get('mode',['echantillon'])[0])
                    self._send(200,{'texte':text})
                elif path=='/api/consignes':
                    from .instructions import policies
                    self._send(200,policies(app,query.get('classe',[''])[0],query.get('type',[''])[0]))
                elif path=='/api/history':
                    self._send(200,app.instruction_history(query.get('classe',[''])[0]))
                elif path=='/api/layout-preview':
                    with app.lock:
                        preview=app.layout_preview(query.get('id',[''])[0])
                    self._send(200,preview,'application/pdf')
                elif path=='/api/corrige-preview':
                    with app.lock:
                        preview=app.corrige_preview(query.get('id',[''])[0])
                    self._send(200,preview,'application/pdf')
                elif path=='/api/grid-preview':
                    with app.lock:
                        preview=app.grid_preview(query.get('id',[''])[0])
                    self._send(200,preview,'application/pdf')
                elif path=='/file':
                    file=app.file(query.get('kind',[''])[0],query.get('id',[''])[0],query.get('name',[None])[0])
                    self._send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                else:
                    self._send(404,{'erreur':'Page introuvable'})
            except (ValueError, OSError, sqlite3.Error, RuntimeError) as exc:
                self._send(400,{'erreur':str(exc)})

        def do_POST(self):
            if not self._trusted(mutation=True):
                return self._send(403,{'erreur':'Requête non autorisée. Recharger la page.'})
            if self.path!='/api/action' or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                return self._send(400,{'erreur':'Requête JSON attendue'})
            data={}
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>MAX_BODY:
                    return self._send(413,{'erreur':'Fichier trop volumineux (environ 120 Mo maximum)'})
                data=json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(data,dict):
                    raise ValueError('Objet JSON attendu')
                with app.lock:
                    result=dispatch(app,data)
                self._send(200,result)
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,RuntimeError) as exc:
                message=str(exc)
                if isinstance(exc,PermissionError):
                    message='Accès aux fichiers refusé. Fermez les PDF ouverts, puis réessayez. Si le problème persiste, vérifiez les droits du dossier de sortie et si sa synchronisation le verrouille. Ce problème se traite dans Windows, pas auprès de l’IA.\n\n'+message
                reparable=(isinstance(exc,ValueError) and isinstance(data,dict)
                           and data.get('action') in {'echange','corrige'})
                self._send(400,{'erreur':message,'reponse_reparable':reparable})

    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def dispatch(app,data):
    action=data.get('action');ident=data.get('dossier')
    commit=data.get('valider',False)
    if type(commit) is not bool:
        raise ValueError('Validation invalide')
    if action=='classe': return app.roster(data['classe'],data['texte'],commit,data.get('rapprochements'),data.get('empreinte'))
    if action=='archiver': return app.archive(ident,data.get('actif'))
    if action=='supprimer': return app.delete(ident,data.get('confirmer',False))
    if action=='creer': return app.create(data['classe'],data['titre'],data.get('type_epreuve',''))
    if action=='consigne':
        from .instructions import replace_policy
        return replace_policy(app,data['portee'],data.get('classe',''),data.get('type_epreuve',''),data['texte'],data['base'])
    if action=='type_epreuve':
        from .instructions import set_type
        return set_type(app,ident,data['type_epreuve'])
    if action=='upload': return app.upload(ident,data['role'],data['nom'],data['contenu'])
    if action=='anonymat': return app.save_anonymity(ident,data.get('actif',True))
    if action=='formats':
        if 'layout' in data: return app.save_layout(ident,data['layout'])
        return app.save_formats(ident,data.get('correction','A6'),data.get('corrige','A6'))
    if action=='brouillon': return app.draft(ident,data['etape'],data['texte'])
    if action=='echange': return app.exchange(ident,data['etape'],data['texte'],commit)
    if action=='corrige':
        if app.state(ident)['dossier']['revision']!=data.get('revision'):
            raise ValueError('La grille a changé ; recharger le dossier')
        return app.corrige(ident,data['version'],data['texte'],commit)
    if action=='echantillon': return app.sample(ident,data['references'],commit)
    if action=='groupes': return app.groups(ident,data.get('actif'),data.get('texte'))
    if action=='revue': return app.review(ident,data['reference'])
    if action=='selection_finale': return app.include_in_final(ident,data['reference'],data.get('inclure'))
    if action=='generer': return app.generate(ident,final=data.get('final',False),pdf=data.get('pdf',True))
    raise ValueError('Action inconnue')


def serve(db_path=DEFAULT_DB, data_dir='private/interface', port=8765, open_browser=True):
    try:
        import pypdf  # noqa: F401
    except ImportError as exc:
        raise RuntimeError('Installer l’interface avec : python -m pip install ".[gui]"') from exc
    app=Application(db_path,data_dir)
    server=make_server(app,port)
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'SmartCorrection : {url}\nGarder cette fenêtre ouverte. Ctrl+C pour arrêter.',flush=True)
    if open_browser:
        threading.Timer(.4,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8',errors='replace')
        sys.stderr.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser(description='Interface locale SmartCorrection')
    parser.add_argument('--db',default=str(DEFAULT_DB))
    parser.add_argument('--data-dir',default='private/interface')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args(argv)
    try:
        serve(args.db,args.data_dir,args.port,not args.no_browser)
        return 0
    except (OSError,RuntimeError,ValueError,sqlite3.Error) as exc:
        print(f'Erreur : {exc}',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())

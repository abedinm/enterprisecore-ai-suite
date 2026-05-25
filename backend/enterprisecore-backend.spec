# PyInstaller spec for the EnterpriseCore FastAPI sidecar.
# Built with: pyinstaller enterprisecore-backend.spec
# Output: dist/enterprisecore-backend.exe
from __future__ import annotations

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

BACKEND_DIR = Path('.').resolve()

block_cipher = None

hiddenimports = []
hiddenimports += collect_submodules('app')
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('alembic')
hiddenimports += collect_submodules('sqlalchemy.dialects')
hiddenimports += [
    'email_validator',
    'passlib.handlers.bcrypt',
    'jose.backends.cryptography_backend',
    'reportlab.graphics.barcode.code39',
    'reportlab.graphics.barcode.code93',
    'reportlab.graphics.barcode.code128',
    'reportlab.graphics.barcode.usps',
    'reportlab.graphics.barcode.qr',
    'multipart',
    'python_multipart',
    'h11',
    'websockets',
    'wsproto',
    'anyio._backends._asyncio',
    # Added by consolidation: Jinja2 (marketing public renderer), keyring
    # (Holy Grail-style provider-key storage), markdown rendering for posts.
    'jinja2',
    'jinja2.ext',
    'keyring',
    'keyring.backends',
    'keyring.backends.Windows',
    # Added by enterprise build (Phases 6-9):
    'authlib',                           # SSO OIDC
    'authlib.integrations.requests_client',
    'authlib.jose',
    'stripe',                            # Billing
    'prometheus_client',                 # Observability /metrics
    'prometheus_client.exposition',
    'opentelemetry',                     # Tracing
    'opentelemetry.sdk',
    'opentelemetry.sdk.trace',
    'opentelemetry.sdk.trace.export',
    'opentelemetry.instrumentation.fastapi',
    'opentelemetry.instrumentation.sqlalchemy',
    'opentelemetry.instrumentation.httpx',
    'opentelemetry.exporter.otlp.proto.http.trace_exporter',
    'sentry_sdk',                        # Error tracking (no-op when DSN unset)
    'sentry_sdk.integrations.fastapi',
    'sentry_sdk.integrations.sqlalchemy',
    'sentry_sdk.integrations.loguru',
    'httpx',                             # Outbound for webhooks/integrations
    'ulid',                              # Request IDs
    'redis',                             # Optional event-bus backend
]

datas = []
# Ship alembic migrations + ini so the sidecar can self-migrate on first launch.
datas.append(('alembic', 'alembic'))
datas.append(('alembic.ini', '.'))
# Marketing public site renderer needs its Jinja2 templates at runtime.
datas.append(('app/templates', 'app/templates'))
# Industry template descriptors loaded by app/services/marketing.py.
datas.append(('app/data', 'app/data'))
# Embeddable chat widget served at GET /widget.js.
datas.append(('app/static', 'app/static'))
# Pydantic & other libraries that ship JSON/templates.
datas += collect_data_files('reportlab')


a = Analysis(
    ['runserver.py'],
    pathex=[str(BACKEND_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='enterprisecore-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

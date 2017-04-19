import os

BASE_DIR = os.path.expanduser('~')

UPLOAD_DIR = os.path.join(BASE_DIR, '.hydra')
POLYVIS_URL = 'http://localhost:5000' 
DATA_FOLDER = os.path.join(BASE_DIR, '.hydra/data')


UPLOAD_DIR = os.path.join(DATA_FOLDER, 'uploads')
TEMPLATE_FOLDER = 'hydra_templates'

ALLOWED_EXTENSIONS = set(['zip'])

"""AI Film Production Bible — pré-produção visual do criador-video.

Camada DERIVADA da bíblia de produção existente (`<projeto>/producao.json`, scripts/producao.py): não substitui nada.
Lê elenco, cenários, objetos e tomadas, atribui IDs estáveis (char_*, env_*, prop_*), monta as pranchas de referência,
o storyboard sincronizado com a narração, o plano de câmera, o registro de continuidade e as pranchas HTML/PNG/PDF em
`<projeto>/production_bible/`. O supervisor de continuidade (scripts/supervisor_continuidade.py) usa esta bíblia.
"""
import os

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.dirname(SCRIPTS)
PASTA = "production_bible"

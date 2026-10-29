from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.main import app
from backend.app.agent import graph
(ROOT/'docs/openapi.json').write_text(json.dumps(app.openapi(),ensure_ascii=False,indent=2))
(ROOT/'docs/agent-graph.mmd').write_text(graph.get_graph().draw_mermaid())
print('Exported OpenAPI and LangGraph')

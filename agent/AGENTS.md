# CLAUDE.md — agent Python

> Chargé seulement quand on travaille sous `agent/`. Les règles communes au projet sont dans `../CLAUDE.md`.

## Pièges

- **Ordre d'import dans `main.py`** : `install()` du patch multimodal doit précéder l'import des graphes. Le patch remplace l'attribut de module `ag_ui_langgraph.utils.convert_agui_multimodal_to_langchain` : après une montée de version d'`ag-ui-langgraph`, vérifier qu'un PDF attaché arrive encore au modèle (symptôme d'un patch devenu inopérant : l'agent ne « voit » aucun document).
- **`recursion_limit`** se règle dans `_AGENT_CONFIG` de `main.py` : un `.with_config()` sur le graphe est écrasé par la config qu'`ag_ui_langgraph` construit à chaque run.
- **Dashboard `/fixed`** : les bindings `{path}` de `src/a2ui/schemas/dashboard.json` (`/kpis/0..3/*`, `/trend`, `/share`, `/rows`, `/scope/*`…) doivent correspondre au data model écrit par `render_dashboard` (`src/fixed_agent.py`). Changer l'un sans l'autre donne des slots vides, sans erreur.
- **Modèle codé en dur** (`gpt-5.5`) à quatre endroits dans `src/` (agents principaux + sous-LLM de `pdf_tools.py` et `dynamic_agent.py`) : un changement de modèle se fait par `grep`, pas à un seul endroit.

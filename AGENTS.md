# CLAUDE.md — A2UI PDF Analyst

> Le contexte global (langue, OS, outils, sécurité, vérification) est dans `~/.claude/CLAUDE.md` —
> **ne pas le répéter ici**. Ce fichier ne contient que ce qui est propre à ce projet. Cible : < 100 lignes.

## Méta — Garder ce fichier vivant

- Une règle qui n'est plus vraie est pire que pas de règle : elle est suivie à tort. La supprimer dès qu'elle est périmée.
- Deux règles contradictoires font choisir au hasard. À la moindre tension entre deux lignes, en supprimer une.
- Une règle qui ne dit rien d'actionnable est du bruit. La couper.
- Toute règle ajoutée ici doit tracer à un fait observé. Tant que le fait n'est pas vérifié, la marquer `TODO: verify` — et la retirer si la vérification échoue.

## Statut

Fork **autonome** de `CopilotKit/examples/showcases/a2ui-pdf-analyst` : aucune resynchronisation amont prévue, renommer et restructurer librement.

## Commandes

- Toute commande pnpm qui résout des paquets passe par Socket Firewall : `sfw pnpm i`, `sfw pnpm add <pkg>`.
- Formatage Python (version alignée sur l'ancienne CI amont) : `cd agent && uv run --with ruff==0.15.13 ruff format .` — `--check` pour contrôler sans écrire.
- Lint Python (règles par défaut de ruff, aucune config) : `cd agent && uv run --with ruff==0.15.13 ruff check .`
- Formatage TS/TSX : aucun formateur configuré ici (l'amont utilisait `oxfmt`). TODO: verify — choisir avant de reformater en masse.

## Pièges

- **Catalogue A2UI en double.** Le schéma et les renderers vivent côté TS (`src/a2ui/catalog/definitions.ts`, `renderers.tsx`) ; le LLM ne voit que `agent/src/catalog.py` (`CATALOG_PROMPT`). Ajouter ou modifier un composant = toucher les trois, et `CATALOG_ID` doit rester identique des deux côtés. Côté Python, les noms de composants valides sont **dérivés** des lignes `- **Nom**` de `CATALOG_PROMPT` par `agent/src/a2ui_validation.py` : changer ce format casse la validation. Les props ne sont validées que par Zod côté client.
- **Zod doit rester en v3** (même majeure que `@copilotkit/a2ui-renderer`). En v4, le binder classe silencieusement toutes les props en STATIC et les objets `{path}` arrivent bruts dans les renderers.
- **`injectA2UITool: false` est voulu** (`src/app/api/copilotkit/route.ts`). Le réactiver laisse des `tool_calls` orphelins dans l'état de l'agent → `INCOMPLETE_STREAM` au 2ᵉ tour. Le middleware A2UI rend quand même les `a2ui_operations` renvoyées par `generate_a2ui`.
- **L'agent `default` est requis** par le client CopilotKit V2 (hooks sans `agentId`) ; il est aliasé sur `fixed_agent`. Ne pas le retirer.
- **Windows `MAX_PATH`** : Turbopack échoue en `Module not found` dès qu'un chemin résolu sous `node_modules/.pnpm` dépasse 260 caractères. Le chemin du clone actuel est déjà proche de la limite.
- **`turbopack.root` est épinglé** dans `next.config.ts` : sans lui, Turbopack remonte vers un lockfile ou un `pnpm-workspace.yaml` parent et ne résout plus les `node_modules` de l'app.
- **`enableInspector={false}` est voulu** (`src/components/Providers.tsx`). L'Inspector de dev se monte par défaut sur localhost et appelle `GET /api/copilotkit/threads?agentId=*` — endpoint multi-route inexistant en `single-route` → salve de 3×404 + annonces CDN + télémétrie à chaque montage/rechargement/reconnexion HMR. Le réactiver fait revenir la salve (audit : `SETUP/2026-10-27-orchestration-loop/`).
- **Cache Turbopack dev périmé = boots froids** (mesuré sur Windows). Si chaque `sfw pnpm dev` recompile à froid (~15-25 s/page au 1ᵉʳ hit), vider `.next/dev/cache/turbopack` : un cache périmé/enflé ne restaure rien, un cache frais redonne des boots ~2 s. Ne pas mélanger `next build` et `next dev` sur le même `.next`. Vérif : `node SETUP/2026-10-27-orchestration-loop/evidence/probe-orchestration.mjs` (verdict D ≤ 5000 ms).

- **Deux dossiers `src/`** : celui du front à la racine, celui de l'agent sous `agent/`. Sans `pyrightconfig.json` (`executionEnvironments: [{root: "agent"}]`), Pylance, ouvert à la racine, résout `from src import …` vers le `src/` du front et signale `"dynamic_agent" is unknown import symbol`. Ne pas supprimer ce fichier, et choisir `agent/.venv` comme interpréteur dans VS Code (Pylance ignore `venvPath`).
- **Rechargement à chaud de l'agent peu fiable sous Windows.** Après une modification sous `agent/`, uvicorn (`--reload`, StatReload) a déjà affiché `Reloading...` sans jamais redémarrer. Avant un e2e live qui suit une modification de l'agent, relancer `sfw pnpm dev`, puis attendre `Application startup complete.`
- **`public/samples/` : uniquement des PDF à licence ouverte, ≤ 30 000 caractères extraits.** Tout ajout se documente dans `public/samples/SOURCES.md` (licence, URL, attribution) ; les exemples cliquables de `/fixed` et `/dynamic` vivent dans `src/lib/samples.ts`.

## Conventions qui s'écartent de l'évidence

- **Politique de dépendances stricte, des deux côtés.**
  - pnpm (`pnpm-workspace.yaml`) : cooldown de 7 jours strict, `trustPolicy: no-downgrade`, `strictDepBuilds`.
  - uv (`agent/pyproject.toml`) : `exclude-newer = "7 days"`, `no-build = true` (wheels uniquement).
  - Une dépendance qui bute sur l'une de ces règles s'ajoute en exception **exacte et commentée** (`trustPolicyExclude: pkg@x.y.z`, `allowBuilds: pkg: true|false`, `exclude-newer-package`), jamais en assouplissant la règle.
- **ESLint reste en `^9` malgré sa fin de vie (2026-08-06), en connaissance de cause.** Ne pas le monter seul. ESLint 10 exige `eslint-config-next` ≥ 16.4.0, donc une montée de `next` au même niveau, et `eslint-plugin-react` (embarqué par `eslint-config-next`) n'accepte encore qu'ESLint `^9.7` (7.37.5). Déclencheur de la migration : `pnpm view eslint-plugin-react peerDependencies` inclut `^10`. Ce jour-là, monter `next`, `eslint-config-next` et `eslint` ensemble, puis vérifier si `semver@6.3.1` et `unrs-resolver` sont encore nécessaires dans `pnpm-workspace.yaml`.
- Commits au format Conventional Commits (`type(scope): ...`), comme l'historique.

## Interdits

- Ne pas réintroduire de `{ path }` sur une prop dont le schéma Zod ne l'accepte pas (règle 4 de `CATALOG_PROMPT`) : le renderer reçoit l'objet au lieu de la valeur.

## Vérification

Niveau par défaut : **standard**.

- Agent Python : `cd agent && uv run pytest` (modèles factices, aucun appel réseau), puis
  `uv run --with "pyright[nodejs]" pyright src tests` (0 erreur attendue).

- Front, logique pure (plafond du texte PDF) : `pnpm test:web` (`node --test`, sans dépendance), puis `pnpm lint` et `pnpm exec tsc --noEmit`.
- Renderers et catalogue : `/catalog` affiche les 21 composants sans appeler l'agent.
- Flux agent (`/fixed`, `/dynamic`) : démonstration réelle avec un PDF attaché. Il faut `MISTRAL_API_KEY` dans `agent/.env`, et chaque essai consomme des tokens.
  - Attendu sur `/dynamic` : **une seule** pastille « SURFACE » par tour, avec un graphique dans le canvas. Plusieurs pastilles signalent une boucle d'outil. Un simple titre suivi d'un résumé signale la surface de repli, c'est-à-dire un rendu rejeté deux fois.
  - Le temps d'un tour se lit côté serveur, dans la ligne `POST /api/copilotkit 200 in …` du terminal. Repères mesurés (2026-10-28, exemples de `public/samples/`) : 12 à 17 s sur `/fixed`, 11 à 36 s sur `/dynamic`, le premier tour après le démarrage étant le plus lent. Timeout par appel : 45 s (`agent/src/models.py`).

## Rétrospectives

Chantiers de fond : `UPDATES/<date>-<sujet>/` avec OPTIMISATION.md, SPEC.md, RETRO.md.

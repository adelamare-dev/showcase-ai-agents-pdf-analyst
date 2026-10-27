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

- **Catalogue A2UI en double.** Le schéma et les renderers vivent côté TS (`src/a2ui/catalog/definitions.ts`, `renderers.tsx`) ; le LLM ne voit que `agent/src/catalog.py` (`CATALOG_PROMPT`). Ajouter ou modifier un composant = toucher les trois, et `CATALOG_ID` doit rester identique des deux côtés. (La docstring de `catalog.py` cite `web/src/...`, chemin périmé.)
- **Zod doit rester en v3** (même majeure que `@copilotkit/a2ui-renderer`). En v4, le binder classe silencieusement toutes les props en STATIC et les objets `{path}` arrivent bruts dans les renderers.
- **`injectA2UITool: false` est voulu** (`src/app/api/copilotkit/route.ts`). Le réactiver laisse des `tool_calls` orphelins dans l'état de l'agent → `INCOMPLETE_STREAM` au 2ᵉ tour. Le middleware A2UI rend quand même les `a2ui_operations` renvoyées par `generate_a2ui`.
- **L'agent `default` est requis** par le client CopilotKit V2 (hooks sans `agentId`) ; il est aliasé sur `fixed_agent`. Ne pas le retirer.
- **Windows `MAX_PATH`** : Turbopack échoue en `Module not found` dès qu'un chemin résolu sous `node_modules/.pnpm` dépasse 260 caractères. Le chemin du clone actuel est déjà proche de la limite.
- **`turbopack.root` est épinglé** dans `next.config.ts` : sans lui, Turbopack remonte vers un lockfile ou un `pnpm-workspace.yaml` parent et ne résout plus les `node_modules` de l'app.

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

Niveau par défaut : **standard**. Il n'existe aucune suite de tests.

- Renderers et catalogue : `/catalog` affiche les 21 composants sans appeler l'agent.
- Flux agent (`/fixed`, `/dynamic`) : démonstration réelle avec un PDF attaché. Il faut `OPENAI_API_KEY` dans `agent/.env`, et chaque essai consomme des tokens.

## Rétrospectives

Chantiers de fond : `UPDATES/<date>-<sujet>/` avec OPTIMISATION.md, SPEC.md, RETRO.md.

"use client";

import { useEffect, useState } from "react";
import { SiteNav, PageHeader } from "@/components/Brand";
import {
  A2UIProvider,
  A2UIRenderer,
  useA2UIActions,
} from "@copilotkit/a2ui-renderer";
import { catalog, CATALOG_ID } from "@/a2ui/catalog";

/* Each example renders a complete tiny A2UI surface. The shape mirrors
 * how the agent emits surfaces over the wire so the showcase doubles as
 * a sanity check on the catalog. */
type Example = {
  group: "layout" | "content" | "data" | "interactive";
  name: string;
  blurb: string;
  surface: {
    components: unknown[];
    data?: Record<string, unknown>;
  };
};

const sampleSeries = [
  { label: "janv.", value: 24 },
  { label: "févr.", value: 32 },
  { label: "mars", value: 38 },
  { label: "avr.", value: 44 },
  { label: "mai", value: 41 },
  { label: "juin", value: 52 },
];

const sampleShare = [
  { label: "Amérique du Nord", value: 480 },
  { label: "EMEA", value: 320 },
  { label: "APAC", value: 200 },
  { label: "LATAM", value: 80 },
];

const sampleRows = [
  { name: "Acme", category: "ETI", value: "48\u00a0k€", delta: "+8\u00a0%" },
  {
    name: "Northwind",
    category: "Grand compte",
    value: "112\u00a0k€",
    delta: "+12\u00a0%",
  },
  { name: "Globex", category: "PME", value: "22\u00a0k€", delta: "-3\u00a0%" },
  { name: "Initech", category: "ETI", value: "61\u00a0k€", delta: "+5\u00a0%" },
];

const sampleRanked = [
  { label: "Atlas Industries Pte Ltd", value: 1280 },
  { label: "Northwind Logistics", value: 940 },
  { label: "Globex International", value: 720 },
  { label: "Initech Holdings", value: 510 },
  { label: "Stark Manufacturing", value: 380 },
];

const sampleScatter = [
  { x: 1, y: 22 },
  { x: 2, y: 28 },
  { x: 3, y: 31 },
  { x: 4, y: 35 },
  { x: 5, y: 41 },
  { x: 6, y: 39 },
  { x: 7, y: 47 },
  { x: 8, y: 52 },
  { x: 9, y: 56 },
  { x: 10, y: 61 },
  { x: 11, y: 64 },
  { x: 12, y: 70 },
];

const EXAMPLES: Example[] = [
  {
    group: "layout",
    name: "Stack",
    blurb:
      "Conteneur vertical. Empile ses enfants de haut en bas avec un espacement régulier. Le conteneur par défaut des surfaces et des sections.",
    surface: {
      components: [
        {
          id: "root",
          component: "Stack",
          gap: "sm",
          children: ["c1", "c2", "c3"],
        },
        { id: "c1", component: "Card", child: "c1-text", tone: "default" },
        {
          id: "c1-text",
          component: "Text",
          text: "Première carte.",
          weight: "medium",
        },
        { id: "c2", component: "Card", child: "c2-text", tone: "lilac" },
        {
          id: "c2-text",
          component: "Text",
          text: "Deuxième carte.",
          weight: "medium",
        },
        { id: "c3", component: "Card", child: "c3-text", tone: "default" },
        {
          id: "c3-text",
          component: "Text",
          text: "Troisième carte.",
          weight: "medium",
        },
      ],
    },
  },
  {
    group: "layout",
    name: "Row",
    blurb:
      "Disposition horizontale. Une Row = une ligne d’enfants. Empilez plusieurs Row pour une mise en page proche d’un tableau ; une seule Row suffit pour une barre d’outils, une bande de métadonnées ou une barre d’actions. Ici : deux Row dans une Stack, pour voir l’unité de disposition horizontale.",
    surface: {
      components: [
        { id: "root", component: "Stack", gap: "xs", children: ["r1", "r2"] },
        {
          id: "r1",
          component: "Row",
          gap: "sm",
          align: "center",
          children: ["r1-name", "r1-sep", "r1-owner", "r1-badge"],
        },
        {
          id: "r1-name",
          component: "Text",
          text: "Migration Atlas",
          weight: "medium",
        },
        { id: "r1-sep", component: "Text", text: "·", tone: "muted" },
        {
          id: "r1-owner",
          component: "Text",
          text: "Priya",
          tone: "muted",
          size: "sm",
        },
        {
          id: "r1-badge",
          component: "Badge",
          label: "En cours",
          tone: "warning",
        },
        {
          id: "r2",
          component: "Row",
          gap: "sm",
          align: "center",
          children: ["r2-name", "r2-sep", "r2-owner", "r2-badge"],
        },
        {
          id: "r2-name",
          component: "Text",
          text: "Lancement Phénix",
          weight: "medium",
        },
        { id: "r2-sep", component: "Text", text: "·", tone: "muted" },
        {
          id: "r2-owner",
          component: "Text",
          text: "Sam",
          tone: "muted",
          size: "sm",
        },
        { id: "r2-badge", component: "Badge", label: "Terminé", tone: "positive" },
      ],
    },
  },
  {
    group: "layout",
    name: "Grid",
    blurb: "Grille adaptative (de 1 à 6 colonnes).",
    surface: {
      components: [
        {
          id: "root",
          component: "Grid",
          columns: 3,
          gap: "sm",
          children: ["s1", "s2", "s3"],
        },
        {
          id: "s1",
          component: "StatCard",
          label: "Chiffre d’affaires",
          value: "1,2\u00a0M€",
          delta: "+18\u00a0%",
          deltaTone: "positive",
        },
        {
          id: "s2",
          component: "StatCard",
          label: "Clients",
          value: "2\u00a0940",
          delta: "+7\u00a0%",
          deltaTone: "positive",
        },
        {
          id: "s3",
          component: "StatCard",
          label: "Attrition",
          value: "4,4\u00a0%",
          delta: "+0,4\u00a0%",
          deltaTone: "negative",
        },
      ],
    },
  },
  {
    group: "layout",
    name: "Card",
    blurb: "Surface encadrée avec marge intérieure. Des tons permettent d’appuyer un message.",
    surface: {
      components: [
        { id: "root", component: "Row", gap: "sm", children: ["c1", "c2"] },
        { id: "c1", component: "Card", child: "c1-text", tone: "default" },
        { id: "c1-text", component: "Text", text: "Ton par défaut." },
        { id: "c2", component: "Card", child: "c2-text", tone: "lilac" },
        {
          id: "c2-text",
          component: "Text",
          text: "Ton lilas.",
          weight: "medium",
        },
      ],
    },
  },
  {
    group: "layout",
    name: "Section",
    blurb:
      "Surtitre + titre + un seul composant enfant. Sert à nommer une zone de la surface.",
    surface: {
      components: [
        {
          id: "root",
          component: "Section",
          eyebrow: "VUE D’ENSEMBLE · T1",
          title: "Chiffre d’affaires trimestriel",
          child: "card",
        },
        { id: "card", component: "Card", child: "text" },
        {
          id: "text",
          component: "Text",
          text: "Le chiffre d’affaires total progresse de 18\u00a0% sur le trimestre, porté par les ETI.",
          tone: "muted",
        },
      ],
    },
  },
  {
    group: "layout",
    name: "Divider",
    blurb: "Filet de 1 px entre deux sections.",
    surface: {
      components: [
        {
          id: "root",
          component: "Stack",
          gap: "sm",
          children: ["t1", "d", "t2"],
        },
        { id: "t1", component: "Text", text: "Au-dessus du filet." },
        { id: "d", component: "Divider" },
        { id: "t2", component: "Text", text: "Sous le filet.", tone: "muted" },
      ],
    },
  },

  {
    group: "content",
    name: "Heading",
    blurb: "Niveaux 1, 2 et 3 : page, section, sous-bloc.",
    surface: {
      components: [
        {
          id: "root",
          component: "Stack",
          gap: "xs",
          children: ["h1", "h2", "h3"],
        },
        { id: "h1", component: "Heading", level: "1", text: "Titre 1" },
        { id: "h2", component: "Heading", level: "2", text: "Titre 2" },
        { id: "h3", component: "Heading", level: "3", text: "Titre 3" },
      ],
    },
  },
  {
    group: "content",
    name: "Text",
    blurb: "Texte courant. Ton, taille, graisse.",
    surface: {
      components: [
        {
          id: "root",
          component: "Stack",
          gap: "xs",
          children: ["t1", "t2", "t3"],
        },
        {
          id: "t1",
          component: "Text",
          text: "Texte courant par défaut.",
          weight: "medium",
        },
        {
          id: "t2",
          component: "Text",
          text: "Texte secondaire atténué.",
          tone: "muted",
        },
        {
          id: "t3",
          component: "Text",
          text: "Petite légende.",
          tone: "muted",
          size: "sm",
        },
      ],
    },
  },
  {
    group: "content",
    name: "Overline",
    blurb:
      "Petite étiquette monospace en capitales, placée au-dessus d’un titre (le motif typographique « overline » de Material Design). Sert aux étiquettes de catégorie.",
    surface: {
      components: [
        { id: "root", component: "Stack", gap: "xs", children: ["e", "h"] },
        { id: "e", component: "Overline", text: "DÉMO · 03" },
        { id: "h", component: "Heading", level: "2", text: "Titre de section" },
      ],
    },
  },
  {
    group: "content",
    name: "Badge",
    blurb: "Pastille d’état en ligne. 5 tons.",
    surface: {
      components: [
        {
          id: "root",
          component: "Row",
          gap: "xs",
          children: ["b1", "b2", "b3", "b4", "b5"],
        },
        { id: "b1", component: "Badge", label: "Neutre", tone: "neutral" },
        { id: "b2", component: "Badge", label: "Info", tone: "info" },
        { id: "b3", component: "Badge", label: "Positif", tone: "positive" },
        { id: "b4", component: "Badge", label: "Attention", tone: "warning" },
        { id: "b5", component: "Badge", label: "Danger", tone: "danger" },
      ],
    },
  },
  {
    group: "content",
    name: "Callout",
    blurb: "Encadré pour mettre en avant une idée clé ou une définition.",
    surface: {
      components: [
        { id: "root", component: "Stack", gap: "sm", children: ["c1", "c2"] },
        {
          id: "c1",
          component: "Callout",
          tone: "info",
          title: "Idée clé",
          body: "Les transformeurs ont remplacé la récurrence par l’attention : chaque jeton peut lire tous les autres en une seule étape.",
        },
        {
          id: "c2",
          component: "Callout",
          tone: "warning",
          title: "Réserve",
          body: "La couche d’attention croît de façon quadratique avec la longueur de la séquence : les contextes longs deviennent vite coûteux.",
        },
      ],
    },
  },
  {
    group: "content",
    name: "BulletList",
    blurb:
      "Énumérations courtes, à puces ou numérotées. `ordered: true` donne une liste numérotée.",
    surface: {
      components: [
        {
          id: "root",
          component: "Stack",
          gap: "md",
          children: ["h1", "ul", "h2", "ol"],
        },
        { id: "h1", component: "Overline", text: "À PUCES" },
        {
          id: "ul",
          component: "BulletList",
          items: [
            "Un nouveau mécanisme d’attention dont le coût croît presque linéairement.",
            "Une méthode d’entraînement qui divise le temps par deux.",
            "Un banc d’essai publié avec l’article.",
          ],
        },
        { id: "h2", component: "Overline", text: "NUMÉROTÉE" },
        {
          id: "ol",
          component: "BulletList",
          ordered: true,
          items: ["Lire le résumé.", "Parcourir le tableau 3.", "Lancer le notebook."],
        },
      ],
    },
  },

  {
    group: "data",
    name: "StatCard",
    blurb: "Carte d’un indicateur unique, avec variation et légende.",
    surface: {
      components: [
        {
          id: "root",
          component: "StatCard",
          label: "MRR",
          value: "48\u00a0200\u00a0€",
          delta: "+12,4\u00a0%",
          deltaTone: "positive",
          caption: "vs mois précédent",
        },
      ],
    },
  },
  {
    group: "data",
    name: "BarChart",
    blurb: "Barres verticales à partir de [{label,value}]. Pour des étiquettes courtes.",
    surface: {
      components: [
        { id: "root", component: "BarChart", height: 220, data: sampleSeries },
      ],
    },
  },
  {
    group: "data",
    name: "HorizontalBarChart",
    blurb: "Barres en lignes. Pour des classements aux étiquettes longues.",
    surface: {
      components: [
        {
          id: "root",
          component: "HorizontalBarChart",
          height: 240,
          data: sampleRanked,
        },
      ],
    },
  },
  {
    group: "data",
    name: "LineChart",
    blurb: "Courbe temporelle, quand c’est le sens de la tendance qui compte.",
    surface: {
      components: [
        { id: "root", component: "LineChart", height: 220, data: sampleSeries },
      ],
    },
  },
  {
    group: "data",
    name: "DonutChart",
    blurb: "Anneau de répartition. De 3 à 6 parts.",
    surface: {
      components: [
        { id: "root", component: "DonutChart", height: 220, data: sampleShare },
      ],
    },
  },
  {
    group: "data",
    name: "ScatterChart",
    blurb:
      "Nuage de points X/Y pour une corrélation. Renseignez toujours xLabel et yLabel pour nommer chaque axe.",
    surface: {
      components: [
        {
          id: "root",
          component: "ScatterChart",
          height: 240,
          xLabel: "Mois sur la plateforme",
          yLabel: "Heures actives par semaine",
          data: sampleScatter,
        },
      ],
    },
  },
  {
    group: "data",
    name: "DataTable",
    blurb: "Lignes × colonnes, valeurs numériques alignées à droite.",
    surface: {
      components: [
        {
          id: "root",
          component: "DataTable",
          columns: [
            { key: "name", label: "Client", align: "left" },
            { key: "category", label: "Segment", align: "left" },
            { key: "value", label: "Revenu annuel", align: "right" },
            { key: "delta", label: "Δ", align: "right" },
          ],
          rows: sampleRows,
        },
      ],
    },
  },

  {
    group: "interactive",
    name: "Button",
    blurb: "Principal / secondaire / discret.",
    surface: {
      components: [
        { id: "root", component: "Row", gap: "sm", children: ["p", "s", "g"] },
        {
          id: "p",
          component: "Button",
          label: "Principal",
          variant: "primary",
          action: { event: { name: "noop" } },
        },
        {
          id: "s",
          component: "Button",
          label: "Secondaire",
          variant: "secondary",
          action: { event: { name: "noop" } },
        },
        {
          id: "g",
          component: "Button",
          label: "Discret",
          variant: "ghost",
          action: { event: { name: "noop" } },
        },
      ],
    },
  },
  {
    group: "interactive",
    name: "ChoiceChips",
    blurb: "Pastilles à choix multiple liées à un chemin de données.",
    surface: {
      components: [
        {
          id: "root",
          component: "ChoiceChips",
          label: "Régions",
          options: [
            { label: "Amérique du Nord", value: "na" },
            { label: "EMEA", value: "emea" },
            { label: "APAC", value: "apac" },
            { label: "LATAM", value: "latam" },
          ],
          value: { path: "/regions" },
        },
      ],
      data: { regions: ["na", "emea"] },
    },
  },
];

const GROUPS: { key: Example["group"]; label: string }[] = [
  { key: "layout", label: "Mise en page" },
  { key: "content", label: "Contenu" },
  { key: "data", label: "Données" },
  { key: "interactive", label: "Interactif" },
];

export default function CatalogPage() {
  const [filter, setFilter] = useState<Example["group"] | "all">("all");
  const items =
    filter === "all" ? EXAMPLES : EXAMPLES.filter((e) => e.group === filter);

  return (
    <>
      <SiteNav active="catalog" />
      <PageHeader
        eyebrow="LE DESIGN SYSTEM"
        meta={
          <span className="pill">
            <span className="dot" /> {EXAMPLES.length} composants
          </span>
        }
        title={
          <>
            Chaque composant que l’agent <br className="hidden md:inline" />
            <span className="text-[var(--muted)]">a le droit de dessiner.</span>
          </>
        }
        subtitle="Un catalogue, un jeu de rendus React, un jeu de jetons de marque. Les deux démos en sont issues : le tableau de bord fixe via une mise en page écrite d’avance, les questions-réponses dynamiques en inventant une mise en page par question."
      />

      <main className="flex-1 max-w-[1320px] mx-auto px-6 py-8 w-full">
        <div className="flex items-center gap-2 mb-6">
          <FilterBtn
            label="Tous"
            active={filter === "all"}
            onClick={() => setFilter("all")}
          />
          {GROUPS.map((g) => (
            <FilterBtn
              key={g.key}
              label={g.label}
              active={filter === g.key}
              onClick={() => setFilter(g.key)}
            />
          ))}
          <span className="ml-auto mono text-[11px] text-[var(--muted-2)] uppercase tracking-wider">
            {items.length} / {EXAMPLES.length} affichés
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {items.map((ex) => (
            <ShowcaseTile key={ex.name} example={ex} />
          ))}
        </div>
      </main>

      <footer className="border-t border-[var(--line)] py-6 mt-10">
        <div className="max-w-[1320px] mx-auto px-6 text-xs text-[var(--muted)] flex items-center justify-between">
          <span>
            Définitions :{" "}
            <code className="mono px-1.5 py-0.5 rounded bg-[var(--surface-soft)] border border-[var(--line)] text-[11px]">
              src/a2ui/catalog/definitions.ts
            </code>{" "}
            · Rendus :{" "}
            <code className="mono px-1.5 py-0.5 rounded bg-[var(--surface-soft)] border border-[var(--line)] text-[11px]">
              src/a2ui/catalog/renderers.tsx
            </code>
          </span>
          <span className="mono">v0.2</span>
        </div>
      </footer>
    </>
  );
}

function FilterBtn({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-sm mono transition ${
        active
          ? "bg-[var(--ink)] text-white border border-[var(--ink)]"
          : "bg-[var(--surface)] text-[var(--ink-2)] border border-[var(--line)] hover:border-[var(--ink-2)]"
      }`}
    >
      {label}
    </button>
  );
}

function ShowcaseTile({ example }: { example: Example }) {
  return (
    <div className="surface overflow-hidden flex flex-col">
      <header className="px-5 py-3 border-b border-[var(--line)] flex items-center justify-between">
        <div>
          <div className="font-semibold text-[15px] text-[var(--ink)]">
            {example.name}
          </div>
          <div className="text-[12.5px] text-[var(--muted)]">
            {example.blurb}
          </div>
        </div>
        <span className="mono text-[10.5px] uppercase tracking-wider text-[var(--muted-2)] px-2 py-0.5 rounded-full border border-[var(--line)]">
          {GROUPS.find((g) => g.key === example.group)?.label ?? example.group}
        </span>
      </header>
      <div className="p-5 bg-[var(--surface-soft)] flex-1">
        <SurfacePreview surface={example.surface} />
      </div>
    </div>
  );
}

function SurfacePreview({
  surface,
}: {
  surface: { components: unknown[]; data?: Record<string, unknown> };
}) {
  return (
    <div className="a2ui-surface rounded-[var(--radius)]">
      <A2UIProvider catalog={catalog}>
        <PreviewInner surface={surface} />
      </A2UIProvider>
    </div>
  );
}

function PreviewInner({
  surface,
}: {
  surface: { components: unknown[]; data?: Record<string, unknown> };
}) {
  const actions = useA2UIActions();
  useEffect(() => {
    const messages: Array<Record<string, unknown>> = [
      {
        createSurface: { surfaceId: "preview", catalogId: CATALOG_ID },
      },
      {
        updateComponents: {
          surfaceId: "preview",
          components: surface.components,
        },
      },
    ];
    if (surface.data) {
      messages.push({
        updateDataModel: { surfaceId: "preview", value: surface.data },
      });
    }
    actions.processMessages(messages);
  }, [actions, surface]);
  return <A2UIRenderer surfaceId="preview" />;
}

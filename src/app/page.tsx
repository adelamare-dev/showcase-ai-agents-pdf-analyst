import Link from "next/link";
import { SiteNav, PageHeader } from "@/components/Brand";

export default function Home() {
  return (
    <>
      <SiteNav active="home" />
      <PageHeader
        eyebrow="CopilotKit × A2UI v0.9"
        meta={
          <span className="pill">
            <span className="dot" /> version de référence
          </span>
        }
        title={
          <>
            Des agents qui composent l’interface à partir de <br className="hidden md:inline" />
            <span
              className="bg-clip-text text-transparent"
              style={{ backgroundImage: "var(--brand-gradient)" }}
            >
              votre propre design system.
            </span>
          </>
        }
        subtitle="Déposez un PDF. Un agent remplit un tableau de bord fixe à partir d’une mise en page écrite à la main, un autre invente l’interface pour chaque question de suivi. Tous deux utilisent le même catalogue de 21 composants."
      />

      <main className="flex-1 max-w-[1320px] mx-auto px-6 py-12 w-full">
        <div className="grid md:grid-cols-2 gap-5">
          <ModeCard
            href="/fixed"
            badge="01 · SCHÉMA FIXE"
            title="Même mise en page, vos données"
            blurb="Vous écrivez le tableau de bord une fois. L’agent ne fait que renseigner les chiffres. Rapide, prévisible, fidèle à votre marque."
            bullets={[
              "Un fichier JSON décrit la mise en page du tableau de bord",
              "L’agent extrait du PDF les indicateurs, la tendance, la répartition et les lignes du tableau",
              "La surface s’affiche aussitôt, sans second appel au modèle pour le rendu",
            ]}
            cta="Ouvrir la démo à schéma fixe"
          />
          <ModeCard
            href="/dynamic"
            badge="02 · SCHÉMA DYNAMIQUE"
            title="L’agent choisit la forme"
            blurb="Aucune mise en page écrite d’avance. L’agent répond à votre question, puis un second passage du modèle invente l’interface à partir du catalogue."
            bullets={[
              "Tous les composants du catalogue (21), dans toutes les combinaisons",
              "StatCard pour un chiffre · LineChart pour une tendance · DataTable pour une liste",
              "Mêmes jetons de marque. L’agent ne voit jamais le CSS",
            ]}
            cta="Ouvrir la démo à schéma dynamique"
          />
        </div>

        <section className="mt-14">
          <div className="flex items-end justify-between mb-4">
            <div>
              <span className="mono text-[11px] uppercase tracking-[0.14em] text-[var(--muted-2)]">
                Le design system
              </span>
              <h2 className="text-[22px] font-semibold tracking-tight mt-1">
                21 composants, un seul catalogue
              </h2>
            </div>
            <Link
              href="/catalog"
              className="mono text-[12px] text-[var(--ink)] hover:text-[var(--lilac)] transition"
            >
              Tous les voir →
            </Link>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {CATALOG_GROUPS.flatMap((g) =>
              g.items.map((name) => (
                <div
                  key={name}
                  className="surface px-3 py-3 text-[13px] flex items-center justify-between"
                >
                  <span className="mono uppercase tracking-wider text-[11px] text-[var(--muted-2)]">
                    {g.short}
                  </span>
                  <span className="font-medium text-[var(--ink)]">{name}</span>
                </div>
              )),
            )}
          </div>
        </section>

        <section className="mt-14 grid md:grid-cols-3 gap-3">
          <Spec
            k="Interface"
            v="Next.js 16 · React 19 · Tailwind v4 · @copilotkit/react-core/v2"
          />
          <Spec
            k="Passerelle"
            v="@copilotkit/runtime (v2) · @ag-ui/client · a2ui middleware"
          />
          <Spec
            k="Serveur"
            v="Python · LangChain · LangGraph · FastAPI · ag-ui-langgraph"
          />
        </section>
      </main>

      <footer className="border-t border-[var(--line)] py-6 mt-10">
        <div className="max-w-[1320px] mx-auto px-6 text-xs text-[var(--muted)] flex items-center justify-between">
          <span>
            Déposez vos jetons de design dans{" "}
            <code className="mono px-1.5 py-0.5 rounded bg-[var(--surface-soft)] border border-[var(--line)] text-[11px]">
              src/a2ui/theme.css
            </code>{" "}
            pour réhabiller toutes les surfaces.
          </span>
          <span className="mono">v0.2</span>
        </div>
      </footer>
    </>
  );
}

const CATALOG_GROUPS = [
  {
    short: "LAY",
    items: ["Stack", "Row", "Grid", "Card", "Section", "Divider"],
  },
  {
    short: "TXT",
    items: ["Heading", "Text", "Overline", "Badge", "Callout", "BulletList"],
  },
  {
    short: "DATA",
    items: [
      "StatCard",
      "BarChart",
      "HorizontalBarChart",
      "LineChart",
      "DonutChart",
      "ScatterChart",
      "DataTable",
    ],
  },
  { short: "ACT", items: ["Button", "ChoiceChips"] },
];

function ModeCard({
  href,
  badge,
  title,
  blurb,
  bullets,
  cta,
}: {
  href: string;
  badge: string;
  title: string;
  blurb: string;
  bullets: string[];
  cta: string;
}) {
  return (
    <Link
      href={href}
      className="group surface p-7 hover:border-[var(--lilac)] transition relative overflow-hidden"
    >
      <div className="absolute -top-20 -right-20 w-[260px] h-[260px] rounded-full brand-gradient-soft opacity-0 group-hover:opacity-100 transition-opacity" />
      <div className="relative">
        <span className="mono text-[11px] uppercase tracking-[0.14em] text-[var(--muted-2)]">
          {badge}
        </span>
        <h3 className="text-[24px] font-semibold tracking-tight mt-2">
          {title}
        </h3>
        <p className="mt-3 text-[var(--muted)] leading-relaxed text-[15px]">
          {blurb}
        </p>
        <ul className="mt-5 space-y-2">
          {bullets.map((b) => (
            <li
              key={b}
              className="flex items-start gap-2.5 text-[13.5px] text-[var(--ink-2)]"
            >
              <span className="mt-2 w-1.5 h-1.5 rounded-full bg-[var(--lilac)] flex-none" />
              <span>{b}</span>
            </li>
          ))}
        </ul>
        <span className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-[var(--ink)] group-hover:text-[var(--ink)] transition mono">
          {cta} <span aria-hidden>→</span>
        </span>
      </div>
    </Link>
  );
}

function Spec({ k, v }: { k: string; v: string }) {
  return (
    <div className="surface-soft p-4">
      <div className="mono text-[11px] uppercase tracking-[0.14em] text-[var(--muted-2)]">
        {k}
      </div>
      <div className="mt-1 text-[13px] text-[var(--ink-2)]">{v}</div>
    </div>
  );
}

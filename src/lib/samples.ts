export type Sample = {
  id: string;
  label: string;
  /** File name under `public/samples/`. */
  file: string;
  suggestions: string[];
};

const INSEE_FILE = "insee-comptes-nationaux-t2-2026.pdf";
const INSEE_LABEL = "Comptes nationaux T2 2026 (Insee)";

/** Open-licensed PDFs only, each at most 30 000 extracted characters.
 *  Provenance and licences: `public/samples/SOURCES.md`. */
export const SAMPLES: { fixed: Sample[]; dynamic: Sample[] } = {
  fixed: [
    {
      id: "insee-fixed",
      label: INSEE_LABEL,
      file: INSEE_FILE,
      suggestions: [
        "Génère le tableau de bord de ce document.",
        "Génère le tableau de bord centré sur les ménages : pouvoir d'achat, consommation et épargne.",
        "Génère le tableau de bord centré sur l'investissement (FBCF).",
      ],
    },
  ],
  dynamic: [
    {
      id: "insee-dynamic",
      label: INSEE_LABEL,
      file: INSEE_FILE,
      suggestions: [
        "Montre l'évolution trimestrielle du PIB.",
        "Compare les contributions à la croissance du PIB au deuxième trimestre 2026.",
        "Quels indicateurs clés résument ce document ?",
      ],
    },
    {
      id: "arxiv-spear",
      label: "SPEAR, article de recherche (arXiv, CC BY 4.0)",
      file: "arxiv-2610.07204-spear.pdf",
      suggestions: [
        "Résume ce document en cinq points.",
        "Présente les cinq principes SPEAR et le rôle de chacun.",
        "En quoi l'alignement interactif diffère-t-il de l'alignement avant déploiement ?",
      ],
    },
  ],
};

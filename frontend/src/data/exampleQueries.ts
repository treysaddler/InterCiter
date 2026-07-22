/**
 * Curated example explorations, shown on the home hero and the empty search screen,
 * that show off InterCiter's distinctive features. Each one either runs a faceted
 * full-text claim search or deep-links into a feature screen, so a first-time visitor
 * can see provenance-anchored claims, the separate function/stance dimensions, the
 * citation network, and seed-based discovery without knowing anything up front.
 */

export interface ExampleQuery {
  /** Short chip label. */
  label: string
  /** One-line description of what it demonstrates. */
  hint: string
  /**
   * Destination. A relative `/search?...` or feature route. Kept as a plain string so
   * both the hero and the search screen can render it as a `<Link>`.
   */
  to: string
  /** What capability this example highlights (for the caption/badge). */
  feature: string
}

export const EXAMPLE_QUERIES: ExampleQuery[] = [
  {
    label: 'metformin',
    hint: 'Find every claim that mentions metformin — anchored to its source sentence.',
    to: '/search?q=metformin',
    feature: 'Full-text claim search',
  },
  {
    label: 'Supporting evidence',
    hint: 'Claims cited as supporting — stance is a first-class, separate dimension.',
    to: '/search?q=glucose&stance=support',
    feature: 'Stance facet',
  },
  {
    label: 'Direct evidence in Results',
    hint: 'Direct-evidence citations drawn from the Results section.',
    to: '/search?q=glucose&function=direct_evidence&section=Results',
    feature: 'Function + section facets',
  },
  {
    label: 'fasting glucose',
    hint: 'Search inside citation statements, not just titles and abstracts.',
    to: '/search?q=fasting%20glucose',
    feature: 'Passage-level search',
  },
  {
    label: 'Explore the citation network',
    hint: 'Walk citations between papers, authors, and claims as a graph.',
    to: '/graph',
    feature: 'Network exploration',
  },
  {
    label: 'Browse the corpus',
    hint: 'See every ingested paper and how it has been cited.',
    to: '/papers',
    feature: 'Corpus + citation reports',
  },
]

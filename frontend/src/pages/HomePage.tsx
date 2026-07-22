import { Link } from 'react-router-dom'

import PageHeading from '../components/PageHeading'
import SearchBox from '../components/SearchBox'
import { EXAMPLE_QUERIES } from '../data/exampleQueries'

/**
 * Home — a search-first landing page (docs/ui-design.md §5). Search is the primary
 * surface: a big box up top, then curated example explorations that show off the
 * distinctive features (provenance-anchored claim search, separate function/stance
 * facets, the citation network, and citation reports) so a first-time visitor can
 * start exploring without knowing the corpus.
 */
export default function HomePage() {
  return (
    <>
      <div className="margin-top-4">
        <PageHeading>Search the evidence, not just the titles</PageHeading>
        <p className="usa-intro measure-4">
          InterCiter anchors every scientific claim to its exact source sentence.
          Search inside citation statements, see how each claim is supported or
          contrasted, and trace it back to the paper it came from.
        </p>
      </div>

      <div className="margin-top-2 measure-5">
        <SearchBox big autoFocus />
      </div>

      <section className="margin-top-5" aria-label="Example explorations">
        <h2 className="font-heading-md">Try an example</h2>
        <p className="text-base measure-4">
          Each of these shows off a different part of InterCiter.
        </p>

        <ul className="usa-card-group">
          {EXAMPLE_QUERIES.map((ex) => (
            <li key={ex.to} className="usa-card tablet:grid-col-6 desktop:grid-col-4">
              <div className="usa-card__container">
                <div className="usa-card__header">
                  <span className="usa-tag bg-primary-lighter text-ink text-no-uppercase">
                    {ex.feature}
                  </span>
                </div>
                <div className="usa-card__body">
                  <h3 className="usa-card__heading">
                    <Link to={ex.to} className="text-no-underline">
                      {ex.label}
                    </Link>
                  </h3>
                  <p className="font-body-2xs text-base">{ex.hint}</p>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="margin-top-4">
        <p className="text-base">
          Or <Link to="/papers">browse every ingested paper</Link>,{' '}
          <Link to="/graph">explore the citation network</Link>, or{' '}
          <Link to="/ingest">submit a paper</Link> to extract its claims.
        </p>
      </section>
    </>
  )
}

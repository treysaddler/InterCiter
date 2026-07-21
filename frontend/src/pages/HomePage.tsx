import { Link } from 'react-router-dom'
import { Button, Grid, Alert } from '@trussworks/react-uswds'

import PageHeading from '../components/PageHeading'

/**
 * Home / dashboard (docs/ui-design.md §5). MVP will show recent papers, a submit
 * CTA, and job activity. Stub for now.
 */
export default function HomePage() {
  return (
    <>
      <PageHeading>InterCiter</PageHeading>
      <p className="usa-intro">
        Provenance-first exploration and review of scientific claims — every claim
        anchored to its exact source passage.
      </p>

      <Alert type="info" heading="Skeleton" headingLevel="h2" slim>
        This is a scaffold. Screens are wired to the information architecture but not
        yet to live data.
      </Alert>

      <Grid row gap className="margin-top-3">
        <Grid tablet={{ col: true }}>
          <Link to="/papers">
            <Button type="button">Browse papers</Button>
          </Link>
        </Grid>
        <Grid tablet={{ col: true }}>
          <Link to="/ingest">
            <Button type="button" outline>
              Submit a paper
            </Button>
          </Link>
        </Grid>
      </Grid>
    </>
  )
}

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

/**
 * The front-and-center search box (USWDS "big" search). Submitting navigates to the
 * search screen, preserving any facet filters passed in via `extraParams` so the same
 * box works from the home hero and from within `/search`.
 */
export default function SearchBox({
  initialQuery = '',
  big = false,
  extraParams,
  autoFocus = false,
}: {
  initialQuery?: string
  big?: boolean
  extraParams?: URLSearchParams
  autoFocus?: boolean
}) {
  const [value, setValue] = useState(initialQuery)
  const navigate = useNavigate()

  function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    const params = new URLSearchParams(extraParams ?? undefined)
    const q = value.trim()
    if (q) params.set('q', q)
    else params.delete('q')
    navigate(`/search?${params.toString()}`)
  }

  return (
    <form
      className={`usa-search${big ? ' usa-search--big' : ''}`}
      role="search"
      onSubmit={onSubmit}
    >
      <label className="usa-sr-only" htmlFor="claim-search-field">
        Search claims
      </label>
      <input
        className="usa-input"
        id="claim-search-field"
        type="search"
        name="q"
        placeholder="Search claims across the corpus…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        // eslint-disable-next-line jsx-a11y/no-autofocus
        autoFocus={autoFocus}
      />
      <button className="usa-button" type="submit">
        <span className="usa-search__submit-text">Search</span>
      </button>
    </form>
  )
}

# TODO - Jellyfin Collection Development Plan

## Phase 1: Core Infrastructure (Current)

- [x] Project structure and packaging (pyproject.toml)
- [x] Docker configuration (Dockerfile, docker-compose.yml)
- [x] Environment configuration (.env.example)
- [x] Core modules (config, logger, scheduler)
- [x] Pydantic models (collection, media)
- [x] Base HTTP client
- [x] CLI skeleton with Typer

## Phase 2: API Clients

- [x] Jellyfin client
  - [x] Library listing
  - [x] Item search by TMDb ID
  - [x] Collection CRUD operations
  - [x] Collection item management
- [x] TMDb client
  - [x] Trending (daily/weekly)
  - [x] Popular
  - [x] Discover with filters
  - [x] Search
  - [x] Details endpoint
- [x] Trakt client
  - [x] Trending/Popular
  - [x] Watched charts
  - [x] List support
- [x] Radarr client
  - [x] Movie lookup
  - [x] Add movie with tags
  - [x] Quality profile support
- [x] Sonarr client
  - [x] Series lookup (by TVDB ID)
  - [x] Add series with tags
  - [x] Monitor options
- [x] Discord webhook client
  - [x] Run start/end notifications
  - [x] Error notifications
  - [x] Collection changes

## Phase 3: Kometa Parser

- [x] Parse config.yml
- [x] Parse collection YAML files
- [x] Template support
- [x] Filter parsing
- [x] tmdb_discover parameter normalization
- [x] Schedule parsing (daily, weekly, monthly)
- [ ] Overlay configuration (future - not needed for collections)

## Phase 4: Collection Building

- [x] MediaMatcher service
  - [x] TMDb ID matching
  - [x] Title + year fallback
  - [x] Result caching
- [x] CollectionBuilder service
  - [x] Fetch items from providers
  - [x] Apply filters
  - [x] Match to library
  - [x] Sync to Jellyfin
  - [x] Add missing to Radarr/Sonarr
- [x] Runner service
  - [x] Orchestrate full run
  - [x] Schedule checking
  - [x] Discord notifications

## Phase 5: Testing & Refinement

- [ ] Unit tests
  - [ ] Parser tests
  - [ ] Model tests
  - [ ] Filter logic tests
- [ ] Integration tests
  - [ ] Mock API responses
  - [ ] End-to-end collection build
- [ ] Error handling improvements
  - [ ] Retry logic for API calls
  - [ ] Graceful degradation
  - [ ] Better error messages

## Phase 6: Advanced Features

- [ ] MDBList support
  - [ ] List parsing
  - [ ] API client
- [ ] IMDb list support
- [ ] Jellyfin search builder (equivalent to plex_search)
  - [ ] Genre filtering
  - [ ] Rating sorting
  - [ ] Added date sorting
- [ ] Collection images
  - [ ] Poster from first item
  - [ ] Custom poster support
- [ ] Overlay support (optional)
  - [ ] Resolution badges
  - [ ] Rating overlays

## Phase 7: Web Interface (Optional)

- [ ] FastAPI backend
  - [ ] Status endpoint
  - [ ] Manual trigger endpoint
  - [ ] Collection preview
- [ ] Simple web UI
  - [ ] Run status
  - [ ] Collection list
  - [ ] Logs viewer

## Phase 8: Production Readiness

- [ ] Comprehensive logging
- [ ] Prometheus metrics endpoint
- [ ] Health check endpoint
- [ ] Database for run history
- [ ] Rate limiting for API calls
- [ ] Documentation
  - [ ] README with examples
  - [ ] Migration guide from Kometa

---

## Known Limitations

1. **No overlay support** - Focus is on collections only
2. **No Plex support** - Jellyfin-only (use Kometa for Plex)
3. **TVDB ID required for Sonarr** - TMDb series ID must be converted
4. **Schedule runs locally** - No distributed scheduling

## Migration from Kometa

To migrate existing Kometa configs:

1. Copy `config.yml` and collection YAML files to `/config`
2. Update `libraries:` section with Jellyfin library names
3. Remove Plex-specific settings
4. Set environment variables for API keys
5. Run `jfc validate` to check configuration
6. Run `jfc run --dry-run` to preview changes

## Contributing

1. Follow existing code patterns
2. Add type hints to all functions
3. Use loguru for logging
4. Write tests for new features
5. Update TODO.md when completing items
# TODO - Futures améliorations

## JustWatch Integration (à traiter plus tard)

**Objectif** : Récupérer les charts de streaming depuis JustWatch

**API** :
- Endpoint : `https://apis.justwatch.com/graphql`
- Query : `GetPopularTitles`
- Paramètres : country, objectTypes (SHOW/MOVIE), packages, limit

**Ressources** :
- https://apis.justwatch.com/docs/api/
- https://github.com/YLTsai0609/DataEngineering101/blob/main/graphql.md
- https://pypi.org/project/simple-justwatch-python-api/

**Usage envisagé** :
```yaml
justwatch_popular:
  content_type: shows
  country: FR
  limit: 50
```

**Notes** :
- API non-officielle, peut changer
- Nécessite mapping IDs JustWatch → TMDb
- Données basées sur activité utilisateur réelle

---

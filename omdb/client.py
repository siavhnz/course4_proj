import logging

import requests

logger = logging.getLogger(__name__)

OMDB_API_URL = "https://www.omdbapi.com/"


class OmdbMovie:
    """A simple class to represent movie data coming back from OMDb
    and transform to Python types."""

    def __init__(self, data):
        """Data is the raw JSON/dict returned from OMDb"""
        self.data = data

    def check_for_detail_data_key(self, key):
        """Some keys are only in the detail response, raise an
        exception if the key is not found."""
        
        if key not in self.data:
            raise AttributeError(
                f"{key} is not in data, please make sure this is a detail response."
            )

    @property
    def imdb_id(self):
        return self.data["imdbID"]

    @property
    def title(self):
        return self.data["Title"]

    @property
    def year(self):
        return int(self.data["Year"])

    @property
    def runtime_minutes(self):
        self.check_for_detail_data_key("Runtime")

        rt, units = self.data["Runtime"].split(" ")

        if units != "min":
            raise ValueError(f"Expected units 'min' for runtime. Got '{units}")

        return int(rt)

    @property
    def genres(self):
        self.check_for_detail_data_key("Genre")

        return self.data["Genre"].split(", ")

    @property
    def plot(self):
        self.check_for_detail_data_key("Plot")
        return self.data["Plot"]

class OmdbClient:
    def __init__(self, api_key):
        self.api_key = api_key

    def make_request(self, params):
        """Make a GET request to the API, automatically adding the `apikey` to parameters."""
        params["apikey"] = self.api_key

        resp = requests.get(OMDB_API_URL, params=params)
        resp.raise_for_status()
        return resp

    def get_by_imdb_id(self, imdb_id):
        """Get a movie by its IMDB ID"""
        logger.info("Fetching detail for IMDB ID %s", imdb_id)
        resp = self.make_request({"i": imdb_id})
        return OmdbMovie(resp.json())

    def search(self, search):
        """Search for movies by title. This is a generator so all results from all pages will be iterated across."""
        page = 1
        seen_results = 0
        total_results = None

        logger.info("Performing a search for '%s'", search)

        while True:
            logger.info("Fetching page %d", page)
            resp = self.make_request({"s": search, "type": "movie", "page": str(page)})
            resp_body = resp.json()
            if total_results is None:
                total_results = int(resp_body["totalResults"])

            for movie in resp_body["Search"]:
                seen_results += 1
                yield OmdbMovie(movie)

            if seen_results >= total_results:
                break

            page += 1

def search_and_save(search):
    """
    Perform a search for search_term against the API, but only if it hasn't been searched in the past 24 hours. Save
    each result to the local DB as a partial record.
    """
    # Replace multiple spaces with single spaces, and lowercase the search
    normalized_search_term = re.sub(r"\s+", " ", search.lower())

    search_term, created = SearchTerm.objects.get_or_create(term=normalized_search_term)

    if not created and (search_term.last_search > now() - timedelta(days=1)):
        # Don't search as it has been searched recently
        logger.warning(
            "Search for '%s' was performed in the past 24 hours so not searching again.",
            normalized_search_term,
        )
        return

    omdb_client = get_client_from_settings()

    for omdb_movie in omdb_client.search(search):
        logger.info("Saving movie: '%s' / '%s'", omdb_movie.title, omdb_movie.imdb_id)
        movie, created = Movie.objects.get_or_create(
            imdb_id=omdb_movie.imdb_id,
            defaults={
                "title": omdb_movie.title,
                "year": omdb_movie.year,
            },
        )

        if created:
            logger.info("Movie created: '%s'", movie.title)

    search_term.save()
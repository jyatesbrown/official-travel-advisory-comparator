import pytest

from src.destinations.resolver import get_resolver
from src.utils.text import normalize_key

resolver = get_resolver()


@pytest.mark.parametrize(
    ("query", "name", "iso2", "iso3", "method"),
    [
        ("Trinidad and Tobago", "Trinidad and Tobago", "TT", "TTO", "name"),
        ("trinidad & tobago", "Trinidad and Tobago", "TT", "TTO", "name"),
        ("  TRINIDAD AND TOBAGO ", "Trinidad and Tobago", "TT", "TTO", "name"),
        ("Turkey", "Türkiye", "TR", "TUR", "alias"),
        ("Türkiye", "Türkiye", "TR", "TUR", "name"),
        ("Turkiye", "Türkiye", "TR", "TUR", "name"),
        ("Ivory Coast", "Côte d'Ivoire", "CI", "CIV", "alias"),
        ("Côte d'Ivoire", "Côte d'Ivoire", "CI", "CIV", "name"),
        ("Côte d’Ivoire", "Côte d'Ivoire", "CI", "CIV", "name"),
        ("Hong Kong", "Hong Kong", "HK", "HKG", "name"),
        ("South Korea", "South Korea", "KR", "KOR", "name"),
        ("Korea, Republic of", "South Korea", "KR", "KOR", "name"),
        ("Republic of Korea", "South Korea", "KR", "KOR", "name"),
        ("Iran", "Iran", "IR", "IRN", "name"),
        ("Russia", "Russia", "RU", "RUS", "alias"),
        ("The Gambia", "Gambia", "GM", "GMB", "name"),
        ("St Lucia", "Saint Lucia", "LC", "LCA", "name"),
        ("Kosovo", "Kosovo", "XK", "XKX", "alias"),
        ("TT", "Trinidad and Tobago", "TT", "TTO", "iso_code"),
        ("mex", "Mexico", "MX", "MEX", "iso_code"),
        ("UK", "United Kingdom", "GB", "GBR", "alias"),
        ("Colmbia", "Colombia", "CO", "COL", "fuzzy"),
    ],
)
def test_resolves(query: str, name: str, iso2: str, iso3: str, method: str) -> None:
    resolution = resolver.resolve(query)
    assert resolution.destination is not None
    assert (resolution.destination.name, resolution.destination.iso2, resolution.destination.iso3) == (
        name,
        iso2,
        iso3,
    )
    assert resolution.method == method


@pytest.mark.parametrize("query", ["Narnia", "not-a-real-country-xyz", "", "   ", "Nigerr", "Atlantis Republic"])
def test_unknown_is_not_guessed(query: str) -> None:
    resolution = resolver.resolve(query)
    assert resolution.destination is None
    assert resolution.method is None


@pytest.mark.parametrize(
    ("query", "candidates"),
    [
        ("Congo", ("Democratic Republic of the Congo", "Republic of the Congo")),
        ("Korea", ("North Korea", "South Korea")),
        ("Virgin Islands", ("British Virgin Islands", "U.S. Virgin Islands")),
    ],
)
def test_ambiguous_returns_candidates(query: str, candidates: tuple[str, ...]) -> None:
    resolution = resolver.resolve(query)
    assert resolution.destination is None
    assert resolution.reason == "ambiguous"
    assert resolution.candidates == candidates


def test_niger_is_not_nigeria() -> None:
    assert resolver.resolve("Niger").destination.iso2 == "NE"
    assert resolver.resolve("Nigeria").destination.iso2 == "NG"


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("Côte d’Ivoire", "cote divoire"),
        ("Trinidad & Tobago", "trinidad and tobago"),
        ("St. Kitts and Nevis", "saint kitts and nevis"),
        ("The Bahamas", "bahamas"),
    ],
)
def test_normalize_key(raw: str, key: str) -> None:
    assert normalize_key(raw) == key

"""Schutz vor der falschen Datenbank (läuft auch ohne PostgreSQL)."""

import pytest
from sqlalchemy.engine import URL

from pg_setup import require_test_database


def url(database):
    return URL.create("postgresql+psycopg2", username="u", host="h", database=database)


def test_test_database_is_accepted():
    require_test_database(url("wasserrakete_test"))


@pytest.mark.parametrize("name", ["wasserrakete", "test_wasserrakete", "wasserrakete_test_alt", "", None])
def test_other_databases_are_rejected(name):
    with pytest.raises(RuntimeError, match="endet nicht auf '_test'"):
        require_test_database(url(name))
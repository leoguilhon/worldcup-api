"""backfill team country codes

Revision ID: 0004_backfill_team_country_codes
Revises: 0003_add_team_is_placeholder
Create Date: 2026-06-04
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0004_backfill_team_country_codes"
down_revision: Union[str, None] = "0003_add_team_is_placeholder"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TEAM_COUNTRY_CODES = {
    "Algeria": "DZ",
    "Argentina": "AR",
    "Australia": "AU",
    "Austria": "AT",
    "Belgium": "BE",
    "Bosnia and Herzegovina": "BA",
    "Brazil": "BR",
    "Canada": "CA",
    "Cape Verde": "CV",
    "Colombia": "CO",
    "Croatia": "HR",
    "Curaçao": "CW",
    "Czech Republic": "CZ",
    "DR Congo": "CD",
    "Ecuador": "EC",
    "Egypt": "EG",
    "England": "ENG",
    "France": "FR",
    "Germany": "DE",
    "Ghana": "GH",
    "Haiti": "HT",
    "Iran": "IR",
    "Iraq": "IQ",
    "Ivory Coast": "CI",
    "Japan": "JP",
    "Jordan": "JO",
    "Mexico": "MX",
    "Morocco": "MA",
    "Netherlands": "NL",
    "New Zealand": "NZ",
    "Norway": "NO",
    "Panama": "PA",
    "Paraguay": "PY",
    "Portugal": "PT",
    "Qatar": "QA",
    "Saudi Arabia": "SA",
    "Scotland": "SCT",
    "Senegal": "SN",
    "South Africa": "ZA",
    "South Korea": "KR",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Tunisia": "TN",
    "Turkey": "TR",
    "United States": "US",
    "Uruguay": "UY",
    "Uzbekistan": "UZ",
}


def upgrade() -> None:
    for team_name, country_code in TEAM_COUNTRY_CODES.items():
        escaped_name = team_name.replace("'", "''")
        op.execute(
            "UPDATE teams "
            f"SET country_code = '{country_code}' "
            f"WHERE name = '{escaped_name}' "
            "AND is_placeholder = false"
        )


def downgrade() -> None:
    pass

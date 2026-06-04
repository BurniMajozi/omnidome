"""Seed coverage_areas with South African FNO coverage data.

Covers major metros with Vumatel, Openserve, and other FNO coverage.
In production, this would be populated from FNO API feeds or manual imports.
"""

import uuid
import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from services.customer_journey.models import CoverageArea, Base
from services.common.db import get_engine


# ── Coverage Data ────────────────────────────────────────────────────────

COVERAGE_DATA = [
    # Gauteng — Vumatel FTTH
    {"fno": "Vumatel", "tech": "FTTH", "area": "Sandton", "suburb": "Sandton Central", "city": "Johannesburg", "province": "Gauteng", "postal": "2196", "lat": Decimal("-26.1076"), "lng": Decimal("28.0567"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Rosebank", "suburb": "Rosebank", "city": "Johannesburg", "province": "Gauteng", "postal": "2196", "lat": Decimal("-26.1468"), "lng": Decimal("28.0422"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Melrose", "suburb": "Melrose", "city": "Johannesburg", "province": "Gauteng", "postal": "2196", "lat": Decimal("-26.1333"), "lng": Decimal("28.0667"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Fourways", "suburb": "Fourways", "city": "Johannesburg", "province": "Gauteng", "postal": "2055", "lat": Decimal("-26.0167"), "lng": Decimal("28.0167"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Bryanston", "suburb": "Bryanston", "city": "Johannesburg", "province": "Gauteng", "postal": "2191", "lat": Decimal("-26.0667"), "lng": Decimal("28.0333"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Randburg", "suburb": "Randburg", "city": "Johannesburg", "province": "Gauteng", "postal": "2194", "lat": Decimal("-26.0936"), "lng": Decimal("27.9833"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Bedfordview", "suburb": "Bedfordview", "city": "Johannesburg", "province": "Gauteng", "postal": "2008", "lat": Decimal("-26.1797"), "lng": Decimal("28.1364"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Midrand", "suburb": "Midrand", "city": "Johannesburg", "province": "Gauteng", "postal": "1685", "lat": Decimal("-25.9833"), "lng": Decimal("28.1333"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Centurion", "suburb": "Centurion", "city": "Pretoria", "province": "Gauteng", "postal": "0157", "lat": Decimal("-25.8667"), "lng": Decimal("28.1833"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Menlyn", "suburb": "Menlyn", "city": "Pretoria", "province": "Gauteng", "postal": "0181", "lat": Decimal("-25.7833"), "lng": Decimal("28.2667"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Hatfield", "suburb": "Hatfield", "city": "Pretoria", "province": "Gauteng", "postal": "0083", "lat": Decimal("-25.7500"), "lng": Decimal("28.2333"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Roodepoort", "suburb": "Roodepoort", "city": "Johannesburg", "province": "Gauteng", "postal": "1724", "lat": Decimal("-26.1667"), "lng": Decimal("27.8667"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Edenvale", "suburb": "Edenvale", "city": "Johannesburg", "province": "Gauteng", "postal": "1609", "lat": Decimal("-26.1333"), "lng": Decimal("28.1500"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Boksburg", "suburb": "Boksburg", "city": "Johannesburg", "province": "Gauteng", "postal": "1459", "lat": Decimal("-26.2167"), "lng": Decimal("28.2500"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Kempton Park", "suburb": "Kempton Park", "city": "Johannesburg", "province": "Gauteng", "postal": "1619", "lat": Decimal("-26.1000"), "lng": Decimal("28.2333"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Alberton", "suburb": "Alberton", "city": "Johannesburg", "province": "Gauteng", "postal": "1450", "lat": Decimal("-26.2667"), "lng": Decimal("28.1333"), "speed": 1000, "status": "available"},

    # Gauteng — Openserve FTTH
    {"fno": "Openserve", "tech": "FTTH", "area": "Soweto", "suburb": "Orlando", "city": "Johannesburg", "province": "Gauteng", "postal": "1804", "lat": Decimal("-26.2500"), "lng": Decimal("27.9167"), "speed": 500, "status": "available"},
    {"fno": "Openserve", "tech": "FTTH", "area": "Alexandra", "suburb": "Alexandra", "city": "Johannesburg", "province": "Gauteng", "postal": "2090", "lat": Decimal("-26.1000"), "lng": Decimal("28.1000"), "speed": 500, "status": "available"},
    {"fno": "Openserve", "tech": "FTTH", "area": "Braamfontein", "suburb": "Braamfontein", "city": "Johannesburg", "province": "Gauteng", "postal": "2001", "lat": Decimal("-26.1833"), "lng": Decimal("28.0333"), "speed": 500, "status": "available"},
    {"fno": "Openserve", "tech": "FTTH", "area": "Hillbrow", "suburb": "Hillbrow", "city": "Johannesburg", "province": "Gauteng", "postal": "2001", "lat": Decimal("-26.2000"), "lng": Decimal("28.0500"), "speed": 500, "status": "available"},
    {"fno": "Openserve", "tech": "FTTH", "area": "Pretoria Central", "suburb": "Central", "city": "Pretoria", "province": "Gauteng", "postal": "0002", "lat": Decimal("-25.7500"), "lng": Decimal("28.1833"), "speed": 500, "status": "available"},
    {"fno": "Openserve", "tech": "FTTH", "area": "Sunnyside", "suburb": "Sunnyside", "city": "Pretoria", "province": "Gauteng", "postal": "0002", "lat": Decimal("-25.7667"), "lng": Decimal("28.2000"), "speed": 500, "status": "available"},

    # Western Cape — Vumatel FTTH
    {"fno": "Vumatel", "tech": "FTTH", "area": "Cape Town CBD", "suburb": "City Bowl", "city": "Cape Town", "province": "Western Cape", "postal": "8001", "lat": Decimal("-33.9258"), "lng": Decimal("18.4232"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Gardens", "suburb": "Gardens", "city": "Cape Town", "province": "Western Cape", "postal": "8001", "lat": Decimal("-33.9333"), "lng": Decimal("18.4167"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Camps Bay", "suburb": "Camps Bay", "city": "Cape Town", "province": "Western Cape", "postal": "8005", "lat": Decimal("-33.9500"), "lng": Decimal("18.3833"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Claremont", "suburb": "Claremont", "city": "Cape Town", "province": "Western Cape", "postal": "7708", "lat": Decimal("-33.9833"), "lng": Decimal("18.4667"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Rondebosch", "suburb": "Rondebosch", "city": "Cape Town", "province": "Western Cape", "postal": "7700", "lat": Decimal("-33.9667"), "lng": Decimal("18.4833"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Bellville", "suburb": "Bellville", "city": "Cape Town", "province": "Western Cape", "postal": "7530", "lat": Decimal("-33.9000"), "lng": Decimal("18.6333"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Durbanville", "suburb": "Durbanville", "city": "Cape Town", "province": "Western Cape", "postal": "7550", "lat": Decimal("-33.8333"), "lng": Decimal("18.6500"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Somerset West", "suburb": "Somerset West", "city": "Cape Town", "province": "Western Cape", "postal": "7130", "lat": Decimal("-34.0833"), "lng": Decimal("18.8500"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Stellenbosch", "suburb": "Stellenbosch", "city": "Cape Town", "province": "Western Cape", "postal": "7600", "lat": Decimal("-33.9333"), "lng": Decimal("18.8667"), "speed": 1000, "status": "available"},

    # Western Cape — Openserve FTTH
    {"fno": "Openserve", "tech": "FTTH", "area": "Khayelitsha", "suburb": "Khayelitsha", "city": "Cape Town", "province": "Western Cape", "postal": "7784", "lat": Decimal("-34.0333"), "lng": Decimal("18.6833"), "speed": 500, "status": "available"},
    {"fno": "Openserve", "tech": "FTTH", "area": "Mitchells Plain", "suburb": "Mitchells Plain", "city": "Cape Town", "province": "Western Cape", "postal": "7785", "lat": Decimal("-34.0500"), "lng": Decimal("18.6167"), "speed": 500, "status": "available"},
    {"fno": "Openserve", "tech": "FTTH", "area": "Blue Downs", "suburb": "Blue Downs", "city": "Cape Town", "province": "Western Cape", "postal": "7100", "lat": Decimal("-33.9500"), "lng": Decimal("18.6833"), "speed": 500, "status": "available"},

    # KwaZulu-Natal — Vumatel FTTH
    {"fno": "Vumatel", "tech": "FTTH", "area": "Umhlanga", "suburb": "Umhlanga", "city": "Durban", "province": "KwaZulu-Natal", "postal": "4319", "lat": Decimal("-29.7167"), "lng": Decimal("31.0667"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Ballito", "suburb": "Ballito", "city": "Durban", "province": "KwaZulu-Natal", "postal": "4420", "lat": Decimal("-29.5333"), "lng": Decimal("31.2167"), "speed": 1000, "status": "available"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Pinetown", "suburb": "Pinetown", "city": "Durban", "province": "KwaZulu-Natal", "postal": "3610", "lat": Decimal("-29.8167"), "lng": Decimal("30.8500"), "speed": 1000, "status": "available"},

    # KwaZulu-Natal — Openserve FTTH
    {"fno": "Openserve", "tech": "FTTH", "area": "Durban CBD", "suburb": "Central", "city": "Durban", "province": "KwaZulu-Natal", "postal": "4001", "lat": Decimal("-29.8587"), "lng": Decimal("31.0218"), "speed": 500, "status": "available"},
    {"fno": "Openserve", "tech": "FTTH", "area": "Westville", "suburb": "Westville", "city": "Durban", "province": "KwaZulu-Natal", "postal": "3630", "lat": Decimal("-29.8333"), "lng": Decimal("30.9333"), "speed": 500, "status": "available"},

    # Eastern Cape — Openserve
    {"fno": "Openserve", "tech": "FTTH", "area": "Port Elizabeth CBD", "suburb": "Central", "city": "Gqeberha", "province": "Eastern Cape", "postal": "6001", "lat": Decimal("-33.9608"), "lng": Decimal("25.6022"), "speed": 500, "status": "available"},
    {"fno": "Openserve", "tech": "FTTH", "area": "East London CBD", "suburb": "Central", "city": "East London", "province": "Eastern Cape", "postal": "5201", "lat": Decimal("-33.0153"), "lng": Decimal("27.9116"), "speed": 500, "status": "available"},

    # Free State — Openserve
    {"fno": "Openserve", "tech": "FTTH", "area": "Bloemfontein CBD", "suburb": "Central", "city": "Bloemfontein", "province": "Free State", "postal": "9301", "lat": Decimal("-29.0852"), "lng": Decimal("26.1596"), "speed": 500, "status": "available"},

    # Coming soon areas
    {"fno": "Vumatel", "tech": "FTTH", "area": "Polokwane", "suburb": "Central", "city": "Polokwane", "province": "Limpopo", "postal": "0699", "lat": Decimal("-23.9000"), "lng": Decimal("29.4500"), "speed": 500, "status": "coming_soon"},
    {"fno": "Vumatel", "tech": "FTTH", "area": "Nelspruit", "suburb": "Central", "city": "Mbombela", "province": "Mpumalanga", "postal": "1200", "lat": Decimal("-25.4667"), "lng": Decimal("30.9667"), "speed": 500, "status": "coming_soon"},
    {"fno": "Openserve", "tech": "FTTH", "area": "Rustenburg", "suburb": "Central", "city": "Rustenburg", "province": "North West", "postal": "0300", "lat": Decimal("-25.6667"), "lng": Decimal("27.2333"), "speed": 500, "status": "coming_soon"},
]

# Standard packages available across all FNOs
STANDARD_PACKAGES = [
    {"name": "Home 50Mbps", "monthly_zar": 799, "once_off_zar": 0, "speed_mbps": 50},
    {"name": "Home 100Mbps", "monthly_zar": 999, "once_off_zar": 0, "speed_mbps": 100},
    {"name": "Home 200Mbps", "monthly_zar": 1299, "once_off_zar": 0, "speed_mbps": 200},
    {"name": "Home 500Mbps", "monthly_zar": 1799, "once_off_zar": 0, "speed_mbps": 500},
    {"name": "Home 1000Mbps", "monthly_zar": 2499, "once_off_zar": 0, "speed_mbps": 1000},
    {"name": "Uncapped 50Mbps", "monthly_zar": 1099, "once_off_zar": 0, "speed_mbps": 50},
    {"name": "Uncapped 100Mbps", "monthly_zar": 1499, "once_off_zar": 0, "speed_mbps": 100},
    {"name": "Uncapped 200Mbps", "monthly_zar": 1999, "once_off_zar": 0, "speed_mbps": 200},
]


def seed_coverage(tenant_id: str = "00000000-0000-0000-0000-000000000001"):
    """Seed coverage areas for a tenant."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        # Check if already seeded
        existing = session.query(CoverageArea).filter(
            CoverageArea.tenant_id == uuid.UUID(tenant_id)
        ).first()
        if existing:
            print("Coverage areas already seeded.")
            return

        tid = uuid.UUID(tenant_id)
        for area in COVERAGE_DATA:
            ca = CoverageArea(
                tenant_id=tid,
                fno_name=area["fno"],
                technology=area["tech"],
                area_name=area["area"],
                suburb=area["suburb"],
                city=area["city"],
                province=area["province"],
                postal_code=area["postal"],
                gps_lat=area["lat"],
                gps_lng=area["lng"],
                status=area["status"],
                max_speed_mbps=area["speed"],
                available_packages=STANDARD_PACKAGES,
                estimated_install_days=14 if area["status"] == "available" else 90,
            )
            session.add(ca)

        session.commit()
        print(f"Seeded {len(COVERAGE_DATA)} coverage areas.")


if __name__ == "__main__":
    seed_coverage()

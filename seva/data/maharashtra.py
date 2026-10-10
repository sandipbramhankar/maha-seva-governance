"""
Maharashtra administrative hierarchy
=====================================
Revenue Division -> District -> Taluka.

Used for Seva ID district codes and for the district/taluka drill-down on the
governance dashboard. District codes follow the three-letter convention used in
Maharashtra revenue correspondence.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class District:
    name: str
    code: str          # three-letter revenue code, used inside the Seva ID
    division: str
    talukas: List[str]


# Six revenue divisions of Maharashtra
DIVISIONS = [
    "Konkan",
    "Pune",
    "Nashik",
    "Chhatrapati Sambhajinagar",
    "Amravati",
    "Nagpur",
]


DISTRICTS: List[District] = [
    # ---------------- Konkan Division ----------------
    District("Mumbai City", "MUC", "Konkan", [
        "Colaba", "Fort", "Girgaon", "Byculla", "Parel", "Worli", "Mahim",
    ]),
    District("Mumbai Suburban", "MUS", "Konkan", [
        "Andheri", "Borivali", "Kurla", "Bandra", "Goregaon", "Mulund", "Dahisar",
    ]),
    District("Thane", "THN", "Konkan", [
        "Thane", "Kalyan", "Bhiwandi", "Murbad", "Shahapur", "Ulhasnagar", "Ambernath",
    ]),
    District("Palghar", "PLG", "Konkan", [
        "Palghar", "Vasai", "Dahanu", "Talasari", "Jawhar", "Mokhada", "Vikramgad", "Wada",
    ]),
    District("Raigad", "RGD", "Konkan", [
        "Alibag", "Panvel", "Pen", "Karjat", "Khalapur", "Mahad", "Mangaon",
        "Murud", "Roha", "Shrivardhan", "Sudhagad", "Tala", "Uran", "Mhasala", "Poladpur",
    ]),
    District("Ratnagiri", "RTN", "Konkan", [
        "Ratnagiri", "Chiplun", "Dapoli", "Guhagar", "Khed", "Lanja",
        "Mandangad", "Rajapur", "Sangameshwar",
    ]),
    District("Sindhudurg", "SDG", "Konkan", [
        "Kudal", "Sawantwadi", "Malvan", "Vengurla", "Kankavli",
        "Devgad", "Dodamarg", "Vaibhavwadi",
    ]),

    # ---------------- Pune Division ----------------
    District("Pune", "PUN", "Pune", [
        "Haveli", "Pune City", "Baramati", "Bhor", "Daund", "Indapur", "Junnar",
        "Khed", "Maval", "Mulshi", "Purandar", "Shirur", "Velhe", "Ambegaon",
    ]),
    District("Satara", "STR", "Pune", [
        "Satara", "Karad", "Koregaon", "Khatav", "Man", "Phaltan", "Wai",
        "Jaoli", "Mahabaleshwar", "Patan", "Khandala",
    ]),
    District("Sangli", "SNG", "Pune", [
        "Miraj", "Tasgaon", "Khanapur", "Atpadi", "Jat", "Kavathe Mahankal",
        "Palus", "Shirala", "Walwa", "Kadegaon",
    ]),
    District("Solapur", "SOL", "Pune", [
        "Solapur North", "Solapur South", "Akkalkot", "Barshi", "Karmala",
        "Madha", "Malshiras", "Mangalvedhe", "Mohol", "Pandharpur", "Sangole",
    ]),
    District("Kolhapur", "KOL", "Pune", [
        "Karvir", "Panhala", "Shahuwadi", "Kagal", "Hatkanangle", "Shirol",
        "Radhanagari", "Gaganbawada", "Bhudargad", "Ajara", "Chandgad", "Gadhinglaj",
    ]),

    # ---------------- Nashik Division ----------------
    District("Nashik", "NSK", "Nashik", [
        "Nashik", "Igatpuri", "Dindori", "Peth", "Trimbakeshwar", "Kalwan",
        "Surgana", "Baglan", "Malegaon", "Nandgaon", "Chandwad", "Niphad",
        "Sinnar", "Yeola", "Deola",
    ]),
    District("Dhule", "DHL", "Nashik", [
        "Dhule", "Sakri", "Shirpur", "Sindkheda",
    ]),
    District("Nandurbar", "NDB", "Nashik", [
        "Nandurbar", "Navapur", "Shahada", "Taloda", "Akkalkuwa", "Akrani",
    ]),
    District("Jalgaon", "JLG", "Nashik", [
        "Jalgaon", "Bhusawal", "Amalner", "Chalisgaon", "Chopda", "Dharangaon",
        "Erandol", "Jamner", "Muktainagar", "Pachora", "Parola", "Raver",
        "Bhadgaon", "Bodwad", "Yawal",
    ]),
    District("Ahilyanagar", "AHN", "Nashik", [
        "Ahilyanagar", "Shrirampur", "Sangamner", "Kopargaon", "Rahuri",
        "Newasa", "Shevgaon", "Pathardi", "Parner", "Akole", "Jamkhed",
        "Karjat", "Rahata", "Shrigonda",
    ]),

    # ---------------- Chhatrapati Sambhajinagar Division ----------------
    District("Chhatrapati Sambhajinagar", "CSN", "Chhatrapati Sambhajinagar", [
        "Chhatrapati Sambhajinagar", "Paithan", "Gangapur", "Vaijapur",
        "Kannad", "Khuldabad", "Sillod", "Soegaon", "Phulambri",
    ]),
    District("Jalna", "JLN", "Chhatrapati Sambhajinagar", [
        "Jalna", "Bhokardan", "Jafrabad", "Partur", "Mantha", "Ghansawangi",
        "Ambad", "Badnapur",
    ]),
    District("Beed", "BED", "Chhatrapati Sambhajinagar", [
        "Beed", "Ashti", "Patoda", "Shirur Kasar", "Georai", "Majalgaon",
        "Wadwani", "Kaij", "Dharur", "Parli", "Ambajogai",
    ]),
    District("Dharashiv", "DHR", "Chhatrapati Sambhajinagar", [
        "Dharashiv", "Tuljapur", "Omerga", "Lohara", "Kalamb",
        "Bhoom", "Paranda", "Washi",
    ]),
    District("Latur", "LTR", "Chhatrapati Sambhajinagar", [
        "Latur", "Ausa", "Nilanga", "Udgir", "Ahmedpur", "Chakur",
        "Deoni", "Jalkot", "Renapur", "Shirur Anantpal",
    ]),
    District("Nanded", "NND", "Chhatrapati Sambhajinagar", [
        "Nanded", "Ardhapur", "Bhokar", "Biloli", "Deglur", "Dharmabad",
        "Hadgaon", "Himayatnagar", "Kandhar", "Kinwat", "Loha", "Mahur",
        "Mudkhed", "Mukhed", "Naigaon", "Umri",
    ]),
    District("Parbhani", "PRB", "Chhatrapati Sambhajinagar", [
        "Parbhani", "Gangakhed", "Jintur", "Manwath", "Palam",
        "Pathri", "Purna", "Sailu", "Sonpeth",
    ]),
    District("Hingoli", "HNG", "Chhatrapati Sambhajinagar", [
        "Hingoli", "Kalamnuri", "Basmath", "Sengaon", "Aundha Nagnath",
    ]),

    # ---------------- Amravati Division ----------------
    District("Amravati", "AMR", "Amravati", [
        "Amravati", "Bhatkuli", "Nandgaon Khandeshwar", "Dharni", "Chikhaldara",
        "Achalpur", "Chandur Bazar", "Morshi", "Warud", "Daryapur",
        "Anjangaon Surji", "Chandur Railway", "Teosa", "Dhamangaon Railway",
    ]),
    District("Akola", "AKL", "Amravati", [
        "Akola", "Akot", "Balapur", "Barshitakli", "Murtizapur", "Patur", "Telhara",
    ]),
    District("Washim", "WSM", "Amravati", [
        "Washim", "Risod", "Malegaon", "Mangrulpir", "Karanja", "Manora",
    ]),
    District("Buldhana", "BLD", "Amravati", [
        "Buldhana", "Chikhli", "Deulgaon Raja", "Jalgaon Jamod", "Khamgaon",
        "Lonar", "Malkapur", "Mehkar", "Motala", "Nandura", "Sangrampur",
        "Shegaon", "Sindkhed Raja",
    ]),
    District("Yavatmal", "YTL", "Amravati", [
        "Yavatmal", "Arni", "Babhulgaon", "Darwha", "Digras", "Ghatanji",
        "Kalamb", "Kelapur", "Mahagaon", "Maregaon", "Ner", "Pusad",
        "Ralegaon", "Umarkhed", "Wani", "Zari Jamani",
    ]),

    # ---------------- Nagpur Division ----------------
    District("Nagpur", "NGP", "Nagpur", [
        "Nagpur Urban", "Nagpur Rural", "Kamptee", "Hingna", "Katol", "Narkhed",
        "Savner", "Kalameshwar", "Ramtek", "Mauda", "Parseoni", "Umred",
        "Kuhi", "Bhiwapur",
    ]),
    District("Wardha", "WRD", "Nagpur", [
        "Wardha", "Deoli", "Seloo", "Arvi", "Ashti", "Karanja",
        "Hinganghat", "Samudrapur",
    ]),
    District("Bhandara", "BHN", "Nagpur", [
        "Bhandara", "Mohadi", "Tumsar", "Pauni", "Lakhandur", "Lakhani", "Sakoli",
    ]),
    District("Gondia", "GON", "Nagpur", [
        "Gondia", "Tirora", "Goregaon", "Amgaon", "Salekasa",
        "Deori", "Arjuni Morgaon", "Sadak Arjuni",
    ]),
    District("Chandrapur", "CHN", "Nagpur", [
        "Chandrapur", "Ballarpur", "Bhadravati", "Brahmapuri", "Chimur",
        "Gondpipri", "Jiwati", "Korpana", "Mul", "Nagbhid", "Pombhurna",
        "Rajura", "Saoli", "Sindewahi", "Warora",
    ]),
    District("Gadchiroli", "GDC", "Nagpur", [
        "Gadchiroli", "Armori", "Desaiganj", "Chamorshi", "Mulchera",
        "Etapalli", "Bhamragad", "Aheri", "Sironcha", "Korchi",
        "Kurkheda", "Dhanora",
    ]),
]


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

DISTRICT_BY_NAME: Dict[str, District] = {d.name: d for d in DISTRICTS}
DISTRICT_BY_CODE: Dict[str, District] = {d.code: d for d in DISTRICTS}


def districts_in_division(division: str) -> List[District]:
    """All districts belonging to one revenue division."""
    return [d for d in DISTRICTS if d.division == division]


def talukas_of(district_name: str) -> List[str]:
    """Taluka list for a district, empty if the district is unknown."""
    d = DISTRICT_BY_NAME.get(district_name)
    return list(d.talukas) if d else []


def district_code(district_name: str) -> str:
    """Three-letter revenue code used in the Seva ID."""
    d = DISTRICT_BY_NAME.get(district_name)
    if d is None:
        raise KeyError(f"Unknown district: {district_name!r}")
    return d.code


def all_district_names() -> List[str]:
    return [d.name for d in DISTRICTS]


def total_talukas() -> int:
    return sum(len(d.talukas) for d in DISTRICTS)


if __name__ == "__main__":
    print(f"Divisions : {len(DIVISIONS)}")
    print(f"Districts : {len(DISTRICTS)}")
    print(f"Talukas   : {total_talukas()}")
    for div in DIVISIONS:
        ds = districts_in_division(div)
        print(f"  {div:32s} {len(ds):2d} districts")

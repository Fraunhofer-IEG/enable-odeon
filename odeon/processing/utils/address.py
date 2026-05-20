
import re
import unicodedata


def standardize_street_name(street: str) -> str:
    street = str(street).lower()
    street = street.replace("ß", "ss")
    street = street.replace("ä", "ae")
    street = street.replace("ö", "oe")
    street = street.replace("ü", "ue")
    street = street.replace("é", "e")
    street = street.replace("è", "e")
    street = street.replace("ê", "e")
    # Normalize the string to decompose special characters
    street = unicodedata.normalize("NFKD", street)
    # Remove diacritical marks (accents) by filtering out combining characters
    street = "".join(c for c in street if not unicodedata.combining(c))
    # Replace specific patterns
    street = street.replace("ß", "ss")
    street = street.replace("straße", "str.")
    street = street.replace("strasse", "str.")
    # Replace multiple spaces with a single space and strip leading/trailing spaces
    street = re.sub(r"\s+", " ", street).strip()
    return street


def standardize_house_number(house_number: str | int | None) -> list[str]:
    """
    Standardize house number formats into a list of standardized house numbers.

    Performed actions:

    - Handles ranges like "1-5" or "2 bis 6" and expands them into lists.
    - Handles multiple numbers separated by commas or slashes.
    - Standardizes single house number formats like "35a", "b35", "35 A", etc.
    """
    # Überprüfung auf None
    if house_number is None:
        return [None]  # Rückgabe einer leeren Liste

    # Entferne Leerzeichen und mache alles klein
    house_number = str(house_number).replace(" ", "").strip().lower()

    # Standardisiere Bereiche wie "1-5" oder "2-6" zu Listen
    range_pattern = r"(\d+)\s*[-bis]\s*(\d+)"
    match = re.match(range_pattern, house_number)
    if match:
        start, end = map(int, match.groups())

        # Überprüfe, ob die Start- und Endnummer gleichmäßig oder ungerade sind
        if start % 2 == end % 2:  # Beide gleich (gerade oder ungerade)
            return [str(num) for num in range(start, end + 1, 2)]  # Zähle in Schritten von 2 und konvertiere zu str
        else:
            return [str(num) for num in range(start, end + 1)]  # Alle Zahlen zwischen start und end, konvertiert zu str

    # Standardisiere Mehrfachnummern wie "35, 36, 37" oder "35 / 36"
    if re.search(r"[,/]", house_number):
        numbers = re.findall(r"[a-zA-Z]*\d+[a-zA-Z]*", house_number)
        new_numbers = []
        for n in numbers:
            new_numbers.extend(standardize_house_number(n))
        return sorted(set(map(str, new_numbers)))  # Eindeutige und sortierte Liste als str

    # Standardisiere Einzelformate wie "35a", "b35", "35 A", etc.
    single_pattern = r"([a-zA-Z]?)\s*(\d+)\s*([a-zA-Z]?)"
    match = re.match(single_pattern, house_number)
    if match:
        prefix, number, suffix = match.groups()
        return [f"{number}{prefix}{suffix}".lower()]

    # Falls nichts passt, gib die Eingabe als Einzelwert zurück
    return [str(house_number)]
